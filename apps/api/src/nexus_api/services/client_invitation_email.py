"""El correo de invitación a la consola de un cliente — spec 030 (R1.4).

Va con el enlace completo (``console_base_url`` + ``/invite/{token}``) y dice
de qué negocio es. No lleva el nombre del partner: la persona entra en la
consola de su negocio, y quién se la vende no le cambia nada.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from nexus_api.config import get_settings
from nexus_api.services.email import send_email


async def send_client_invitation(
    *, email: str, client_name: str, accept_path: str, expires_at: datetime
) -> bool:
    settings = get_settings()
    link = f"{settings.console_base_url.rstrip('/')}{accept_path}"
    name = escape(client_name)
    body = (
        f"<p>Te dieron acceso a la consola de <strong>{name}</strong> en Auphere: "
        "ahí ves cómo va tu agente, lo que gasta y, si está activada, la bandeja "
        "de entrada de tus conversaciones.</p>"
        f'<p><a href="{escape(link)}">Crear mi contraseña y entrar</a></p>'
        f"<p>El enlace sirve una vez y caduca el {expires_at:%d/%m/%Y}.</p>"
        "<p>Si no esperabas este correo, ignóralo.</p>"
    )
    return await send_email(
        to=email,
        subject=f"Tu acceso a la consola de {client_name}",
        html=body,
        from_addr=settings.signup_from_email,
    )
