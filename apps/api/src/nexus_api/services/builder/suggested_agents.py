"""Los agentes que sugiere el constructor del cliente — spec 047, enmienda del
2026-10-29 (requisito 60.6; research D51 y D61).

El constructor del cliente propone los agentes que el negocio podría necesitar.
**No se crean solos**: la pestaña Agentes los enseña como tarjetas «Sugerido» con
«Crear este agente», que abre «Nuevo agente» con su nombre y su descripción (sin
ruta nueva para crear), y «Descartar».

- Uno por nombre: una pasada nueva con el mismo nombre actualiza el pendiente; los
  pendientes que la pasada nueva ya no propone quedan sustituidos (``superseded``).
- Lo descartado **no vuelve**: un nombre descartado no se vuelve a proponer, ni
  para esta ficha ni para otra (D61, más estricto que el requisito, que lo pide
  para la misma ficha).
- Un sugerido con el nombre de un agente que ya existe no se enseña: ya se creó.

Tabla de cliente (``suggested_agents``, migración 0206): RLS FORCE, y el
``tenant_id`` sale siempre del contexto.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Agent, AuditLog
from nexus_api.db.models.business import SUGGESTED_AGENT_ROLES, SuggestedAgent

NAME_MAX: Final = 40
DESCRIPTION_MIN: Final = 20
DESCRIPTION_MAX: Final = 1024
DISMISSED_ACTION: Final = "suggested_agent.dismissed"


def name_key(name: str) -> str:
    """El nombre normalizado: sin mayúsculas, tildes ni espacios de más."""
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(c)
    )
    return " ".join(plain.split())[:60]


def clean(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Un agente propuesto, saneado; ``None`` si no sirve."""
    name = " ".join(str(raw.get("name") or "").split())[:NAME_MAX]
    description = " ".join(str(raw.get("description") or "").split())[:DESCRIPTION_MAX]
    role = raw.get("role")
    if not name or len(description) < DESCRIPTION_MIN:
        return None
    return {
        "name": name,
        "description": description,
        "role": role if role in SUGGESTED_AGENT_ROLES else None,
    }


async def store(
    session: AsyncSession,
    agents: Sequence[Mapping[str, Any]],
    *,
    fingerprint: str | None,
    job_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    """Guarda lo que propone una pasada y devuelve lo que quedó pendiente de ella."""
    tenant_id = require_current_tenant()
    rows = (
        await session.scalars(
            sa.select(SuggestedAgent).where(
                SuggestedAgent.tenant_id == tenant_id,
                SuggestedAgent.status.in_(("open", "dismissed")),
            )
        )
    ).all()
    dismissed = {r.name_key for r in rows if r.status == "dismissed"}
    open_rows = {r.name_key: r for r in rows if r.status == "open"}
    now = datetime.now(UTC)
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in agents:
        item = clean(raw)
        if item is None:
            continue
        key = name_key(item["name"])
        if key in dismissed or key in seen:
            continue
        seen.add(key)
        row = open_rows.get(key)
        if row is None:
            # El orden en que los propone el constructor es el de las tarjetas.
            row = SuggestedAgent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name_key=key,
                status="open",
                created_at=now + timedelta(microseconds=len(seen)),
            )
            session.add(row)
        row.name = item["name"]
        row.description = item["description"]
        row.role = item["role"]
        row.fingerprint = fingerprint
        row.job_id = job_id
        kept.append({"id": str(row.id), **item})
    for key, row in open_rows.items():
        if key not in seen:
            row.status = "superseded"
            row.decided_at = now
            row.decided_by = "system"
    await session.flush()
    return kept


async def list_open(session: AsyncSession) -> list[SuggestedAgent]:
    """Los pendientes del cliente del contexto, sin los que ya existen como agente."""
    tenant_id = require_current_tenant()
    rows = (
        await session.scalars(
            sa.select(SuggestedAgent)
            .where(SuggestedAgent.tenant_id == tenant_id, SuggestedAgent.status == "open")
            .order_by(SuggestedAgent.created_at, SuggestedAgent.id)
        )
    ).all()
    taken = {
        name_key(name)
        for name in (
            await session.scalars(
                sa.select(Agent.name).where(
                    Agent.tenant_id == tenant_id, Agent.status != "archived"
                )
            )
        ).all()
    }
    return [r for r in rows if r.name_key not in taken]


async def dismiss(session: AsyncSession, suggestion_id: uuid.UUID, *, actor: str) -> None:
    """«Descartar»: no vuelve. ``LookupError`` si no es de este cliente. Descartar
    dos veces no falla."""
    tenant_id = require_current_tenant()
    row = await session.scalar(
        sa.select(SuggestedAgent)
        .where(SuggestedAgent.tenant_id == tenant_id, SuggestedAgent.id == suggestion_id)
        .with_for_update()
    )
    if row is None or row.status == "superseded":
        raise LookupError("unknown suggested agent")
    if row.status == "dismissed":
        return
    row.status = "dismissed"
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=DISMISSED_ACTION,
            target=f"suggested_agent:{row.id}",
            before_json=None,
            after_json={"name": row.name},
        )
    )
    await session.flush()


__all__ = ["DISMISSED_ACTION", "clean", "dismiss", "list_open", "name_key", "store"]
