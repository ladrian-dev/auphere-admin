"""El catálogo cerrado de correos — spec 051, R2 y R6.

Cada correo que envía la plataforma es un tipo con nombre, con su plantilla en
Resend, su remitente y sus variables. Estas pruebas fijan las reglas que
Resend impone (formato y tope de las claves, nombres reservados) y las que
pusimos nosotros (quién sale de facturación, qué correo no puede llevar
enlaces).
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from nexus_api.config import get_settings
from nexus_api.services.email_catalog import (
    CATALOG,
    MAX_VARIABLE_CHARS,
    ROLE_LABELS,
    EmailKind,
    EmailLines,
    console_link,
    email_locale,
    format_day_en,
    format_day_es,
    format_month_en,
    format_month_es,
    lines_variable,
)

_RESERVED = {"FIRST_NAME", "LAST_NAME", "EMAIL", "UNSUBSCRIBE_URL", "RESEND_UNSUBSCRIBE_URL"}
_ALIAS = re.compile(r"^auphere-[a-z0-9-]+-(es|en)$")
_KEY = re.compile(r"^[A-Z0-9_]{1,50}$")
#: Todo correo externo sale en el idioma de la cuenta de quien lo recibe; el
#: interno lo lee el equipo de Auphere y va solo en español.
_BILINGUAL = set(EmailKind) - {EmailKind.INTERNAL_ALERT}


def test_cada_tipo_tiene_ficha() -> None:
    assert set(CATALOG) == set(EmailKind)


@pytest.mark.parametrize("kind", list(EmailKind))
def test_alias_por_idioma(kind: EmailKind) -> None:
    spec = CATALOG[kind]
    assert "es" in spec.aliases
    assert ("en" in spec.aliases) is (kind in _BILINGUAL)
    for locale, alias in spec.aliases.items():
        assert _ALIAS.match(alias), alias
        assert alias.endswith(f"-{locale}")


def test_los_alias_no_se_repiten() -> None:
    aliases = [a for spec in CATALOG.values() for a in spec.aliases.values()]
    assert len(aliases) == len(set(aliases))


@pytest.mark.parametrize("kind", list(EmailKind))
def test_variables_validas_para_resend(kind: EmailKind) -> None:
    spec = CATALOG[kind]
    assert 0 < len(spec.variables) <= 50
    for key in spec.variables:
        assert _KEY.match(key), key
        assert key not in _RESERVED, key
    assert spec.link_variables <= spec.variables


def test_el_aviso_de_contrasena_no_lleva_enlaces() -> None:
    """Spec 011, R4.3: un correo sobre tu contraseña que trae un enlace
    entrena a pulsar enlaces en correos sobre tu contraseña."""
    spec = CATALOG[EmailKind.PASSWORD_CHANGED]
    assert spec.links_allowed is False
    assert spec.link_variables == frozenset()
    assert [k for k in CATALOG if not CATALOG[k].links_allowed] == [EmailKind.PASSWORD_CHANGED]


def test_solo_los_cobros_salen_de_facturacion() -> None:
    billing = {k for k, spec in CATALOG.items() if spec.sender == "billing"}
    assert billing == {EmailKind.RECEIPT, EmailKind.CHARGE_CONFIRM}


def test_los_dos_correos_del_alta_comparten_remitente() -> None:
    """Spec 006: remitentes distintos delatarían cuál de los dos te tocó."""
    assert CATALOG[EmailKind.SIGNUP_LINK].sender == CATALOG[EmailKind.SIGNUP_EXISTING].sender


def test_las_fechas_se_escriben_como_una_persona() -> None:
    assert format_day_es(date(2026, 11, 6)) == "6 de noviembre de 2026"
    assert format_day_en(date(2026, 11, 6)) == "November 6, 2026"
    assert format_month_es(2026, 10) == "octubre de 2026"
    assert format_month_en(2026, 10) == "October 2026"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("en", "en"),
        ("en-US", "en"),
        ("EN", "en"),
        ("es", "es"),
        ("pt", "es"),
        (None, "es"),
        ("", "es"),
    ],
)
def test_el_idioma_sale_de_la_cuenta(value: str | None, expected: str) -> None:
    """Inglés solo si la cuenta lo pide. El alta hacía lo contrario: todo lo
    que no fuera ``es`` salía en inglés."""
    assert email_locale(value) == expected


def test_los_roles_se_llaman_como_en_la_consola() -> None:
    assert ROLE_LABELS["es"]["admin"] == "Administrador"
    assert ROLE_LABELS["en"]["admin"] == "Admin"
    assert set(ROLE_LABELS["es"]) == set(ROLE_LABELS["en"])


def test_los_enlaces_son_absolutos() -> None:
    """R2.6: la invitación al equipo llevaba una ruta relativa en ``<code>``."""
    base = get_settings().console_base_url.rstrip("/")
    assert console_link("/invite/tok") == f"{base}/invite/tok"
    assert console_link("inbox?c=1") == f"{base}/inbox?c=1"


def test_las_lineas_se_escapan_una_a_una() -> None:
    value = lines_variable(["Barber <b>Supply</b> — US$1", "New & Air — US$2"])
    assert isinstance(value, EmailLines)
    assert value == "Barber &lt;b&gt;Supply&lt;/b&gt; — US$1<br>New &amp; Air — US$2"


def test_las_lineas_que_no_caben_se_cuentan() -> None:
    lines = [f"Cliente {i:03d} — suscripción mensual — US$125.99" for i in range(200)]
    value = lines_variable(lines, more=lambda n: f"y {n} conceptos más")
    assert len(value) <= MAX_VARIABLE_CHARS
    shown = value.count("<br>")  # la última línea es la de «y N más»
    assert value.endswith(f"y {200 - shown} conceptos más")


def test_las_lineas_que_caben_no_se_tocan() -> None:
    assert lines_variable(["a", "b"], more=lambda n: f"y {n} más") == "a<br>b"


def test_los_correos_de_acceso_son_seis() -> None:
    """Los que staging envía de verdad: los que alguien necesita para seguir."""
    access = {k for k, spec in CATALOG.items() if spec.access}
    assert access == {
        EmailKind.SIGNUP_LINK,
        EmailKind.SIGNUP_EXISTING,
        EmailKind.TEAM_INVITE,
        EmailKind.CLIENT_INVITE,
        EmailKind.PASSWORD_RESET,
        EmailKind.PASSWORD_CHANGED,
    }
