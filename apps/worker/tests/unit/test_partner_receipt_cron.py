"""Unit tests for the partner-receipt cron: its period logic and its email."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from nexus_api.services.email_catalog import EmailKind
from nexus_api.services.partner_receipt import ReceiptLine, ReceiptResult
from nexus_api.services.partner_receipt_email import receipt_email

from nexus_worker.streams.partner_receipt_cron import _mail_receipt, _previous_month

pytestmark = [pytest.mark.unit]


class TestPreviousMonth:
    def test_mid_year(self) -> None:
        assert _previous_month(date(2026, 7, 1)) == (2026, 6)

    def test_january_rolls_to_december(self) -> None:
        assert _previous_month(date(2026, 1, 1)) == (2025, 12)

    def test_march(self) -> None:
        assert _previous_month(date(2026, 3, 1)) == (2026, 2)


def _receipt() -> ReceiptResult:
    return ReceiptResult(
        invoice_id=uuid.uuid4(),
        partner_id=uuid.uuid4(),
        partner_slug="facelad",
        partner_name="Facelad SPA",
        billing_email="contacto@facelad.com",
        period_year=2026,
        period_month=9,
        total_cents=2500,
        currency="USD",
        status="issued",
        clp_per_usd=None,
        issued_at=datetime(2026, 10, 1, tzinfo=UTC),
        due_date=date(2026, 10, 5),
        lines=[
            ReceiptLine(
                uuid.uuid4(),
                "newair",
                "New Air",
                "subscription",
                "New Air — suscripción mensual",
                2500,
            )
        ],
        created=True,
    )


class TestMailReceipt:
    """Spec 051: the cron mails the ``receipt`` template in the partner's name."""

    async def test_sends_the_receipt_template_to_billing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []

        async def _fake(kind: EmailKind, **kw: Any) -> bool:
            calls.append({"kind": kind, **kw})
            return True

        monkeypatch.setattr("nexus_api.services.email.send_localized", _fake)
        r = _receipt()
        await _mail_receipt(r)
        assert len(calls) == 1
        call = calls[0]
        assert call["kind"] is EmailKind.RECEIPT
        assert call["to"] == "contacto@facelad.com"
        assert call["partner_id"] == r.partner_id
        subject, variables = call["compose"]("es")
        assert subject == "Tu recibo de septiembre de 2026 (Facelad SPA)"
        assert (subject, variables) == receipt_email(r, "es")
        assert call["compose"]("en")[0] == "Your Auphere receipt for September 2026 (Facelad SPA)"
