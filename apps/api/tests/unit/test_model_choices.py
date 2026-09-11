"""La etiqueta de coste del formulario (spec 003, R2.1).

Función pura: precios → etiquetas. Se prueba aparte de la ruta porque lo que
puede salir mal aquí no es el JSON, es la comparación — y un empate mal
resuelto convierte «todos cuestan igual» en «este es el barato».
"""

from __future__ import annotations

from decimal import Decimal

from nexus_api.services.model_choices import (
    COST_HIGH,
    COST_LOW,
    COST_MID,
    COST_UNKNOWN,
    cost_labels,
)


def test_the_cheapest_and_the_dearest_are_named_and_the_rest_is_middle() -> None:
    labels = cost_labels({"a": Decimal("1.00"), "b": Decimal("5.00"), "c": Decimal("30.00")})
    assert labels == {"a": COST_LOW, "b": COST_MID, "c": COST_HIGH}


def test_a_tie_is_not_a_difference() -> None:
    """Tres modelos al mismo precio: ninguno es «el barato»."""
    same = Decimal("3.00")
    assert cost_labels({"a": same, "b": same}) == {"a": COST_MID, "b": COST_MID}


def test_a_model_with_no_price_is_unknown_not_free() -> None:
    """``NULL`` en ``model_profiles`` es «no sabemos costarlo». Valorarlo a
    cero lo pintaría como el más barato de la lista, que es la mentira que la
    tarifa nula existe para evitar."""
    labels = cost_labels({"a": None, "b": Decimal("2.00"), "c": Decimal("9.00")})
    assert labels["a"] == COST_UNKNOWN
    assert labels["b"] == COST_LOW and labels["c"] == COST_HIGH


def test_with_nothing_priced_nobody_is_compared() -> None:
    assert cost_labels({"a": None, "b": None}) == {"a": COST_UNKNOWN, "b": COST_UNKNOWN}


def test_the_only_model_priced_is_not_declared_cheap() -> None:
    """Uno solo con tarifa no tiene con qué compararse: es un empate de uno."""
    assert cost_labels({"a": Decimal("4.00"), "b": None}) == {"a": COST_MID, "b": COST_UNKNOWN}


def test_an_empty_offer_says_nothing() -> None:
    assert cost_labels({}) == {}
