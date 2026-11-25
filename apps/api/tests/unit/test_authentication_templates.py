"""Spec 077 · R3 — crear plantillas de autenticación con la forma de Meta.

Meta fija el cuerpo de una plantilla de autenticación; solo se eligen el aviso
de seguridad, la caducidad y el texto del botón de copiar código. Mandar un
cuerpo libre (lo que hacían el panel y la consola) es lo que Meta rechaza. Y
Marketing y Utilidad no cambian ni un byte.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexus_api.api.admin.whatsapp_templates import TemplateCreateIn as AdminTemplateIn
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


def test_admin_authentication_is_built_from_otp() -> None:
    body = AdminTemplateIn(
        name="tecfin_codigo",
        category="authentication",
        otp={"button_text": "Copiar", "code_expiration_minutes": 5},
    )
    components = body.final_components()
    assert components[0] == {"type": "BODY", "add_security_recommendation": True}
    assert components[-1]["buttons"][0]["otp_type"] == "COPY_CODE"


def test_admin_authentication_with_free_text_is_refused() -> None:
    with pytest.raises(ValidationError):
        AdminTemplateIn(
            name="tecfin_codigo",
            category="AUTHENTICATION",
            components=[{"type": "BODY", "text": "Tu código es {{1}}"}],
        )


def test_admin_utility_is_unchanged() -> None:
    components = [{"type": "BODY", "text": "Hola {{nombre}}"}]
    body = AdminTemplateIn(name="recordatorio", category="UTILITY", components=components)
    assert body.final_components() == components


def test_admin_utility_without_components_is_refused() -> None:
    with pytest.raises(ValidationError):
        AdminTemplateIn(name="recordatorio", category="UTILITY")


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
