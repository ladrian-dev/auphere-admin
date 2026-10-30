"""Pedir que se borre la cuenta — spec 031, R11.4.

Las cuentas de las personas de cliente las crea Auphere desde el admin, así que
el borrado también lo hace una persona de Auphere: aquí solo se avisa. El aviso
va a la dirección de seguridad (``security_contact_email``), que es a la que ya
se escribe por una cuenta comprometida y que producción exige al arrancar.

Spec 051 (catálogo §20): sale por ``internal_alert``, en español. Es el único
correo cuya respuesta no va a soporte: responder le escribe a la persona que lo
pidió, como antes.
"""

from __future__ import annotations

import structlog

from nexus_api.config import get_settings
from nexus_api.services.email_catalog import EmailKind, lines_variable

log = structlog.get_logger(__name__)


async def notify_deletion_request(*, email: str, client_name: str) -> bool:
    from nexus_api.services.email import send_template

    to = get_settings().security_contact_email.strip()
    if not to:
        log.warning("account_deletion.no_contact", email=email)
        return False
    detail = lines_variable(
        [
            f"Cuenta: {email}",
            f"Cliente: {client_name}",
            "Dónde revisarlo: admin, pestaña Acceso del cliente",
            "Acción de auditoría: client_account.deletion_requested",
        ]
    )
    return await send_template(
        EmailKind.INTERNAL_ALERT,
        to=to,
        subject=f"[Auphere] Petición de borrado de cuenta: {email}",
        variables={
            "HEADING": "Una persona pide borrar su cuenta de Auphere Customers",
            "DETAIL": detail,
            "KIND": "client_account.deletion_requested",
        },
        locale="es",
        reply_to=email,
    )


__all__ = ["notify_deletion_request"]
