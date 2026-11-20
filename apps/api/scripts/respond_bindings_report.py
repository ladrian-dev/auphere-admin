"""Spec 065, T031: qué hará la 0240 con cada cliente, antes de desplegar. **Solo lee.**

La 0240 pasa el modelo de respuesta de cada cliente (``tenant_model_bindings`` con
``role = 'respond'``) a sus agentes activos sin elección propia, y deja de usar la
``fallback_chain`` y el tope por turno de esa fila. Este informe dice, por cliente:

- con qué modelo responde hoy;
- cuántos agentes recibirán ese modelo (activos sin elección) y cuántos no (archivados, o con
  elección propia, que no cambia);
- qué deja de usarse: ``fallback_chain`` y ``max_cost_per_turn_usd``.

Los totales son los que la 0240 deja escritos en su ``RAISE NOTICE`` («N asignaciones de
respuesta, M agentes escritos»): si no coinciden al desplegar, algo cambió entre medias.

Lee con la misma conexión que Alembic (``NEXUS_DATABASE_URL_DIRECT`` si está, si no
``NEXUS_DATABASE_URL``), que es el rol con el que correrá la 0240. Uso, en staging o (con el
sí de Luis) en prod como tarea suelta con la definición de la tarea de migración
(``…-migrate``, la misma imagen y los mismos secretos que la API)::

    cd apps/api && uv run python scripts/respond_bindings_report.py

La transacción es de solo lectura (``SET TRANSACTION READ ONLY``) y desactiva la RLS solo
para leer: con un rol que no la salta (el de la aplicación), falla en voz alta en vez de
enseñar cero clientes. No imprime teléfonos ni contenido de conversaciones: identificadores,
slugs y modelos.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

QUERY = """
SELECT tmb.tenant_id, t.slug, mp.model_id, mp.display_name,
       coalesce(tmb.fallback_chain, '[]'::jsonb) AS fallback_chain,
       tmb.max_cost_per_turn_usd,
       count(a.id) FILTER (
           WHERE a.status = 'active' AND a.respond_model_profile_id IS NULL
       ) AS agents_to_write,
       count(a.id) FILTER (
           WHERE a.status = 'active' AND a.respond_model_profile_id IS NOT NULL
       ) AS agents_with_choice,
       count(a.id) FILTER (WHERE a.status <> 'active') AS agents_not_active
  FROM tenant_model_bindings tmb
  JOIN model_profiles mp ON mp.id = tmb.model_profile_id
  JOIN tenants t ON t.id = tmb.tenant_id
  LEFT JOIN agents a ON a.tenant_id = tmb.tenant_id
 WHERE tmb.role = 'respond'
 GROUP BY tmb.tenant_id, t.slug, mp.model_id, mp.display_name, tmb.fallback_chain,
          tmb.max_cost_per_turn_usd
 ORDER BY tmb.tenant_id
"""


@dataclass(frozen=True)
class Row:
    tenant_id: uuid.UUID
    slug: str
    model_id: str
    display_name: str
    fallback_chain: list[str]
    max_cost_per_turn_usd: Decimal | None
    agents_to_write: int
    agents_with_choice: int
    agents_not_active: int

    @property
    def drops(self) -> list[str]:
        """Lo de esta fila que deja de usarse tras la 0240."""
        out = []
        if self.fallback_chain:
            out.append("fallback_chain")
        if self.max_cost_per_turn_usd is not None:
            out.append("max_cost_per_turn_usd")
        return out


@dataclass(frozen=True)
class Report:
    rows: list[Row] = field(default_factory=list)

    @property
    def bindings_found(self) -> int:
        return len(self.rows)

    @property
    def agents_to_write(self) -> int:
        return sum(r.agents_to_write for r in self.rows)


def _chain(value: Any) -> list[str]:
    if isinstance(value, str):
        value = json.loads(value)
    return [str(v) for v in value or []]


async def read_report(database_url: str, *, probe_write: bool = False) -> Report:
    """Lee el informe en una transacción de solo lectura.

    ``probe_write`` intenta escribir dentro de esa transacción: es para la prueba que fija
    que el informe no puede escribir aunque alguien lo cambie."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            await conn.execute(sa.text("SET LOCAL row_security = off"))
            if probe_write:
                await conn.execute(sa.text("UPDATE agents SET name = name WHERE false"))
                await conn.execute(sa.text("CREATE TEMP TABLE _probe (x int)"))
            result = await conn.execute(sa.text(QUERY))
            rows = [
                Row(
                    tenant_id=r.tenant_id,
                    slug=str(r.slug),
                    model_id=str(r.model_id),
                    display_name=str(r.display_name),
                    fallback_chain=_chain(r.fallback_chain),
                    max_cost_per_turn_usd=r.max_cost_per_turn_usd,
                    agents_to_write=int(r.agents_to_write),
                    agents_with_choice=int(r.agents_with_choice),
                    agents_not_active=int(r.agents_not_active),
                )
                for r in result
            ]
            await conn.rollback()
    finally:
        await engine.dispose()
    return Report(rows=rows)


def render(report: Report) -> str:
    lines = []
    for r in report.rows:
        lines.append(
            f"{r.slug} ({r.tenant_id}) · {r.display_name} [{r.model_id}] · "
            f"recibirán el modelo: {r.agents_to_write} · con elección propia: "
            f"{r.agents_with_choice} · no activos: {r.agents_not_active}"
        )
        if r.drops:
            lines.append(
                f"    deja de usarse: fallback_chain={r.fallback_chain} "
                f"tope={r.max_cost_per_turn_usd}"
            )
    lines.append(
        f"0240_respond_bindings_to_agents: {report.bindings_found} asignaciones de respuesta, "
        f"{report.agents_to_write} agentes escritos"
    )
    return "\n".join(lines)


async def main() -> int:
    from nexus_api.config import get_settings

    settings = get_settings()
    # La conexión de Alembic: el rol con el que correrá la 0240.
    print(render(await read_report(settings.database_url_direct or settings.database_url)))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
