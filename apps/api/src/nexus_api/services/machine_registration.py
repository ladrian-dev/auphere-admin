"""Registrar una máquina con la sesión — spec 012, Requisito 3.

Sustituye al canje del código de ocho símbolos. **No es superficie nueva**: el
código solo se podía teclear desde una aplicación que ya tenía la sesión
confirmada (`app-runtime.ts` aborta sin `userId`, y `userId` solo llega de un
`whoami` con éxito), así que la autoridad era la sesión antes y lo es ahora. Lo
que se retira es un segundo acto que no probaba nada — y que además es el patrón
que explotó Storm-2372 contra el device code flow.

**La frescura se mira por persona, no por token.** La API no ve la cookie: el
BFF le manda su token de servicio. Así que la pregunta que puede contestar es
«¿esta persona tiene alguna sesión abierta hace poco?», que es exactamente lo que
el requisito quiere saber: si confirmó quién era hace poco. Y se mira el momento
en que la sesión **se abrió**, no el de su último uso: tener la aplicación
abierta mueve el segundo y no demuestra nada.

**Los cuatro motivos de rechazo dan la misma respuesta.** Sin sesión reciente,
sin permiso, en el tope, o cualquier otro. El del tope es el que tienta: parece
amable decir «tienes cinco máquinas», y es contar de más a quien todavía no ha
demostrado ser nadie. Quien ya está dentro lo pregunta por la vía normal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.workstation_limits import (
    MAX_ACTIVE_MACHINES_PER_PRINCIPAL,
    SESSION_FRESH_FOR,
)
from nexus_api.db.models import PartnerDevice
from nexus_api.db.models.console_identity import ConsoleSession

log = structlog.get_logger(__name__)


class RegistrationRefused(Exception):
    """Un registro que no procede.

    Lleva el motivo **para la auditoría y los registros**, nunca para la
    respuesta: la respuesta es una sola y no distingue (R3.4). Separar las dos
    cosas es lo que permite que un rechazo uniforme siga siendo investigable.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class MachineIdentity:
    """Lo que la aplicación sabe de sí misma y la persona no elige."""

    hostname: str
    platform: str
    install_id: str | None
    app_version: str | None = None


async def session_recently_confirmed(
    session: AsyncSession, principal_id: uuid.UUID, *, now: datetime | None = None
) -> bool:
    """¿Entró esta persona hace poco?

    Mira ``created_at`` —cuándo se abrió la sesión— y **no** ``last_used_at``.
    Confundirlos es el error silencioso de este requisito: con el segundo, una
    sesión de hace seis días con la aplicación abierta pasaría por recién
    confirmada, que es el caso exacto que el umbral existe para atajar.
    """
    moment = now or datetime.now(UTC)
    cutoff = moment - SESSION_FRESH_FOR
    newest = (
        await session.execute(
            sa.select(sa.func.max(ConsoleSession.created_at)).where(
                ConsoleSession.principal_id == principal_id,
                ConsoleSession.expires_at > moment,
            )
        )
    ).scalar_one_or_none()
    return newest is not None and newest > cutoff


async def active_machine_count(session: AsyncSession, principal_id: str) -> int:
    """Cuántas máquinas vivas tiene. **Las archivadas no cuentan** (R4.3).

    Si contaran, cada retirada de acceso —y cada restablecimiento de contraseña,
    cuando llegue la spec 011— cerraría el tope un poco más: sería un tope que se
    cierra solo, que es un defecto y no una política.
    """
    return int(
        (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(PartnerDevice)
                .where(
                    PartnerDevice.principal_id == principal_id,
                    PartnerDevice.revoked_at.is_(None),
                )
            )
        ).scalar_one()
    )


async def find_same_install(
    session: AsyncSession, *, principal_id: str, install_id: str | None
) -> PartnerDevice | None:
    """La máquina activa de esta persona para esta instalación, si la hay (R3.7).

    Sin ``install_id`` no se deduplica: es lo que traen las filas de antes de la
    012, y adivinar por ``hostname`` sería peor que no adivinar —cambia al
    renombrar el ordenador y dos «MacBook-Pro» en un partner son normales—.
    """
    if not install_id:
        return None
    return (
        await session.execute(
            sa.select(PartnerDevice)
            .where(
                PartnerDevice.principal_id == principal_id,
                PartnerDevice.install_id == install_id,
                PartnerDevice.revoked_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def assert_can_register(
    session: AsyncSession,
    *,
    principal_uuid: uuid.UUID,
    principal_id: str,
    install_id: str | None,
) -> PartnerDevice | None:
    """Las dos puertas, en el orden en que importan. Devuelve la máquina
    existente si es un re-registro (que no pasa por el tope: no añade ninguna).

    Levanta :class:`RegistrationRefused` con el motivo real, que va a los
    registros y **no** a la respuesta.
    """
    if not await session_recently_confirmed(session, principal_uuid):
        raise RegistrationRefused("session_not_recently_confirmed")

    existing = await find_same_install(session, principal_id=principal_id, install_id=install_id)
    if existing is not None:
        return existing

    if await active_machine_count(session, principal_id) >= MAX_ACTIVE_MACHINES_PER_PRINCIPAL:
        raise RegistrationRefused("machine_cap_reached")
    return None


__all__ = [
    "MachineIdentity",
    "RegistrationRefused",
    "active_machine_count",
    "assert_can_register",
    "find_same_install",
    "session_recently_confirmed",
]
