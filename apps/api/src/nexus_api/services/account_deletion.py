"""Pedir que se borre la cuenta — spec 031, R11.4.

Las cuentas de las personas de cliente las crea Auphere desde el admin, así que
el borrado también lo hace una persona de Auphere: aquí solo se avisa. El aviso
va a la dirección de seguridad (``security_contact_email``), que es a la que ya
se escribe por una cuenta comprometida y que producción exige al arrancar.
"""

from __future__ import annotations

import html

import structlog

from nexus_api.config import get_settings
from nexus_api.services.email import send_email

log = structlog.get_logger(__name__)


async def notify_deletion_request(*, email: str, client_name: str) -> bool:
    to = get_settings().security_contact_email.strip()
    if not to:
        log.warning("account_deletion.no_contact", email=email)
        return False
    body = (
        "<p>Una persona de un cliente pidió desde la app Auphere Customers que se "
        "borre su cuenta.</p>"
        f"<p><strong>Cuenta:</strong> {html.escape(email)}<br>"
        f"<strong>Cliente:</strong> {html.escape(client_name)}</p>"
        "<p>Revísalo en el admin (pestaña Acceso del cliente). La petición queda "
        "en la auditoría como <code>client_account.deletion_requested</code>.</p>"
    )
    return await send_email(
        to=to,
        subject=f"Petición de borrado de cuenta: {email}",
        html=body,
        reply_to=email,
    )


__all__ = ["notify_deletion_request"]
