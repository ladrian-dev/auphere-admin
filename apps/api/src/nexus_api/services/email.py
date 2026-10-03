"""Minimal transactional-email sender (Resend HTTP API).

Deliberately tiny: one ``send_email`` coroutine. When no real API key is
configured (``NEXUS_RESEND_API_KEY`` unset or still the dev placeholder) it
logs a warning and returns ``False`` instead of raising — callers treat email
as best-effort so a missing key never blocks the work that produced the mail
(e.g. the monthly receipt is still generated and shown in the panel).

El repliegue SMTP (spec 011, D-4)
---------------------------------
Se enciende **sólo** cuando no hay clave de Resend **y** sí hay
``NEXUS_SMTP_URL``. En producción hay clave y no hay ``SMTP_URL``, así que el
camino de producción no cambia ni un byte; en local apunta al Mailhog que lleva
en ``docker-compose.yml`` sin conectar a nada desde que se eligió Resend.

Existe porque CE-006 pide poder recorrer el circuito de recuperar la contraseña
**entero y en local**, y un enlace de un solo uso que nadie puede leer no se
recorre. La alternativa —escribir el enlace en los registros en desarrollo— se
rechazó en el plan: es la salida fácil y es cómo un secreto acaba en producción.

``smtplib`` es de la biblioteca estándar: **ninguna dependencia nueva**. Es
síncrona, así que va a un hilo, igual que hace ``console_identity`` con scrypt.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse

import httpx
import structlog

from nexus_api.config import get_settings

log = structlog.get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_S = 20.0
_SMTP_TIMEOUT_S = 10.0


def _smtp_send(
    *,
    url: str,
    from_addr: str,
    recipients: list[str],
    subject: str,
    html: str,
    reply_to: str | None,
) -> None:
    """Un envío por SMTP, síncrono. Lanza; quien llama lo traduce a ``False``."""
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to
    # Sin alternativa en texto plano a propósito: el sumidero local enseña el
    # HTML tal cual, y fabricar aquí una segunda versión del cuerpo sería
    # mantener dos plantillas de las que sólo una se mira.
    message.set_content(html, subtype="html")

    parsed = urlparse(url)
    with smtplib.SMTP(
        parsed.hostname or "localhost", parsed.port or 25, timeout=_SMTP_TIMEOUT_S
    ) as smtp:
        smtp.send_message(message)


async def send_email(
    *,
    to: str | list[str],
    subject: str,
    html: str,
    from_addr: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Send an HTML email. Returns True on a 2xx, False otherwise (never raises)."""
    settings = get_settings()
    recipients = [to] if isinstance(to, str) else list(to)
    sender = from_addr or settings.receipt_from_email
    if not settings.email_enabled:
        # D-4: el sumidero local, y sólo ahí. Sin proveedor **y** con
        # ``SMTP_URL`` puesta, que es una combinación que producción no tiene.
        if settings.smtp_url:
            try:
                await asyncio.to_thread(
                    _smtp_send,
                    url=settings.smtp_url,
                    from_addr=sender,
                    recipients=recipients,
                    subject=subject,
                    html=html,
                    reply_to=reply_to,
                )
            except OSError as exc:
                # Mismo contrato que el camino de Resend: **no lanza**. Un
                # sumidero local apagado no puede reventar el trabajo que
                # produjo el correo.
                log.error("email.smtp_error", error=str(exc), to=recipients)
                return False
            log.info("email.sent_smtp", to=recipients, subject=subject)
            return True
        log.warning("email.not_configured", to=recipients, subject=subject)
        return False

    payload: dict[str, object] = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        if resp.status_code >= 300:
            log.error(
                "email.send_failed", status=resp.status_code, body=resp.text[:500], to=recipients
            )
            return False
    except httpx.HTTPError as exc:
        log.error("email.send_error", error=str(exc), to=recipients)
        return False

    log.info("email.sent", to=recipients, subject=subject)
    return True
