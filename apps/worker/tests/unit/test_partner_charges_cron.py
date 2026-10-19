"""Spec 041 — the charges cron: nothing without Stripe keys; the settlement decides its days."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from nexus_worker.streams import partner_charges_cron as cron

pytestmark = pytest.mark.asyncio
_MADRID = ZoneInfo("Europe/Madrid")


class _Settings:
    def __init__(self, enabled: bool) -> None:
        self.billing_enabled = enabled


async def test_closed_billing_charges_nobody(monkeypatch) -> None:
    calls: list[str] = []

    async def recharge() -> list:
        calls.append("recharge")
        return []

    monkeypatch.setattr(cron, "get_settings", lambda: _Settings(False))
    monkeypatch.setattr(cron, "run_auto_recharges", recharge)
    await cron.tick(datetime(2026, 11, 1, 8, tzinfo=_MADRID))
    assert calls == []


async def test_every_tick_tops_up_and_lets_the_settlement_decide(monkeypatch) -> None:
    calls: list[str] = []

    async def recharge() -> list:
        calls.append("recharge")
        return []

    async def settle(now) -> list:
        calls.append(f"settle:{now:%Y-%m-%d}")
        return []

    monkeypatch.setattr(cron, "get_settings", lambda: _Settings(True))
    monkeypatch.setattr(cron, "run_auto_recharges", recharge)
    monkeypatch.setattr(cron, "run_postpaid_settlement", settle)
    await cron.tick(datetime(2026, 11, 2, 8, tzinfo=_MADRID))
    await cron.tick(datetime(2026, 11, 1, 8, tzinfo=_MADRID))
    assert calls == ["recharge", "settle:2026-11-02", "recharge", "settle:2026-11-01"]
