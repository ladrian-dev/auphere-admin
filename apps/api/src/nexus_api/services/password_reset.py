"""Recuperar la contraseña — spec 011, Requisitos 1, 2, 3 y 5.

Dos gestos, y el segundo es el que tiene filo.

**Pedir** emite un enlace de un solo uso, invalida los vivos de esa cuenta e
intenta mandarlo. De todo eso, **hacia fuera no se ve nada**: la respuesta es la
misma con cuenta, sin cuenta, con el envío caído y pasado el tope. Ver
``api/console/password_reset.py``, que es donde esa decisión se aplica y donde
está escrita la razón del orden.

**Canjear** hace tres cosas **en una sola transacción** (R3.3): fija la
contraseña nueva, cierra todas las demás sesiones y archiva todas las máquinas.
Las dos últimas no se escriben aquí: las hace ``services/principal_access``, que
la spec 012 construyó **sin commit a propósito** —su docstring dice literalmente
que la 011 la usaría dentro de su misma transacción—. Componerla es el motivo
por el que existe con esa forma, así que se usa, no se reescribe.

El estado que no puede existir es «contraseña nueva, sesiones vivas»: alguien
que restablece porque cree que le entraron, y a quien el producto le dice que ha
terminado mientras el intruso sigue dentro con su cookie siete días.

Sobre el secreto del enlace
---------------------------
``secrets.token_urlsafe(32)`` —256 bits— y en reposo **sólo** su SHA-256. Es el
mismo secreto que emiten las otras dos cosas de este repositorio que viajan
dentro de un enlace de correo: ``SignupRequest`` (``repositories/signup.py``) y
``PartnerInvitation``. Del hash se encarga ``core/one_time_codes.hash_code``,
que es el SHA-256 hex que ya usan los códigos de sesión.

**No se usa ``one_time_codes.generate_code``**, y conviene que quede escrito:
ese generador hace códigos de ocho caracteres de un alfabeto de treinta porque
están pensados para **dictarse en voz alta**. Eso son ~39 bits, y aquí el
secreto no se dicta: viaja en una URL, donde la longitud no le cuesta nada a
nadie y donde el canje no tiene techo por token. Heredar la forma del código
hablado habría sido heredar su compromiso sin heredar su motivo.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.one_time_codes import hash_code
from nexus_api.db.models.console_identity import ConsoleAccount, PasswordResetRequest
from nexus_api.services import console_identity, principal_access

log = structlog.get_logger(__name__)

#: D-6: una hora. Es el mismo umbral que la 012 fijó para «sesión recién
#: confirmada», y por el mismo motivo: suficiente para ir al correo, corto para
#: que un enlace olvidado en una bandeja no siga abriendo la cuenta.
RESET_TTL = timedelta(hours=1)

#: D-6: cinco por dirección y hora. Suficiente para quien no encuentra el
#: correo; insuficiente para barrer direcciones.
REQUESTS_PER_WINDOW = 5
REQUEST_WINDOW = timedelta(hours=1)

#: Lo que queda escrito en la auditoría de la retirada de acceso. El
#: vocabulario del asiento —``principal.access_revoked``— lo sembró la 012 en la
#: migración 0124, y el motivo de archivado de las máquinas lo cierra el CHECK
#: de la 0107: aquí no se inventa ninguno de los dos.
REVOKE_REASON = "password_reset"


class ResetTokenRejected(Exception):
    """El enlace no vale: no existe, caducó o ya se usó.

    **Una sola excepción para los tres**, y no tres con su nombre. Quien la
    captura no puede elegir un mensaje distinto por descuido, que es como se
    construye un oráculo sin querer (R5.3).
    """


def hash_reset_token(plaintext: str) -> str:
    """SHA-256 hex del token. En reposo sólo vive esto."""
    return hash_code(plaintext)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """Una fila recién escrita en la misma transacción puede traer el
    ``datetime`` naive que puso el propio código; comparar los dos revienta."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def invalidate_live_for(session: AsyncSession, account_id: uuid.UUID) -> int:
    """Mata los enlaces vivos de esa cuenta. Devuelve cuántos (R1.6).

    Se sellan con ``used_at`` en vez de borrarse: desde fuera un enlace
    invalidado y uno gastado son el mismo enlace muerto, y la fila que queda es
    lo que permite auditar que existió.
    """
    result = await session.execute(
        sa.update(PasswordResetRequest)
        .where(
            PasswordResetRequest.account_id == account_id,
            PasswordResetRequest.used_at.is_(None),
        )
        .values(used_at=_now())
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def create_request(session: AsyncSession, *, account: ConsoleAccount) -> str:
    """Emite un enlace para esa cuenta y devuelve el token **en claro**.

    El claro no se almacena y es lo único que abre el enlace. Invalidar los
    anteriores va **en la misma transacción** que crea el nuevo: si fueran dos,
    una caída entre medias dejaría dos llaves buenas a la vez, que es justo lo
    que R1.6 prohíbe.
    """
    await invalidate_live_for(session, account.id)
    plaintext = secrets.token_urlsafe(32)
    session.add(
        PasswordResetRequest(
            id=uuid.uuid4(),
            account_id=account.id,
            token_hash=hash_reset_token(plaintext),
            expires_at=_now() + RESET_TTL,
        )
    )
    await session.flush()
    # **Sin el token, y sin el correo.** Lo que se puede decir de una petición
    # es que hubo una; quién la pidió ya está en la fila.
    log.info("password_reset.requested", account_id=str(account.id))
    return plaintext


async def _live_request(session: AsyncSession, token: str) -> PasswordResetRequest | None:
    """La petición detrás de un enlace, o ``None``.

    Inexistente, caducada y ya usada devuelven lo mismo: **los tres casos son el
    mismo desde fuera**, que es lo que impide preguntarle a esta ruta de quién
    era un enlace. ``FOR UPDATE`` porque dos canjes simultáneos del mismo
    enlace tienen que resolverse en uno solo.
    """
    row = (
        await session.execute(
            sa.select(PasswordResetRequest)
            .where(PasswordResetRequest.token_hash == hash_reset_token(token))
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None:
        return None
    if _aware(row.expires_at) <= _now():
        return None
    return row


async def redeem(session: AsyncSession, *, token: str, password: str) -> ConsoleAccount:
    """Canjea el enlace: contraseña nueva, sesiones cerradas, máquinas fuera.

    **Las tres cosas o ninguna** (R3.3). No hay commit aquí —lo hace el
    llamante, que es quien abrió la transacción— por la misma razón por la que
    ``revoke_all_access`` tampoco lo hace: la atomicidad de las tres mitades
    sólo existe si las tres viven en la misma.

    Orden, y no es de estilo:

    1. **El enlace primero.** Un enlace muerto no llega a gastar los ~100 ms de
       scrypt ni a tocar la cuenta.
    2. **La contraseña después**, que valida la política ANTES de escribir: una
       contraseña rechazada no puede quemar el enlace, porque equivocarse
       escribiéndola obligaría a pedir otro correo.
    3. **Sellar el enlace** cuando ya se sabe que la contraseña valía.
    4. **Retirar el acceso** al final, con todo lo demás ya dentro.

    ``set_password`` reinicia los intentos fallidos y levanta el bloqueo (R2.4):
    sin eso se arreglaría la contraseña y se seguiría sin poder entrar.
    """
    row = await _live_request(session, token)
    if row is None:
        raise ResetTokenRejected

    account = await session.get(ConsoleAccount, row.account_id)
    if account is None:  # pragma: no cover - el ON DELETE CASCADE lo impide
        raise ResetTokenRejected

    # Valida la política y lanza ``PasswordPolicyError`` si no la cumple. Va
    # antes de sellar nada: ver el punto 2 de arriba.
    await console_identity.set_password(session, account, password)

    row.used_at = _now()
    await session.flush()

    # D-4: **y las máquinas**. Si alguien pudo entrar en la cuenta, pudo dar de
    # alta una máquina, y una credencial de máquina abre ejecución local —la
    # puerta más peligrosa de las dos—. Dentro de esta misma transacción.
    await principal_access.revoke_all_access(
        session,
        principal_id=account.id,
        reason=REVOKE_REASON,
        actor=f"console:{account.email}",
    )
    return account


async def send_reset_mail(*, email: str, token: str, locale: str = "es") -> bool:
    """El correo con el enlace. Devuelve si salió; **nadie decide nada con eso**.

    ``send_email`` no lanza: devuelve ``False`` tanto si no hay proveedor como
    si el proveedor rechazó. Quien llama registra el fallo y contesta lo mismo
    de siempre — decir «no pudimos enviarlo» revelaría que la cuenta existe
    (R1.3, D-3 de la evaluación).

    **Remitente explícito**: sin él ``send_email`` hereda el de los recibos, y
    un correo para recuperar una cuenta no puede venir de «facturación».
    """
    from nexus_api.config import get_settings
    from nexus_api.services.email import send_email

    settings = get_settings()
    link = f"{settings.console_base_url.rstrip('/')}/reset/{token}"
    if locale == "en":
        subject = "Reset your Auphere password"
        body = (
            "<p>Someone asked to reset the password of this Auphere account. "
            "The link below works <strong>once</strong> and expires in one hour.</p>"
            f'<p><a href="{link}">{link}</a></p>'
            "<p>Resetting also signs you out everywhere and unregisters your "
            "machines: you will sign in again on each one.</p>"
            "<p>If it wasn't you, ignore this message — nothing has changed.</p>"
        )
    else:
        subject = "Restablece tu contraseña de Auphere"
        body = (
            "<p>Alguien ha pedido restablecer la contraseña de esta cuenta de "
            "Auphere. El enlace de abajo sirve <strong>una vez</strong> y caduca "
            "en una hora.</p>"
            f'<p><a href="{link}">{link}</a></p>'
            "<p>Restablecerla cierra además todas tus sesiones y da de baja tus "
            "máquinas: tendrás que volver a entrar en cada una.</p>"
            "<p>Si no has sido tú, ignora este mensaje: no ha cambiado nada.</p>"
        )
    return await send_email(
        to=email, subject=subject, html=body, from_addr=settings.signup_from_email
    )


async def send_changed_notice(*, email: str, locale: str = "es") -> bool:
    """«Tu contraseña ha cambiado» — Requisito 4.

    **Va después de la transacción, y ése es todo su diseño** (R4.4). Si el
    aviso pudiera deshacer el restablecimiento, un proveedor de correo con un
    mal día dejaría a la persona sin entrar **y** sin enterarse, que es lo peor
    de los dos mundos. El fallo del envío es de Auphere y vive en sus
    registros.

    **Sin enlaces, y no es minimalismo** (R4.3). Un aviso sobre tu contraseña
    que trae un enlace entrena a pulsar enlaces dentro de correos sobre tu
    contraseña, que es justo el gesto que un suplantador necesita. Lo único que
    lleva es la hora y una dirección a la que escribir — y escribir a alguien
    no es entrar en ningún sitio.

    Dice **cuándo** en UTC y con la zona escrita. Una hora sin zona no sirve
    para lo único que tiene que servir: que alguien pueda decir «yo a esa hora
    no estaba».
    """
    from nexus_api.config import get_settings
    from nexus_api.services.email import send_email

    settings = get_settings()
    contact = settings.security_contact_email.strip()
    if not contact:
        # En producción no se llega aquí: la guardia de arranque lo impide.
        # En local sí, y entonces el aviso sale igual —R4.1 no admite
        # condiciones— pero el agujero queda dicho en vez de escondido.
        log.warning("password_reset.notice_without_contact")
    when = _now().strftime("%d/%m/%Y %H:%M UTC" if locale != "en" else "%Y-%m-%d %H:%M UTC")
    quien = f'<a href="mailto:{contact}">{contact}</a>' if contact else "Auphere"
    if locale == "en":
        subject = "Your Auphere password was changed"
        body = (
            f"<p>The password of this Auphere account was changed on <strong>{when}</strong>.</p>"
            "<p>Every open session was closed and every registered machine was "
            "unregistered, so you will sign in again on each one.</p>"
            f"<p><strong>If it wasn't you, write to {quien} now.</strong> Whoever "
            "did it can get in with the new password.</p>"
            "<p>This message carries no link on purpose: nothing here signs you "
            "in. Open Auphere the way you normally do.</p>"
        )
    else:
        subject = "Tu contraseña de Auphere ha cambiado"
        body = (
            f"<p>La contraseña de esta cuenta de Auphere cambió el "
            f"<strong>{when}</strong>.</p>"
            "<p>Se cerraron todas las sesiones abiertas y se dieron de baja todas "
            "las máquinas, así que tendrás que volver a entrar en cada una.</p>"
            f"<p><strong>Si no has sido tú, escribe a {quien} ahora mismo.</strong> "
            "Quien lo haya hecho puede entrar con la contraseña nueva.</p>"
            "<p>Este mensaje no lleva ningún enlace a propósito: desde aquí no se "
            "entra a ninguna parte. Abre Auphere como lo haces siempre.</p>"
        )
    return await send_email(
        to=email, subject=subject, html=body, from_addr=settings.signup_from_email
    )


__all__ = [
    "REQUESTS_PER_WINDOW",
    "REQUEST_WINDOW",
    "RESET_TTL",
    "REVOKE_REASON",
    "ResetTokenRejected",
    "create_request",
    "hash_reset_token",
    "invalidate_live_for",
    "redeem",
    "send_changed_notice",
    "send_reset_mail",
]
