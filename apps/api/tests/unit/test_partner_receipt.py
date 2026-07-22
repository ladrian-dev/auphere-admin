"""Unit tests for the partner-receipt money math + rendering (DB-free)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from nexus_api.services.partner_receipt import (
    ReceiptLine,
    ReceiptResult,
    commission_cents,
    due_date_for,
    emission_month_start,
    period_bounds,
    subscription_active,
    subscription_cents,
)
from nexus_api.services.partner_receipt_email import receipt_subject, render_receipt_html

pytestmark = [pytest.mark.unit]


class TestCommissionCents:
    def test_converts_clp_commission_to_usd_cents(self) -> None:
        # 924.50 CLP / 932.84 -> 0.99 USD -> 99 cents
        assert commission_cents(Decimal("924.50"), clp_per_usd=Decimal("932.84")) == 99

    def test_sums_are_converted_once_as_a_whole(self) -> None:
        # 1,000,000 CLP / 932.84 -> 1072.00 USD -> 107200 cents
        assert commission_cents(Decimal("1000000"), clp_per_usd=Decimal("932.84")) == 107200

    def test_zero_clp_is_zero_cents(self) -> None:
        assert commission_cents(Decimal("0"), clp_per_usd=Decimal("932.84")) == 0


class TestSubscriptionCents:
    def test_uses_the_plan_price(self) -> None:
        assert subscription_cents(price_override_cents=None, plan_amount_cents=2500) == 2500

    def test_override_wins_over_plan(self) -> None:
        assert subscription_cents(price_override_cents=1900, plan_amount_cents=2500) == 1900

    def test_missing_both_is_zero(self) -> None:
        assert subscription_cents(price_override_cents=None, plan_amount_cents=None) == 0


class TestPeriod:
    def test_bounds_span_the_month(self) -> None:
        start, end = period_bounds(2026, 6)
        assert start == datetime(2026, 6, 1, tzinfo=UTC)
        assert end == datetime(2026, 7, 1, tzinfo=UTC)

    def test_bounds_roll_over_december(self) -> None:
        start, end = period_bounds(2026, 12)
        assert start == datetime(2026, 12, 1, tzinfo=UTC)
        assert end == datetime(2027, 1, 1, tzinfo=UTC)

    def test_due_date_is_the_5th_of_next_month(self) -> None:
        assert due_date_for(2026, 6) == date(2026, 7, 5)

    def test_due_date_rolls_over_december(self) -> None:
        assert due_date_for(2026, 12) == date(2027, 1, 5)

    def test_emission_month_start_is_first_of_next_month(self) -> None:
        assert emission_month_start(2026, 7) == date(2026, 8, 1)

    def test_emission_month_start_rolls_over_december(self) -> None:
        assert emission_month_start(2026, 12) == date(2027, 1, 1)


class TestSubscriptionEffectivity:
    """New Air: $40/mo billed in advance, effective from August 2026.

    First appears on the receipt emitted 2026-08-01 (which covers July).
    """

    EFFECTIVE = date(2026, 8, 1)

    def test_null_effective_is_always_active(self) -> None:
        assert subscription_active(None, date(2020, 1, 1)) is True

    def test_july_receipt_bills_new_air_in_advance_for_august(self) -> None:
        # Receipt for July period is emitted 2026-08-01.
        assert subscription_active(self.EFFECTIVE, emission_month_start(2026, 7)) is True

    def test_june_receipt_does_not_bill_new_air_yet(self) -> None:
        # Receipt for June period is emitted 2026-07-01, before the start.
        assert subscription_active(self.EFFECTIVE, emission_month_start(2026, 6)) is False


def _result() -> ReceiptResult:
    tid = uuid.uuid4()
    return ReceiptResult(
        invoice_id=uuid.uuid4(),
        partner_id=uuid.uuid4(),
        partner_slug="facelad",
        partner_name="Facelad SPA",
        billing_email="contacto@facelad.com",
        period_year=2026,
        period_month=6,
        total_cents=12599,
        currency="USD",
        status="issued",
        clp_per_usd=Decimal("932.84"),
        issued_at=datetime(2026, 7, 1, tzinfo=UTC),
        due_date=date(2026, 7, 5),
        lines=[
            ReceiptLine(
                tid,
                "barbersupply",
                "Barber Supply",
                "commission",
                "Barber Supply — comisión 2,5%",
                10099,
                Decimal("94200"),
            ),
            ReceiptLine(
                uuid.uuid4(),
                "newair",
                "New Air",
                "subscription",
                "New Air — suscripción mensual",
                2500,
            ),
            ReceiptLine(uuid.uuid4(), "vedhome", "Vedhome", "inactive", "Vedhome — sin cargos", 0),
        ],
        created=True,
    )


class TestRendering:
    def test_subject_names_partner_and_period(self) -> None:
        assert receipt_subject(_result()) == "Recibo Junio 2026 — Facelad SPA"

    def test_html_shows_total_due_and_all_lines(self) -> None:
        html = render_receipt_html(_result())
        assert "$125.99" in html  # total
        assert "05/07/2026" in html  # due date
        assert "Barber Supply" in html and "New Air" in html and "Vedhome" in html
        assert "932.84" in html  # FX note

    def test_html_omits_fx_note_when_no_conversion(self) -> None:
        r = _result()
        no_fx = ReceiptResult(**{**r.__dict__, "clp_per_usd": None})
        assert "dólar observado" not in render_receipt_html(no_fx)
