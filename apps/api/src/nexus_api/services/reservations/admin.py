"""Reservas desde el panel de operador — spec 043 (Requisito 1).

El admin activa el módulo ``reservas`` en la pestaña Acceso y elige el modo
(y, en Aforo, el tipo de negocio) en la misma llamada. Aquí vive lo que eso
cambia en Reservas:

- la primera activación crea los ajustes con los valores de partida;
- cambiar de modo con reservas futuras vivas es un 409 con cuántas, salvo que el
  admin pida **cancelarlas y avisar**; nunca conviven dos modos en una agenda;
- activar o desactivar prepara, por cada agente activo, una versión **no
  activa** con (o sin) ``reservas.*`` y sin ``booking.*``. Promoverla es de una
  persona (constitución §IV).

La sesión del admin trabaja sin RLS (``declare_tenant``). Esta parte se hace
bajo la RLS del cliente **en la misma transacción** (:func:`as_tenant`), para
que cada consulta del dominio vea solo sus filas y todo se confirme o se
deshaga junto.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AgentStatus,
    AuditLog,
    Reservation,
    ReservationSettings,
)
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.reservations.core import Actor, cancel_booking, load_ctx
from nexus_api.services.reservations.settings import apply_defaults

#: Lo que el agente gana al activar Reservas (contrato ``agent-tools.md``).
RESERVAS_TOOLS: tuple[str, ...] = (
    "reservas.services",
    "reservas.find_slots",
    "reservas.create",
    "reservas.list_mine",
    "reservas.reschedule",
    "reservas.cancel",
    "reservas.confirm_attendance",
    "reservas.join_waitlist",
    "reservas.answer_offer",
)
#: Lo que pierde: escribían en ``appointments``, que la consola no ve.
LEGACY_PREFIX = "booking."


class ReservasChoiceError(Exception):
    def __init__(self, code: str, status: int, **info: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.info = info


@dataclass(frozen=True)
class Choice:
    mode: str
    capacity_kind: str | None = None
    on_live: str = "refuse"  # refuse | cancel_and_notify


@asynccontextmanager
async def as_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> AsyncIterator[None]:
    """Bajo la RLS del cliente dentro de la transacción del admin, y de vuelta."""
    await apply_tenant_to_session(session, tenant_id)
    try:
        with tenant_context(tenant_id):
            yield
    finally:
        await session.execute(sa.text("RESET ROLE"))


async def live_future(session: AsyncSession, now: datetime) -> int:
    return int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(Reservation)
            .where(Reservation.status.in_(("pending", "confirmed")), Reservation.starts_at > now)
        )
        or 0
    )


def _validate(choice: Choice) -> None:
    if choice.mode not in ("services", "capacity"):
        raise ReservasChoiceError("reservas_mode_required", 422)
    if choice.mode == "capacity" and not choice.capacity_kind:
        raise ReservasChoiceError("reservas_kind_required", 422)
    if choice.mode == "services" and choice.capacity_kind:
        raise ReservasChoiceError("reservas_kind_forbidden", 422)


async def apply_choice(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    had_module: bool,
    wants_module: bool,
    choice: Choice | None,
    actor: str,
    now: datetime,
) -> None:
    """Lo que la llamada del admin cambia en Reservas. Corre bajo la RLS."""
    settings = await session.get(ReservationSettings, tenant_id)
    if choice is not None:
        _validate(choice)
    if wants_module and settings is None and choice is None:
        raise ReservasChoiceError("reservas_mode_required", 422)

    if choice is not None and settings is None:
        settings = ReservationSettings(tenant_id=tenant_id, version=1, updated_by=actor)
        apply_defaults(settings, choice.mode, choice.capacity_kind)
        session.add(settings)
        await session.flush()
    elif choice is not None and settings is not None and choice.mode != settings.mode:
        count = await live_future(session, now)
        if count and choice.on_live != "cancel_and_notify":
            raise ReservasChoiceError("live_reservations", 409, count=count)
        cancelled = 0
        if count:
            ctx = await load_ctx(session, tenant_id)
            assert ctx is not None
            rows = (
                await session.execute(
                    sa.select(Reservation).where(
                        Reservation.status.in_(("pending", "confirmed")),
                        Reservation.starts_at > now,
                    )
                )
            ).scalars()
            for res in list(rows):
                await cancel_booking(
                    session,
                    ctx,
                    res,
                    by="business",
                    actor=Actor("person", "Auphere"),
                    now=now,
                    notify=True,
                    cause="mode_change",
                    check_allowed=False,
                )
                cancelled += 1
        before = settings.mode
        apply_defaults(settings, choice.mode, choice.capacity_kind)
        settings.version += 1
        settings.updated_by = actor
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=actor,
                action="reservations.mode_changed",
                target=f"tenant:{tenant_id}",
                after_json={"from": before, "to": choice.mode, "cancelled": cancelled},
            )
        )
    elif (
        choice is not None
        and settings is not None
        and settings.mode == "capacity"
        and choice.capacity_kind != settings.capacity_kind
    ):
        # Cambiar el tipo cambia las palabras; los números son del negocio.
        settings.capacity_kind = choice.capacity_kind
        settings.version += 1
        settings.updated_by = actor

    if had_module != wants_module:
        await prepare_agent_versions(session, enable=wants_module, actor=actor)
    await session.flush()


def _tools(current: list[str], *, enable: bool) -> list[str]:
    tools = set(current)
    if enable:
        tools = {t for t in tools if not t.startswith(LEGACY_PREFIX)} | set(RESERVAS_TOOLS)
    else:
        tools -= set(RESERVAS_TOOLS)
    return sorted(tools)


async def prepare_agent_versions(session: AsyncSession, *, enable: bool, actor: str) -> int:
    """Una versión preparada por agente activo, sin promover."""
    svc = AgentConfigService(session)
    agents = (
        await session.execute(
            sa.select(Agent.id)
            .where(Agent.status == AgentStatus.ACTIVE.value)
            .order_by(Agent.created_at)
        )
    ).scalars()
    staged = 0
    for agent_id in list(agents):
        versions = await svc.list_versions(agent_id=agent_id)
        base = max(versions, key=lambda v: v.version, default=None)
        if base is None:
            continue
        new_tools = _tools(list(base.tools), enable=enable)
        if new_tools == sorted(base.tools):
            continue
        await svc.stage_new_version(
            actor=actor,
            system_prompt_rendered=base.system_prompt_rendered,
            channels=list(base.channels),
            tools=new_tools,
            policies=dict(base.policies),
            seed_template_ref=base.seed_template_ref,
            kg_schema_id=base.kg_schema_id,
            agent_id=agent_id,
        )
        staged += 1
    return staged


async def admin_view(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime
) -> dict[str, Any] | None:
    settings = await session.get(ReservationSettings, tenant_id)
    if settings is None:
        return None
    pending: list[dict[str, Any]] = []
    agents = (
        await session.execute(
            sa.select(Agent.id, Agent.name).where(Agent.status == AgentStatus.ACTIVE.value)
        )
    ).all()
    for agent_id, name in agents:
        active = await session.scalar(
            sa.select(sa.func.max(AgentConfig.version)).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
        staged = await session.scalar(
            sa.select(sa.func.max(AgentConfig.version)).where(
                AgentConfig.agent_id == agent_id,
                AgentConfig.status == AgentConfigStatus.STAGED,
                AgentConfig.version > (active or 0),
                AgentConfig.created_by.like("operator:%"),
            )
        )
        if staged is not None:
            pending.append({"agent_id": agent_id, "name": str(name), "version": int(staged)})
    return {
        "mode": settings.mode,
        "capacity_kind": settings.capacity_kind,
        "live_future": await live_future(session, now),
        "agents_pending_promotion": pending,
    }


__all__ = [
    "RESERVAS_TOOLS",
    "Choice",
    "ReservasChoiceError",
    "admin_view",
    "apply_choice",
    "as_tenant",
    "live_future",
    "prepare_agent_versions",
]
