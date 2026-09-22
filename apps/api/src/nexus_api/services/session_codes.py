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

**El código se ata con PKCE** (RFC 7636), no con la máquina. Se intentó con el
`hostname` y no había a qué atarlo; PKCE lo resuelve mejor: el `code_verifier`
se genera en la aplicación y **no sale de su proceso**, así que un código visto
en la URL del retorno —en un historial, en un log de proxy, en la pantalla— no
le sirve a nadie. Es la atadura que la spec quería, con nombre estándar.

**Y el límite de intentos es obligatorio, no decorativo.** PKCE no lo sustituye:
sin él, la ruta pública del canje admite intentos infinitos y gratis contra una
consulta que toca base de datos. Se usa el mismo `PairingRateLimiter` que el
emparejamiento, con la misma política.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.one_time_codes import CODE_TTL, generate_code, hash_code, normalize_code
from nexus_api.db.models.console_identity import ConsoleAccount
from nexus_api.services import console_identity
from nexus_api.services.one_time_code_limits import CodeRateLimiter as PairingRateLimiter


class SessionCodeRejected(Exception):
    """El único rechazo que este módulo conoce.

    **Un solo texto, y es deliberado.** Si hubiera dos, la diferencia entre
    ellos sería información: «este código existió» o «este código no es tuyo».
    """

    def __init__(self) -> None:
        super().__init__("el código no vale")


def _now() -> datetime:
    return datetime.now(UTC)


def pkce_challenge(verifier: str) -> str:
    """S256, que es el único método que esto acepta.

    `plain` existe en el RFC y no se admite aquí: un challenge que es el propio
    verifier no protege de nada, y admitirlo sólo sirve para que alguien lo use
    sin darse cuenta.
    """
    return hashlib.sha256(verifier.encode("utf-8")).hexdigest()


async def issue_session_code(
    session: AsyncSession, *, principal_id: uuid.UUID, code_challenge: str
) -> str:
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
            "(code_hash, principal_id, code_challenge, expires_at) "
            "VALUES (:h, :p, :c, :e)"
        ),
        {
            "h": hash_code(code),
            "p": str(principal_id),
            "c": code_challenge,
            "e": _now() + CODE_TTL,
        },
    )
    return code


async def redeem_session_code(
    session: AsyncSession,
    *,
    code: str,
    code_verifier: str,
    ip: str | None = None,
    user_agent: str | None = None,
    limiter: PairingRateLimiter | None = None,
    attempt_key: str | None = None,
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
    if limiter is not None and attempt_key is not None:
        # Antes de mirar nada: quien ya ha fallado cinco veces espera, y la
        # espera crece. Va primero para que ni siquiera el trabajo de buscar el
        # código sea gratis.
        await limiter.check(attempt_key)

    normalised = normalize_code(code)
    if normalised is None:
        await _punish(limiter, attempt_key)
        raise SessionCodeRejected

    fila = (
        await session.execute(
            sa.text(
                "SELECT principal_id, code_challenge FROM console_auth.session_codes "
                "WHERE code_hash = :h AND consumed_at IS NULL AND expires_at > now() "
                "FOR UPDATE"
            ),
            {"h": hash_code(normalised)},
        )
    ).one_or_none()
    if fila is None:
        await _punish(limiter, attempt_key)
        raise SessionCodeRejected
    # PKCE. Va después de encontrar la fila y produce el MISMO error: si se
    # distinguieran, acertar el código y fallar el verifier confirmaría que el
    # código existe.
    if not hmac.compare_digest(str(fila.code_challenge), pkce_challenge(code_verifier)):
        await _punish(limiter, attempt_key)
        raise SessionCodeRejected

    await session.execute(
        sa.text("UPDATE console_auth.session_codes SET consumed_at = now() WHERE code_hash = :h"),
        {"h": hash_code(normalised)},
    )

    if limiter is not None and attempt_key is not None:
        # Un canje correcto limpia la cuenta: esa máquina ya no es sospechosa.
        await limiter.clear(attempt_key)

    account = await session.get(ConsoleAccount, fila.principal_id)
    if account is None:  # pragma: no cover - FK CASCADE lo impide
        raise SessionCodeRejected
    return await console_identity.start_session(session, account, ip=ip, user_agent=user_agent)


async def _punish(limiter: PairingRateLimiter | None, key: str | None) -> None:
    """Un fallo cuenta, venga de donde venga. **Todos los caminos de rechazo
    pasan por aquí**, o el límite tendría un agujero por el lado que menos se
    mira: el del código mal formado."""
    if limiter is not None and key is not None:
        await limiter.record_failure(key)


__all__ = [
    "CODE_TTL",
    "SessionCodeRejected",
    "issue_session_code",
    "pkce_challenge",
    "redeem_session_code",
]
