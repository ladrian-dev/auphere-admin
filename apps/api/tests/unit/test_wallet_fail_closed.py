"""Spec 004 · R4.5 — an unreadable book means zero, never "probably fine".

This property already holds and the spec does not relax it anywhere. The test
exists because the story rewires where the budget is read from, and the easiest
way to break fail-closed is to add a ``try/except`` that returns a default so a
screen stops erroring.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.asyncio]


async def test_unreadable_book_reads_as_zero(monkeypatch) -> None:
    from nexus_api.metering import wallet

    async def _boom(*_a, **_kw):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(wallet, "get_sessionmaker", _boom)
    assert await wallet.read_wallet(uuid.uuid4()) is None
    assert await wallet.companion_wallet_remaining(uuid.uuid4()) == 0


async def test_unreadable_book_closes_the_channel(monkeypatch) -> None:
    from nexus_api.metering import wallet

    async def _boom(*_a, **_kw):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(wallet, "get_sessionmaker", _boom)
    assert await wallet.allow_channel_turn(uuid.uuid4()) is False


async def test_unreadable_book_closes_the_allocation_read(monkeypatch) -> None:
    from nexus_api.metering import wallet

    async def _boom(*_a, **_kw):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(wallet, "get_sessionmaker", _boom)
    assert await wallet.companion_allocation_remaining(uuid.uuid4(), uuid.uuid4()) == 0
