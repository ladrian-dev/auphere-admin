"""La consola nueva, partner a partner — spec 047, T004 (requisito 55.2, research D38).

La consola de la fábrica no se enciende para todos a la vez: Auphere la activa
para cada partner desde el panel de operador. Hasta entonces el partner ve la
consola de hoy y la API sirve a las dos. Tres reglas viven aquí:

* **Un partner sin activar ve ``v1``.** La versión sale de una sola columna,
  ``partners.console_v2_enabled_at``: con fecha, ``v2``; sin ella, ``v1``.
* **Se guarda quién y cuándo.** ``console_v2_enabled_by`` es la persona de
  Auphere que la activó (la base no deja un «quién» sin «cuándo»), y cada
  cambio deja una fila de auditoría de plataforma con antes y después (§IV).
* **Desactivar devuelve la consola de hoy** (55.5). Que solo se pueda hasta
  que el partner confirme el reparto en bolsas llega con esa confirmación
  (ola 10); hoy no hay nada que confirmar.

No es un módulo de ``console_modules`` (spec 032): es un modo de la consola
con estado de migración. Ninguna función confirma: la transacción es del
llamante.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog, Partner

ConsoleVersion = Literal["v1", "v2"]

ENABLED_ACTION = "partner.console_v2_enabled"
DISABLED_ACTION = "partner.console_v2_disabled"


class ConsoleV2Error(Exception):
    """Un no con nombre. ``code`` es vocabulario cerrado; ``status``, el HTTP."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ConsoleV2State:
    version: ConsoleVersion
    enabled_at: datetime | None
    enabled_by: str | None


def console_version(partner: Partner) -> ConsoleVersion:
    """La consola que ve el partner: ``v2`` solo si Auphere la activó."""
    return "v2" if partner.console_v2_enabled_at is not None else "v1"


def _state(partner: Partner) -> ConsoleV2State:
    return ConsoleV2State(
        version=console_version(partner),
        enabled_at=partner.console_v2_enabled_at,
        enabled_by=partner.console_v2_enabled_by,
    )


async def _locked(session: AsyncSession, partner_id: uuid.UUID) -> Partner:
    partner = await session.scalar(
        sa.select(Partner)
        .where(Partner.id == partner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if partner is None:
        raise ConsoleV2Error("unknown_partner", 404)
    return partner


async def _set(
    session: AsyncSession, partner_id: uuid.UUID, *, enable: bool, actor: str
) -> ConsoleV2State:
    if not actor.strip():
        raise ValueError("enabling or disabling the new console needs the person")
    partner = await _locked(session, partner_id)
    before = console_version(partner)
    after: ConsoleVersion = "v2" if enable else "v1"
    if before == after:
        # Repetir no cambia quién ni cuándo, ni deja otra fila.
        return _state(partner)
    if enable:
        partner.console_v2_enabled_at = await session.scalar(sa.select(sa.func.now()))
        partner.console_v2_enabled_by = actor
    else:
        partner.console_v2_enabled_at = None
        partner.console_v2_enabled_by = None
    session.add(
        AuditLog(
            tenant_id=None,
            actor=actor,
            action=ENABLED_ACTION if enable else DISABLED_ACTION,
            target=f"partner:{partner_id}",
            before_json={"console_version": before},
            after_json={"console_version": after},
        )
    )
    await session.flush()
    return _state(partner)


async def enable_console_v2(
    session: AsyncSession, partner_id: uuid.UUID, *, actor: str
) -> ConsoleV2State:
    """Activa la consola nueva para el partner, en nombre de ``actor``."""
    return await _set(session, partner_id, enable=True, actor=actor)


async def disable_console_v2(
    session: AsyncSession, partner_id: uuid.UUID, *, actor: str
) -> ConsoleV2State:
    """Devuelve al partner la consola de hoy, en nombre de ``actor``."""
    return await _set(session, partner_id, enable=False, actor=actor)


__all__ = [
    "DISABLED_ACTION",
    "ENABLED_ACTION",
    "ConsoleV2Error",
    "ConsoleV2State",
    "ConsoleVersion",
    "console_version",
    "disable_console_v2",
    "enable_console_v2",
]
