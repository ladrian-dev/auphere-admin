"""Plantillas de autenticación de WhatsApp — spec 077, requisito 3.

La forma en que Meta crea una plantilla de autenticación con botón de copiar
código. Vive aparte, sin dependencias, porque la usan el esquema de la consola y
el endpoint del panel, y ninguno de los dos debe arrastrar el cliente de Meta.
"""

from __future__ import annotations

from typing import Any

#: Spec 077: what an authentication template's copy-code button says when the
#: operator does not change it (Meta's own default is a localized "Copy code").
DEFAULT_OTP_BUTTON_TEXT = "Copiar código"
OTP_BUTTON_TEXT_MAX = 25
OTP_EXPIRATION_RANGE = (1, 90)


def authentication_components(
    *,
    button_text: str = DEFAULT_OTP_BUTTON_TEXT,
    code_expiration_minutes: int | None = None,
    add_security_recommendation: bool = True,
) -> list[dict[str, Any]]:
    """Spec 077 (R3.2): the ``components`` Meta expects to CREATE an
    authentication template with a copy-code button.

    The body text is Meta's, fixed ("*{{1}}* es tu código de verificación…"):
    only the security line, the expiry footer and the button label are ours.
    Shared by the operator panel and the partner console so both send the same
    shape; a free-text body is what Meta rejects.
    """
    text = button_text.strip() or DEFAULT_OTP_BUTTON_TEXT
    if len(text) > OTP_BUTTON_TEXT_MAX:
        raise ValueError(f"the button text is at most {OTP_BUTTON_TEXT_MAX} characters")
    components: list[dict[str, Any]] = [
        {"type": "BODY", "add_security_recommendation": bool(add_security_recommendation)}
    ]
    if code_expiration_minutes is not None:
        low, high = OTP_EXPIRATION_RANGE
        if not low <= code_expiration_minutes <= high:
            raise ValueError(f"the code expiry is {low} to {high} minutes")
        components.append({"type": "FOOTER", "code_expiration_minutes": code_expiration_minutes})
    components.append(
        {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": text}]}
    )
    return components
