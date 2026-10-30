"""La comprobación de plantillas — spec 051, R7.1.

La parte que decide es pura (``check_template``): estas pruebas le dan
respuestas de Resend fabricadas y fijan qué cuenta como plantilla rota.
"""

from __future__ import annotations

from typing import Any

from nexus_api.services.email_catalog import CATALOG, EmailKind
from scripts.check_email_templates import check_template

_BUTTON = '<td bgcolor="#00DF81"><a href="{{{RESET_URL}}}">Crear una contraseña nueva</a></td>'


def _template(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "published",
        "has_unpublished_versions": False,
        "variables": [{"key": "RESET_URL", "type": "string"}],
        "html": (
            "<h1>Restablece tu contraseña</h1><p>Hola,</p>"
            f"{_BUTTON}<p>{{{{{{RESET_URL}}}}}}</p><p>Un saludo,<br>El equipo de Auphere</p>"
        ),
    }
    base.update(overrides)
    return base


def _check(template: dict[str, Any] | None, kind: EmailKind = EmailKind.PASSWORD_RESET):
    return check_template(kind, "es", CATALOG[kind], template)


def test_una_plantilla_en_orden_pasa() -> None:
    result = _check(_template())
    assert result.ok, result.problems


def test_una_plantilla_que_no_existe() -> None:
    assert _check(None).problems == ["no existe en Resend"]


def test_sin_publicar() -> None:
    result = _check(_template(status="draft"))
    assert any("no está publicada" in p for p in result.problems)


def test_cambios_sin_publicar_es_un_aviso() -> None:
    result = _check(_template(has_unpublished_versions=True))
    assert result.ok
    assert result.warnings == ["tiene cambios sin publicar"]


def test_una_variable_de_menos() -> None:
    result = _check(_template(variables=[]))
    assert any("le faltan variables" in p and "RESET_URL" in p for p in result.problems)


def test_dos_botones() -> None:
    html = _template()["html"] + _BUTTON
    result = _check(_template(html=html))
    assert "tiene más de un botón de llamada a la acción" in result.problems


def test_una_muletilla() -> None:
    html = _template()["html"] + "<p>No dudes en contactarnos.</p>"
    result = _check(_template(html=html))
    assert "contiene «no dudes en contactarnos»" in result.problems


def test_una_palabra_de_dentro() -> None:
    html = _template()["html"] + "<p>Se darán de baja tus máquinas.</p>"
    result = _check(_template(html=html))
    assert any("máquinas" in p for p in result.problems)


def test_sin_firma() -> None:
    html = _template()["html"].replace("El equipo de Auphere", "Auphere")
    assert "no lleva la firma «El equipo de Auphere»" in _check(_template(html=html)).problems


def test_el_aviso_de_contrasena_no_admite_enlaces_web() -> None:
    template = {
        "status": "published",
        "variables": [
            {"key": "CHANGED_AT", "type": "string"},
            {"key": "SECURITY_CONTACT", "type": "string"},
        ],
        "html": (
            "<p>{{{CHANGED_AT}}}</p>"
            '<a href="mailto:{{{SECURITY_CONTACT}}}">{{{SECURITY_CONTACT}}}</a>'
            '<a href="https://www.auphere.com">auphere.com</a>'
            "<p>El equipo de Auphere</p>"
        ),
    }
    result = _check(template, EmailKind.PASSWORD_CHANGED)
    assert result.problems == ["lleva enlaces que este correo no admite: https://www.auphere.com"]
