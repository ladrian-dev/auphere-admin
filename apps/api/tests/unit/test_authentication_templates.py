"""Spec 077 · R3 — crear plantillas de autenticación con la forma de Meta.

Meta fija el cuerpo de una plantilla de autenticación; solo se eligen el aviso
de seguridad, la caducidad y el texto del botón de copiar código. Mandar un
cuerpo libre (lo que hacían el panel y la consola) es lo que Meta rechaza. Y
Marketing y Utilidad no cambian ni un byte.

Desde el 2026-11-25 (spec 075, requisito 10) el panel y la consola crean con el
mismo ``TemplateCreateIn``: el del panel, con ``components`` u ``otp``, ya no existe.
"""

from __future__ import annotations

import typing

import pytest
from pydantic import ValidationError

from nexus_api.api.admin import whatsapp_templates as admin_routes
from nexus_api.api.console.schemas_channels import TemplateCreateIn as ConsoleTemplateIn
from nexus_api.schemas.whatsapp_authentication import authentication_components


def test_builder_has_metas_shape() -> None:
    assert authentication_components(
        button_text="Copiar código", code_expiration_minutes=10, add_security_recommendation=True
    ) == [
        {"type": "BODY", "add_security_recommendation": True},
        {"type": "FOOTER", "code_expiration_minutes": 10},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copiar código"}],
        },
    ]


def test_builder_without_expiry_has_no_footer() -> None:
    components = authentication_components()
    assert [c["type"] for c in components] == ["BODY", "BUTTONS"]
    assert components[1]["buttons"][0]["text"] == "Copiar código"


@pytest.mark.parametrize("minutes", [0, 91])
def test_builder_rejects_expiry_out_of_range(minutes: int) -> None:
    with pytest.raises(ValueError):
        authentication_components(code_expiration_minutes=minutes)


def test_panel_and_console_create_with_the_same_model() -> None:
    """Spec 075, 10.5 (D7, 2026-11-25): one shape to create, in both screens."""
    from nexus_api.schemas import whatsapp_templates as shared

    hints = typing.get_type_hints(admin_routes.create_whatsapp_template)
    assert hints["body"] is ConsoleTemplateIn
    assert getattr(shared, "TemplateCreateIn", None) is ConsoleTemplateIn
    assert not hasattr(admin_routes, "OtpTemplateIn")


def test_authentication_with_free_text_is_refused() -> None:
    with pytest.raises(ValidationError):
        ConsoleTemplateIn(
            name="tecfin_codigo",
            category="AUTHENTICATION",
            components=[{"type": "BODY", "text": "Tu código es {{1}}"}],
        )


def test_the_panels_old_otp_object_is_refused() -> None:
    with pytest.raises(ValidationError):
        ConsoleTemplateIn(
            name="tecfin_codigo", category="AUTHENTICATION", otp={"button_text": "Copiar"}
        )


def test_console_authentication_needs_no_body() -> None:
    body = ConsoleTemplateIn(
        name="tecfin_codigo",
        category="AUTHENTICATION",
        otp_button_text="Copiar código",
        otp_expiration_minutes=10,
    )
    assert body.to_components() == authentication_components(
        button_text="Copiar código", code_expiration_minutes=10
    )
    assert body.parameter_format() is None


def test_console_utility_still_needs_body() -> None:
    with pytest.raises(ValidationError):
        ConsoleTemplateIn(name="recordatorio", category="UTILITY")


def test_console_utility_is_unchanged() -> None:
    body = ConsoleTemplateIn(
        name="recordatorio",
        category="UTILITY",
        body_text="Hola {{nombre}}",
        examples={"nombre": "Camila"},
    )
    assert body.to_components() == [
        {
            "type": "BODY",
            "text": "Hola {{nombre}}",
            "example": {"body_text_named_params": [{"param_name": "nombre", "example": "Camila"}]},
        }
    ]
    assert body.parameter_format() == "NAMED"
