"""El código que trae una sesión de Google a la aplicación — spec 009, H2.

**El de emparejamiento ata una máquina; éste ata una persona.** Se teclean
igual, a propósito: mismo alfabeto, misma longitud, mismos diez minutos, porque
la persona los escribe en la misma hoja de la misma barra. Lo que cambia es qué
queda atado, y eso no se ve al teclear — por eso la pantalla tiene que decirlo.

**La regla que gobierna este fichero: un rechazo nunca cuenta por qué.** Caducado,
ya usado, inexistente o mal escrito devuelven exactamente la misma excepción con
exactamente el mismo texto (R4.5). Quien prueba códigos no puede aprender cuáles
existieron ni de quién eran. Es la razón de que este módulo tenga **una sola**
clase de error y de que no acepte un parámetro para matizarla.

**El código NO se ata a la máquina, y es una decisión enmendada** (spec 009,
«Enmienda del 2026-09-15»). Se intentó: quien pide el código es el navegador del
sistema al volver de Google, y no conoce el Mac donde corre la aplicación. Lo
que lo protege son los diez minutos y el uso único — el mismo modelo que el
código de emparejamiento de máquinas, que tampoco ata.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.pairing_codes import CODE_TTL, generate_code, hash_code, normalize_code
from nexus_api.db.models.console_identity import ConsoleAccount
from nexus_api.services import console_identity


class SessionCodeRejected(Exception):
    """El único rechazo que este módulo conoce.

    **Un solo texto, y es deliberado.** Si hubiera dos, la diferencia entre
    ellos sería información: «este código existió» o «este código no es tuyo».
    """

    def __init__(self) -> None:
        super().__init__("el código no vale")


def _now() -> datetime:
    return datetime.now(UTC)


async def issue_session_code(session: AsyncSession, *, principal_id: uuid.UUID) -> str:
    """Emite el código y devuelve el texto en claro. Sólo existe aquí y en la
    pantalla: la base guarda su SHA-256 (R3.3).

    Emitir uno nuevo **invalida el anterior** (R3.4) marcándolo consumido, no
    borrándolo: la fila sigue haciendo falta para que un canje tardío se rechace
    como cualquier otro y no como «no existe».
    """
    await session.execute(
        sa.text(
            "UPDATE console_auth.session_codes SET consumed_at = now() "
            "WHERE principal_id = :p AND consumed_at IS NULL"
        ),
        {"p": str(principal_id)},
    )
    code = generate_code()
    await session.execute(
        sa.text(
            "INSERT INTO console_auth.session_codes "
            "(code_hash, principal_id, expires_at) VALUES (:h, :p, :e)"
        ),
        {
            "h": hash_code(code),
            "p": str(principal_id),
            "e": _now() + CODE_TTL,
        },
    )
    return code


async def redeem_session_code(
    session: AsyncSession,
    *,
    code: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, datetime]:
    """Canjea el código por una **sesión nueva** y devuelve ``(token, expira)``.

    Nueva y no una copia de la del navegador (spec 009, Q1): se acuña con
    ``console_identity.start_session``, el mismo camino que usa el callback de
    Google. Las dos sesiones quedan independientes, y el ``user_agent`` —que la
    cáscara rellena con ``AuphereDesktop/<versión>``— es lo que permite después
    decir cuál hizo qué.

    **Todos los caminos de rechazo terminan igual**, y el orden en que se
    comprueban no cambia lo que se responde.
    """
    normalised = normalize_code(code)
    if normalised is None:
        raise SessionCodeRejected

    fila = (
        await session.execute(
            sa.text(
                "SELECT principal_id FROM console_auth.session_codes "
                "WHERE code_hash = :h AND consumed_at IS NULL AND expires_at > now() "
                "FOR UPDATE"
            ),
            {"h": hash_code(normalised)},
        )
    ).one_or_none()
    if fila is None:
        raise SessionCodeRejected

    await session.execute(
        sa.text("UPDATE console_auth.session_codes SET consumed_at = now() WHERE code_hash = :h"),
        {"h": hash_code(normalised)},
    )

    account = await session.get(ConsoleAccount, fila.principal_id)
    if account is None:  # pragma: no cover - FK CASCADE lo impide
        raise SessionCodeRejected
    return await console_identity.start_session(session, account, ip=ip, user_agent=user_agent)


__all__ = [
    "CODE_TTL",
    "SessionCodeRejected",
    "issue_session_code",
    "redeem_session_code",
]
