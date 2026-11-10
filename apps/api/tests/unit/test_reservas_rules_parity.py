"""Spec 056, T035/T037 — los esquemas de la ficha y de Reservas dicen las reglas de ``rules.py``.

La ficha del partner (``api/console/schemas_business_sections.py``) y los Ajustes
de Reservas (``api/console/lite/reservas_schemas.py``) aceptan y rechazan los
mismos servicios (requisito 5.2). Los límites que tienen código propio
(categoría, duración e importe: ``category_too_long``, ``bad_duration``,
``amount_too_large``) los comprueba ``services/business/rules.py`` y responden
``422 {code, field}``; los esquemas los publican en el OpenAPI (lo lee la app) con
los valores de ``rules``, sin una copia que pueda divergir, y no los cortan antes
con un 422 genérico que la consola no sabría explicar (5.6).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from nexus_api.api.console import schemas_business_sections as ficha
from nexus_api.api.console.lite import reservas_schemas as reservas
from nexus_api.services.business import rules


def _prop(model: type[BaseModel], name: str) -> dict[str, Any]:
    schema = model.model_json_schema()
    props: dict[str, Any] = schema["properties"]
    return props[name]


CATEGORY = {"maxLength": rules.CATEGORY_MAX}
DURATION = {
    "minimum": rules.DURATION_MIN,
    "maximum": rules.DURATION_MAX,
    "multipleOf": rules.DURATION_STEP,
}


@pytest.mark.parametrize(
    ("model", "field", "limits"),
    [
        (reservas.ServiceIn, "category", CATEGORY),
        (reservas.ServicePatchIn, "category", CATEGORY),
        (ficha.ServiceIn, "category", CATEGORY),
        (ficha.ServicePatchIn, "category", CATEGORY),
        (reservas.ServiceIn, "duration_minutes", DURATION),
        (reservas.ServicePatchIn, "duration_minutes", DURATION),
        (ficha.ServiceIn, "duration_min", DURATION),
        (ficha.ServicePatchIn, "duration_min", DURATION),
        (ficha.PriceIn, "amount_minor", {"maximum": rules.AMOUNT_MAX_MINOR}),
    ],
)
def test_the_schemas_publish_the_rules_values(
    model: type[BaseModel], field: str, limits: dict[str, int]
) -> None:
    prop = _prop(model, field)
    assert {k: prop.get(k) for k in limits} == limits, prop


def test_reservas_takes_the_ficha_price() -> None:
    assert reservas.ServiceIn.model_fields["price"].annotation is ficha.PriceIn
    assert reservas.ServiceOut.model_fields["price"].annotation is ficha.PriceOut
    # Ni ``price_minor`` ni ``clear_price``: «Gratis» es un tipo de precio, no un importe nulo.
    assert "price_minor" not in reservas.ServicePatchIn.model_fields
    assert "clear_price" not in reservas.ServicePatchIn.model_fields


@pytest.mark.parametrize("model", [reservas.ServiceIn, ficha.ServiceIn])
def test_the_name_has_the_rules_length(model: type[BaseModel]) -> None:
    assert _prop(model, "name")["maxLength"] == rules.NAME_MAX


@pytest.mark.parametrize(
    ("model", "body"),
    [
        (reservas.ServicePatchIn, {"category": "x" * (rules.CATEGORY_MAX + 1)}),
        (reservas.ServicePatchIn, {"duration_minutes": 7}),
        (reservas.ServicePatchIn, {"price": {"kind": "amount", "amount_minor": 10**12 + 1}}),
        (ficha.ServicePatchIn, {"category": "x" * (rules.CATEGORY_MAX + 1)}),
        (ficha.ServicePatchIn, {"price": {"kind": "amount", "amount_minor": 10**12 + 1}}),
    ],
)
def test_the_coded_limits_are_left_to_the_rules(
    model: type[BaseModel], body: dict[str, Any]
) -> None:
    """El esquema no los corta: los corta ``rules`` con su código (5.6)."""
    model.model_validate(body)


def test_a_negative_amount_is_never_a_price() -> None:
    with pytest.raises(ValidationError):
        ficha.PriceIn.model_validate({"kind": "amount", "amount_minor": -1})


@pytest.mark.parametrize("model", [reservas.StaffIn, reservas.StaffPatchIn])
def test_a_staff_email_is_an_email_of_254_at_most(model: type[BaseModel]) -> None:
    """11.3: con formato válido, y 254 caracteres como mucho."""
    base = {"name": "Nora"} if model is reservas.StaffIn else {}
    model.model_validate({**base, "email": "nora@cultor.cl"})
    for bad in ("no-es-un-correo", "a" * 250 + "@x.co"):
        with pytest.raises(ValidationError):
            model.model_validate({**base, "email": bad})
