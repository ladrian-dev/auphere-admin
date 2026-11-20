"""Lectura/escritura de ``partner_model_allowlist`` bajo GUC ya fijado.

Spec 016 (R5.3): la allowlist es la única verdad de lo que un partner puede
elegir. Spec 065: cuando se reescribe sin un modelo que algún agente tenía elegido por
el partner, ``reconcile_agents`` lo pasa al modelo por defecto —desde su siguiente
turno— y avisa al partner con ``agent.model_reset``. La asignación de cliente
(``client.model_reset``) ya no decide nada.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.partner_model_allowlist import PartnerModelAllowlist

log = structlog.get_logger(__name__)


async def read_allowlist(session: AsyncSession, partner_id: uuid.UUID) -> frozenset[str]:
    rows = await session.scalars(
        sa.select(PartnerModelAllowlist.model_id).where(
            PartnerModelAllowlist.partner_id == partner_id
        )
    )
    return frozenset(str(mid) for mid in rows.all())


async def replace_allowlist(
    session: AsyncSession, partner_id: uuid.UUID, model_ids: list[str]
) -> frozenset[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for mid in model_ids:
        if mid in seen:
            continue
        seen.add(mid)
        unique.append(mid)
    await session.execute(
        sa.delete(PartnerModelAllowlist).where(PartnerModelAllowlist.partner_id == partner_id)
    )
    for mid in unique:
        session.add(PartnerModelAllowlist(partner_id=partner_id, model_id=mid))
    await session.flush()
    return frozenset(unique)


@dataclass(frozen=True)
class AgentModelReset:
    """Un agente que volvió al modelo por defecto porque su modelo dejó de ofrecerse."""

    partner_id: uuid.UUID
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    external_client_ref: str
    agent_name: str
    from_model: str
    to_model: str


async def reconcile_agents(
    partner_id: uuid.UUID, allowed: frozenset[str], *, actor: str
) -> list[AgentModelReset]:
    """Pasa al modelo por defecto los agentes cuyo modelo ya no está en la lista (spec 065).

    Solo las elecciones del partner (requisito 8.2): las de Auphere no cambian (8.3). Se
    llama DESPUÉS de que la lista nueva esté confirmada. Nunca lanza."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import PartnerTenant

    async with get_sessionmaker()() as session, session.begin():
        mappings = [
            (partner_id, uuid.UUID(str(t)), str(r))
            for t, r in (
                await session.execute(
                    sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref).where(
                        PartnerTenant.partner_id == partner_id
                    )
                )
            ).all()
        ]
    return await _reset_partner_choices(
        mappings, lambda model_id: model_id not in allowed, actor=actor
    )


async def reset_choices_of_model(model_id: str, *, actor: str) -> list[AgentModelReset]:
    """Spec 065 (requisito 1.4): un modelo deja de estar habilitado para responder; los
    agentes de cualquier partner que lo tenían elegido pasan al modelo por defecto, con su
    aviso. Las elecciones de Auphere no cambian (8.3). Nunca lanza."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import PartnerTenant

    async with get_sessionmaker()() as session, session.begin():
        mappings = [
            (uuid.UUID(str(p)), uuid.UUID(str(t)), str(r))
            for p, t, r in (
                await session.execute(
                    sa.select(
                        PartnerTenant.partner_id,
                        PartnerTenant.tenant_id,
                        PartnerTenant.external_client_ref,
                    )
                )
            ).all()
        ]
    return await _reset_partner_choices(mappings, lambda chosen: chosen == model_id, actor=actor)


async def _reset_partner_choices(
    mappings: list[tuple[uuid.UUID, uuid.UUID, str]],
    should_reset: Callable[[str], bool],
    *,
    actor: str,
) -> list[AgentModelReset]:
    """Una sesión por cliente, con su GUC; el aviso ``agent.model_reset`` es del partner y va
    en la suya, uno por agente, con el modelo con el que responde ahora. Un cliente que no se
    pueda leer se salta y se registra."""
    from nexus_api.core.respond_catalog import RESPOND_MODEL_ID_SET, agent_respond_default
    from nexus_api.core.respond_model import resolve
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import Agent, NotificationKind, NotificationSeverity
    from nexus_api.db.models.model_profile import ModelProfile
    from nexus_api.services.agent_model import agent_facts, set_agent_model
    from nexus_api.services.console_notifications import emit_detached

    sm = get_sessionmaker()
    resets: list[AgentModelReset] = []
    for partner_id, tenant_id, ref in mappings:
        try:
            moved: list[AgentModelReset] = []
            async with sm() as scoped, tenant_scoped_session(scoped, tenant_id):
                rows = (
                    await scoped.execute(
                        sa.select(
                            Agent.id, Agent.name, ModelProfile.model_id, ModelProfile.display_name
                        )
                        .join(ModelProfile, ModelProfile.id == Agent.respond_model_profile_id)
                        .where(Agent.status == "active", Agent.respond_model_set_by == "partner")
                    )
                ).all()
                for agent_id, name, model_id, display in rows:
                    if not should_reset(str(model_id)):
                        continue
                    await set_agent_model(
                        scoped,
                        agent_id=agent_id,
                        model_id=None,
                        set_by="operator",
                        actor=actor,
                        allowed=None,
                        action="admin.agent.model.update",
                        reason="model_no_longer_offered",
                    )
                    facts = await agent_facts(scoped, agent_id)
                    now_on = resolve(
                        None,
                        facts.version_override,
                        agent_respond_default(),
                        agent_needs=facts.needs,
                        enabled=RESPOND_MODEL_ID_SET,
                    ).model_id
                    to_name = await scoped.scalar(
                        sa.select(ModelProfile.display_name).where(ModelProfile.model_id == now_on)
                    )
                    moved.append(
                        AgentModelReset(
                            partner_id=partner_id,
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            external_client_ref=ref,
                            agent_name=str(name),
                            from_model=str(display),
                            to_model=str(to_name or now_on),
                        )
                    )
                await scoped.commit()
            for reset in moved:
                await emit_detached(
                    partner_id=reset.partner_id,
                    kind=NotificationKind.AGENT_MODEL_RESET,
                    data={
                        "external_client_ref": reset.external_client_ref,
                        "agent_id": str(reset.agent_id),
                        "agent": reset.agent_name,
                        "from_model": reset.from_model,
                        "to_model": reset.to_model,
                    },
                    severity=NotificationSeverity.INFO,
                    external_client_ref=reset.external_client_ref,
                    dedupe_key=(
                        f"partner:{reset.partner_id}:agent.model_reset:{reset.agent_id}:"
                        f"{reset.from_model}:{datetime.now(UTC):%Y-%m-%d}"
                    ),
                )
            resets.extend(moved)
        except Exception as exc:
            log.warning(
                "partner_allowlist.reset_choices_failed",
                partner_id=str(partner_id),
                tenant_id=str(tenant_id),
                error=str(exc),
            )
    return resets


__all__ = [
    "AgentModelReset",
    "read_allowlist",
    "reconcile_agents",
    "replace_allowlist",
    "reset_choices_of_model",
]
