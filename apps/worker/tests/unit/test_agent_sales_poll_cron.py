"""Unit tests for the agent-sales poll's pure decision/compute logic.

The money-sensitive bits: only WhatsApp-tagged orders count, commission is
2.5% of the paid total, and a refund zeroes it on re-poll.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from nexus_worker.streams.agent_sales_poll_cron import (
    DEFAULT_COMMISSION_RATE,
    _is_whatsapp_order,
    _parse_dt,
    _sale_row,
)

pytestmark = [pytest.mark.unit]

_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _order(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 3908,
        "number": "3908",
        "status": "completed",
        "currency": "CLP",
        "total": "36980",
        "date_paid_gmt": "2026-07-21T14:00:00",
        "billing": {"phone": "+56912345678"},
        "meta_data": [{"key": "_auphere_source", "value": "whatsapp"}],
    }
    base.update(over)
    return base


class TestWhatsAppDetection:
    def test_detects_the_wa_mark(self) -> None:
        assert _is_whatsapp_order(_order()) is True

    def test_ignores_orders_without_the_mark(self) -> None:
        assert _is_whatsapp_order(_order(meta_data=[])) is False
        assert _is_whatsapp_order(_order(meta_data=[{"key": "other", "value": "x"}])) is False
        assert (
            _is_whatsapp_order(_order(meta_data=[{"key": "_auphere_source", "value": "web"}]))
            is False
        )


class TestCommission:
    def test_commission_is_2_5_percent_of_paid_total(self) -> None:
        row = _sale_row(_order(total="36980"), tenant_id=_TENANT, rate=DEFAULT_COMMISSION_RATE)
        assert row is not None
        assert row["gross_amount"] == Decimal("36980.00")
        assert row["commission_rate"] == Decimal("0.025")
        assert row["commission_amount"] == Decimal("924.50")  # 36980 * 0.025
        assert row["wc_status"] == "completed"

    def test_processing_counts_as_paid(self) -> None:
        row = _sale_row(
            _order(status="processing", total="1000"), tenant_id=_TENANT, rate=Decimal("0.025")
        )
        assert row is not None and row["commission_amount"] == Decimal("25.00")

    @pytest.mark.parametrize("status", ["refunded", "cancelled", "pending", "on-hold", "failed"])
    def test_unpaid_states_accrue_zero_commission(self, status: str) -> None:
        row = _sale_row(
            _order(status=status, total="36980"), tenant_id=_TENANT, rate=Decimal("0.025")
        )
        assert row is not None
        # gross is still captured, but nothing is owed until money is collected.
        assert row["commission_amount"] == Decimal("0.00")
        assert row["wc_status"] == status[:20]

    def test_keeps_store_currency_not_converted(self) -> None:
        row = _sale_row(_order(currency="CLP"), tenant_id=_TENANT, rate=DEFAULT_COMMISSION_RATE)
        assert row is not None and row["currency"] == "CLP"


class TestCashOnDeliveryDate:
    """COD / pickup orders never get a date_paid from WooCommerce. Without a
    fallback the receipt (which buckets by date_paid) would never bill them."""

    def test_falls_back_to_completed_date_when_paid_without_date_paid(self) -> None:
        row = _sale_row(
            _order(date_paid_gmt=None, date_completed_gmt="2026-07-21T18:00:00"),
            tenant_id=_TENANT,
            rate=DEFAULT_COMMISSION_RATE,
        )
        assert row is not None and row["date_paid"] is not None
        assert row["date_paid"].day == 21

    def test_falls_back_to_created_date_when_nothing_else(self) -> None:
        row = _sale_row(
            _order(status="processing", date_paid_gmt=None, date_created_gmt="2026-07-20T10:00:00"),
            tenant_id=_TENANT,
            rate=DEFAULT_COMMISSION_RATE,
        )
        assert row is not None and row["date_paid"] is not None
        assert row["date_paid"].day == 20
        # and the commission is still charged — the money was collected
        assert row["commission_amount"] > 0

    def test_unpaid_orders_keep_a_null_date(self) -> None:
        row = _sale_row(
            _order(status="pending", date_paid_gmt=None, date_created_gmt="2026-07-20T10:00:00"),
            tenant_id=_TENANT,
            rate=DEFAULT_COMMISSION_RATE,
        )
        assert row is not None and row["date_paid"] is None

    def test_real_date_paid_still_wins(self) -> None:
        row = _sale_row(
            _order(date_paid_gmt="2026-07-15T12:00:00", date_created_gmt="2026-07-01T10:00:00"),
            tenant_id=_TENANT,
            rate=DEFAULT_COMMISSION_RATE,
        )
        assert row is not None and row["date_paid"] is not None
        assert row["date_paid"].day == 15


class TestHelpers:
    def test_parse_dt_adds_utc_when_naive(self) -> None:
        dt = _parse_dt("2026-07-21T14:00:00")
        assert dt is not None and dt.tzinfo is not None

    @pytest.mark.parametrize("value", [None, "", "not-a-date"])
    def test_parse_dt_returns_none_on_junk(self, value: str | None) -> None:
        assert _parse_dt(value) is None

    def test_missing_order_id_is_skipped(self) -> None:
        assert _sale_row({"total": "100"}, tenant_id=_TENANT, rate=DEFAULT_COMMISSION_RATE) is None
