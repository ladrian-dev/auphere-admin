"""El correo de invitación a la consola de un cliente — spec 030 (R1.4) y
spec 051 (``client_invite``).

Va con el enlace completo (``console_link`` + ``/invite/{token}``) y dice de qué
negocio es. No lleva el nombre del partner: la persona entra en la consola de
su negocio, y quién se la vende no le cambia nada. Por eso este módulo ni
siquiera lo recibe.

El texto vive en la plantilla de Resend; aquí van el asunto, en el idioma de la
cuenta de la persona si ya tiene una (``send_localized`` lo consulta), y las
tres variables del catálogo. El correo es **del cliente** (garantía 6): quien
llama pasa su ``tenant_id``, que es lo que el registro del envío lleva.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime


async def send_client_invitation(
    *,
    email: str,
    client_name: str,
    accept_path: str,
    expires_at: datetime,
    tenant_id: uuid.UUID,
    client_ref: str | None = None,
) -> bool:
    from nexus_api.services.email import send_localized
    from nexus_api.services.email_catalog import EmailKind, console_link, format_day

    def compose(locale: str) -> tuple[str, Mapping[str, str]]:
        subject = (
            f"Your access to the {client_name} console is ready"
            if locale == "en"
            else f"Ya puedes acceder a la consola de {client_name}"
        )
        return subject, {
            "CLIENT_NAME": client_name,
            "EXPIRES_ON": format_day(expires_at.date(), locale),
            "ACCEPT_URL": console_link(accept_path),
        }

    return await send_localized(
        EmailKind.CLIENT_INVITE,
        to=email,
        compose=compose,
        tenant_id=tenant_id,
        client_ref=client_ref,
    )
