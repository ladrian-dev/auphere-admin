"""Spec 076, requisitos 5.1, 5.2, 5.4, 5.7, 6.2 y 6.4 — reglas puras de los eventos.

- El teléfono se normaliza como dice Meta (solo dígitos, con código de país y
  sin ceros iniciales) y se cifra con SHA-256. El caso de prueba es el de su
  página de parámetros de información del cliente.
- Una reserva con precio es ``Purchase`` con importe; sin precio,
  ``LeadSubmitted`` sin importe. Un pedido es ``OrderCreated``.
- ``event_id`` es estable: ``"{source_kind}:{source_id}:{event_name}"``.
- A Meta, ``value`` va en unidades mayores según la moneda (ISO 4217).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexus_api.services.ad_conversions import (
    booking_event,
    event_id,
    major_value,
    normalize_phone,
    order_minor,
    phone_hash,
)

# ── teléfono (T027) ───────────────────────────────────────────────────────────


def test_metas_own_example() -> None:
    # Meta: «(650)555-1212» de EE. UU. → «16505551212» → este SHA-256.
    assert normalize_phone("+1 (650)555-1212") == "16505551212"
    assert (
        phone_hash("+1 (650)555-1212")
        == "e323ec626319ca94ee8bff2e4c87cf613be6ea19919ed1364124e16807ab3176"
    )


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("+56 9 1111 2222", "56911112222"),
        ("56911112222", "56911112222"),
        ("0056911112222", "56911112222"),
        ("+34-600-111-222", "34600111222"),
        ("tel:+34600111222", "34600111222"),
    ],
)
def test_normalize(raw: str, normalized: str) -> None:
    assert normalize_phone(raw) == normalized


@pytest.mark.parametrize("raw", [None, "", "abc", "+12", "ES.100000000000000001"])
def test_no_phone_no_hash(raw: str | None) -> None:
    # Muy corto para ser un teléfono, o un BSUID: no hay con qué identificar.
    assert phone_hash(raw) is None


# ── qué evento (T028) ─────────────────────────────────────────────────────────


def test_a_booking_with_price_is_a_purchase() -> None:
    assert booking_event(price_minor=15000, currency="CLP") == ("Purchase", 15000, "CLP")


@pytest.mark.parametrize(
    ("price", "currency"), [(None, "CLP"), (None, None), (0, None), (500, None)]
)
def test_without_price_it_is_a_lead(price: int | None, currency: str | None) -> None:
    assert booking_event(price_minor=price, currency=currency) == ("LeadSubmitted", None, None)


def test_a_free_booking_with_currency_is_a_purchase_of_zero() -> None:
    assert booking_event(price_minor=0, currency="EUR") == ("Purchase", 0, "EUR")


def test_event_id_is_stable() -> None:
    assert event_id("reservation", "6f1c", "Purchase") == "reservation:6f1c:Purchase"
    assert event_id("woo_order", "1234", "OrderCreated") == "woo_order:1234:OrderCreated"


@pytest.mark.parametrize(
    ("total", "currency", "minor"),
    [
        ("15000", "CLP", 15000),
        ("12.50", "EUR", 1250),
        ("12.5", "EUR", 1250),
        ("7.125", "KWD", 7125),
    ],
)
def test_order_total_to_minor(total: str, currency: str, minor: int) -> None:
    assert order_minor(total, currency) == minor


@pytest.mark.parametrize("total", ["", "abc", "-5", None])
def test_order_total_garbage(total: str | None) -> None:
    assert order_minor(total, "EUR") is None


@pytest.mark.parametrize(
    ("minor", "currency", "value"),
    [
        (15000, "CLP", Decimal("15000")),
        (1250, "EUR", Decimal("12.50")),
        (7125, "KWD", Decimal("7.125")),
    ],
)
def test_value_to_meta_in_major_units(minor: int, currency: str, value: Decimal) -> None:
    assert major_value(minor, currency) == value
