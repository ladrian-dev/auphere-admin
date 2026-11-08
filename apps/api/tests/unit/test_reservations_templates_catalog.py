"""Spec 043, requisito 15 — el catálogo de las seis plantillas de Reservas.

Lo que el outbox manda a Meta con cada plantilla tiene que ser **exactamente**
lo que su texto pide (15.8): una variable de más o de menos y Meta rechaza el
envío. Hasta esta enmienda, ``reserva_hueco_libre`` no decía ``{{nombre}}`` y
el outbox lo mandaba igual.

Y el texto libre (dentro de la ventana de 24 h) dice lo mismo que la plantilla.
"""

from __future__ import annotations

import re

import pytest

from nexus_api.services.reservations import automation, templates

VARS = {
    "nombre": "Ana",
    "negocio": "La Fonda",
    "cuando": "el jueves 23 a las 20:30",
    "detalle": "4 comensales",
    "minutos": "15",
}
VAR = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")

SPECS = {t.name: t for t in templates.CATALOG}


def test_the_catalog_is_the_six_the_outbox_uses() -> None:
    used = {t for t in automation.TEMPLATES.values() if t is not None}
    assert set(SPECS) == used
    assert len(templates.CATALOG) == 6
    names = tuple(t.name for t in templates.CATALOG)
    assert names == templates.NAMES


@pytest.mark.parametrize("name", sorted(SPECS))
def test_language_category_and_named_variables(name: str) -> None:
    spec = SPECS[name]
    payload = spec.create_payload()
    assert payload["name"] == name
    assert payload["language"] == "es"
    assert payload["category"] == "UTILITY"
    assert payload["parameter_format"] == "NAMED"
    [body] = [c for c in payload["components"] if c["type"] == "BODY"]
    assert body["text"] == spec.body
    examples = body["example"]["body_text_named_params"]
    # Una muestra por variable, en el orden en que aparecen, ninguna vacía.
    assert [e["param_name"] for e in examples] == list(spec.variables)
    assert all(e["example"].strip() for e in examples)


@pytest.mark.parametrize("name", sorted(SPECS))
def test_the_outbox_sends_exactly_the_variables_of_the_text(name: str) -> None:
    """15.8: ni una de más ni una de menos, en el orden del texto."""
    spec = SPECS[name]
    in_text = tuple(dict.fromkeys(VAR.findall(spec.body)))
    assert spec.variables == in_text
    assert automation.TEMPLATE_VARIABLES[name] == in_text
    for kind, template in automation.TEMPLATES.items():
        if template != name:
            continue
        notice = automation.Notice(
            kind=kind,
            template=template,
            variables=dict(VARS),
            text="",
            reservation=None,
            phone=None,
            customer_id=None,
            conversation_id=None,
        )
        assert tuple(notice.template_body()) == in_text


@pytest.mark.parametrize("name", sorted(SPECS))
def test_meta_accepts_the_shape(name: str) -> None:
    """Lo que Meta rechaza sin mirar más: un cuerpo que empieza o acaba en una
    variable, dos variables seguidas, o más de 1024 caracteres."""
    body = SPECS[name].body
    assert not body.lstrip().startswith("{{")
    assert not body.rstrip().endswith("}}")
    assert not re.search(r"\}\}\s*\{\{", body)
    assert len(body) <= 1024


def test_the_offer_greets_by_name() -> None:
    """15.8: el aviso del hueco libre empieza saludando, como los otros cinco."""
    assert SPECS["reserva_hueco_libre"].body.startswith("Hola, {{nombre}}.")
    assert automation.render_text("offer", VARS).startswith("Hola, Ana.")


@pytest.mark.parametrize("kind", sorted(k for k, t in automation.TEMPLATES.items() if t))
def test_the_in_window_text_is_the_template(kind: str) -> None:
    """Dentro de la ventana sale el mismo mensaje que fuera, como texto."""
    spec = SPECS[automation.TEMPLATES[kind] or ""]
    assert automation.TEXTS[kind] == VAR.sub(r"{\1}", spec.body)
