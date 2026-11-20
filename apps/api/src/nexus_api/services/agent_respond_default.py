"""El modelo por defecto de Auphere para los agentes sin elección — spec 065, requisito 13.

Vive en ``platform_settings.agent_respond_default`` (migración 0239; Sol al desplegar) y lo
lee la resolución única por el catálogo cacheado (``respond_catalog.agent_respond_default``).

- :func:`following_default` dice quién lo sigue: los agentes activos sin elección propia y sin
  ajuste de su versión (``policies.llm.respond_model``). Recorre los clientes uno a uno, cada
  uno con su sesión acotada, como el barrido de uso de la 059: nunca una lectura de agentes sin
  la RLS de su cliente.
- :func:`store_default` escribe el ajuste; :func:`return_tests_pass` devuelve la pasada de
  pruebas a los afectados (``agents.tests_pass_returned_at``, spec 047, 68.14): el cambio lo
  hizo Auphere por su cuenta (requisito 13.5).

Cambiarlo es silencioso para los partners (requisito 13.6): aquí no se crea ninguna
notificación.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.respond_catalog import AGENT_RESPOND_DEFAULT_KEY, RESPOND_MODEL_ID_SET
from nexus_api.core.respond_model import resolve
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent

_TENANTS_SQL = sa.text("SELECT id FROM tenants WHERE status <> 'archived' ORDER BY id")
_REFS_SQL = sa.text("SELECT tenant_id, external_client_ref FROM partner_tenants")


@dataclass(frozen=True)
class Affected:
    tenant_id: uuid.UUID
    external_client_ref: str | None
    agent_id: uuid.UUID
    agent_name: str
    current_model: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "external_client_ref": self.external_client_ref,
            "agent_id": str(self.agent_id),
            "agent_name": self.agent_name,
            "current_model": self.current_model,
        }


async def read_setting(session: AsyncSession) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.text(
                "SELECT value #>> '{}' AS model_id, updated_by, updated_at "
                "FROM platform_settings WHERE key = :k"
            ),
            {"k": AGENT_RESPOND_DEFAULT_KEY},
        )
    ).first()
    if row is None or not row.model_id:
        return None
    return {"model_id": str(row.model_id), "set_by": row.updated_by, "set_at": row.updated_at}


async def store_default(session: AsyncSession, model_id: str, *, actor: str) -> str | None:
    """Escribe el ajuste en la transacción de ``session``. Devuelve el anterior."""
    before = await session.scalar(
        sa.text("SELECT value #>> '{}' FROM platform_settings WHERE key = :k FOR UPDATE"),
        {"k": AGENT_RESPOND_DEFAULT_KEY},
    )
    await session.execute(
        sa.text(
            "INSERT INTO platform_settings (key, value, updated_at, updated_by) "
            "VALUES (:k, CAST(:v AS jsonb), now(), :a) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
            "updated_at = now(), updated_by = EXCLUDED.updated_by"
        ),
        {"k": AGENT_RESPOND_DEFAULT_KEY, "v": json.dumps(model_id), "a": actor},
    )
    return None if before is None else str(before)


async def following_default(current_default: str) -> list[Affected]:
    """Los agentes que hoy responden con el modelo por defecto, cliente a cliente."""
    from nexus_api.services.agent_model import agent_facts

    sm = get_sessionmaker()
    async with sm() as session:
        tenants = [uuid.UUID(str(t)) for (t,) in (await session.execute(_TENANTS_SQL))]
        refs = {uuid.UUID(str(t)): str(r) for t, r in (await session.execute(_REFS_SQL))}
    out: list[Affected] = []
    for tenant_id in tenants:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            agents = (
                await session.scalars(
                    sa.select(Agent)
                    .where(Agent.status == "active", Agent.respond_model_profile_id.is_(None))
                    .order_by(Agent.created_at, Agent.id)
                )
            ).all()
            for agent in agents:
                facts = await agent_facts(session, agent.id)
                if facts.version_override:
                    continue
                resolved = resolve(
                    None,
                    None,
                    current_default,
                    agent_needs=facts.needs,
                    enabled=RESPOND_MODEL_ID_SET,
                )
                out.append(
                    Affected(
                        tenant_id=tenant_id,
                        external_client_ref=refs.get(tenant_id),
                        agent_id=agent.id,
                        agent_name=str(agent.name),
                        current_model=resolved.model_id,
                    )
                )
    return out


async def return_tests_pass(affected: list[Affected]) -> None:
    """Les devuelve la pasada de pruebas (requisito 13.5), cada cliente en su sesión."""
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    by_tenant: dict[uuid.UUID, list[uuid.UUID]] = {}
    for row in affected:
        by_tenant.setdefault(row.tenant_id, []).append(row.agent_id)
    for tenant_id, agent_ids in by_tenant.items():
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await session.execute(
                sa.update(Agent).where(Agent.id.in_(agent_ids)).values(tests_pass_returned_at=now)
            )
            await session.commit()


__all__ = [
    "Affected",
    "following_default",
    "read_setting",
    "return_tests_pass",
    "store_default",
]
