"""Encender Reservas desde un agente — spec 057 (requisitos 1.4, 1.8, 5.2 y 7).

«Gestiona citas», en el alta o en Conectores, enciende Reservas para el cliente si
hace falta, antes de que el constructor escriba o de que el borrador gane la agenda.
Lo hace quien edita agentes (``agents:write``); apagarlo sigue siendo cosa de Acceso.

Corre **dentro** de la ruta de la consola, bajo la RLS del cliente (``nexus_app`` y
``app.tenant_id`` del contexto, ``client_scope`` o ``tenant_scoped_session``):

- no usa ``admin.as_tenant``, cuyo ``RESET ROLE`` devolvería la petición al rol de la
  conexión;
- no llama a ``client_access.set_access``, que reescribe ``enabled`` y los módulos y
  toca ``console_auth.*`` (por eso exige ``client_access:manage`` y no corre así);
- el partner sale del ``PartnerTenant`` ya resuelto por la ruta, nunca del cuerpo.

Añade ``reservas`` a los módulos sin tocar ``enabled`` ni los demás (el acceso de las
personas del cliente es otra cosa, spec 048, decisión 16), crea los ajustes con el modo
elegido y prepara la agenda, en un borrador sin publicar, a los **otros** agentes que
dan citas (5.1 y 5.2). Dos agentes que encienden a la vez no chocan: candado por cliente.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    AuditLog,
    ClientAccess,
    ClientModule,
    ReservationSettings,
    Tenant,
    TenantStatus,
)
from nexus_api.services.reservations import admin as reservations_admin
from nexus_api.services.reservations import passing
from nexus_api.services.reservations.core import lock

log = structlog.get_logger(__name__)

#: La acción de auditoría, la misma que Acceso y el paso automático.
AUDIT_ACTION: Final = "client_access.updated"


class TurnOnRefused(Exception):
    """El cliente no puede encender Reservas (archivado, sin partner)."""

    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class TurnedOn:
    """Lo que pasó. ``turned_on`` es falso si ya estaba encendido: el modo no cambia
    desde un agente (es del cliente, se cambia en Acceso)."""

    turned_on: bool
    mode: str
    capacity_kind: str | None
    prepared: list[passing.PreparedAgent] = field(default_factory=list)


def add_reservas_module(
    session: AsyncSession,
    access: ClientAccess | None,
    *,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    actor: str,
    extra: dict[str, Any],
) -> ClientAccess:
    """``reservas`` en la lista de módulos del cliente, con ``enabled`` como estaba, y
    su fila de auditoría. Sin fila de acceso, la crea cerrada (nadie entra por esto).
    La comparten el paso automático (``auto_pass.turn_on_reservas``) y el agente."""
    if access is None:
        if partner_id is None:
            # ``client_access`` cuelga del partner del cliente.
            raise TurnOnRefused("no_partner")
        access = ClientAccess(tenant_id=tenant_id, partner_id=partner_id, enabled=False, modules=[])
        session.add(access)
    if not access.reservas_on:
        access.modules = list(access.ordered_modules(also=(ClientModule.RESERVAS.value,)))
        access.updated_by = actor
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=actor,
                action=AUDIT_ACTION,
                target=f"tenant:{tenant_id}",
                after_json={"enabled": access.enabled, "modules": list(access.modules), **extra},
            )
        )
    return access


async def suggested_choice(session: AsyncSession) -> reservations_admin.Choice:
    """El modo que corresponde al cliente (requisito 1.3): aforo de restaurante para un
    restaurante; por servicio y profesional para el resto. El mismo criterio que el paso
    automático (``auto_pass.choose_mode``). Bajo la RLS del cliente; solo lee."""
    from nexus_api.services.reservations.auto_pass import choose_mode

    mode = await choose_mode(session)
    return reservations_admin.Choice(mode=mode.mode, capacity_kind=mode.capacity_kind)


async def turn_on_from_agent(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    choice: reservations_admin.Choice | None,
    actor: str,
    origin_agent_id: uuid.UUID | None,
    now: datetime,
) -> TurnedOn:
    """Reservas encendido para el cliente de la ruta. ``choice`` es obligatorio la
    primera vez (``reservas_mode_required``); si el cliente ya tuvo Reservas, vuelve con
    su modo. ``origin_agent_id``: el agente desde el que se enciende, que no recibe el
    borrador de 5.1 (su cambio es el del alta o el de Conectores)."""
    await lock(session, f"reservas-on:{tenant_id}")
    settings = await session.get(ReservationSettings, tenant_id)
    if await passing.reservas_enabled(session, tenant_id):
        assert settings is not None
        return TurnedOn(False, settings.mode, settings.capacity_kind)

    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.status == TenantStatus.ARCHIVED:
        raise TurnOnRefused("archived")
    if settings is None:
        if choice is None:
            raise reservations_admin.ReservasChoiceError("reservas_mode_required", 422)
        reservations_admin.validate_choice(choice)
    mode = settings.mode if settings is not None else choice.mode  # type: ignore[union-attr]
    kind = (
        settings.capacity_kind if settings is not None else choice.capacity_kind  # type: ignore[union-attr]
    )

    add_reservas_module(
        session,
        await session.get(ClientAccess, tenant_id),
        tenant_id=tenant_id,
        partner_id=partner_id,
        actor=actor,
        extra={
            "from_agent": str(origin_agent_id) if origin_agent_id else "new_agent",
            "mode": mode,
            "capacity_kind": kind,
        },
    )
    await session.flush()
    await reservations_admin.apply_choice(
        session,
        tenant_id,
        had_module=False,
        wants_module=True,
        # Con ajustes de antes, vuelve con su modo: cambiarlo es cosa de Acceso.
        choice=choice if settings is None else None,
        actor=actor,
        now=now,
        prepare_agents=False,
    )
    report = await passing.pass_to_reservas(
        session,
        tenant_id,
        actor=actor,
        now=now,
        scope="givers",
        exclude=frozenset({origin_agent_id}) if origin_agent_id else frozenset(),
    )
    log.info(
        "reservas.turned_on_from_agent",
        tenant_id=str(tenant_id),
        agent_id=str(origin_agent_id) if origin_agent_id else None,
        mode=mode,
    )
    return TurnedOn(True, mode, kind, list(report.agents))


__all__ = [
    "AUDIT_ACTION",
    "TurnOnRefused",
    "TurnedOn",
    "add_reservas_module",
    "suggested_choice",
    "turn_on_from_agent",
]
