"""Spec 033 — migration 0158 names every entry and starts the monthly cap.

Down to 0157, write the book as it was (kinds read from keys, a balance
written by hand, a spent cap), up to 0158, and check: each entry got its
kind, the hand-written difference became ONE opening entry and the book
balances, every cap starts the monthly regime whole.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from nexus_api.metering.wallet import reconcile_purchased
from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0157_tenant_payments"
_UNDER_TEST = "0158_ledger_kind_and_monthly_cap"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


@pytest.fixture
def at_head_afterwards() -> Any:
    yield
    _alembic("upgrade", "head")


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def test_0158_names_entries_opens_the_book_and_refills_caps(
    console_world, at_head_afterwards
) -> None:
    a = console_world["a"]
    pid, tid = a["partner_id"], a["tenant_id"]
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    # The book as it was: an admin top-up of 5 000, a debit of 1 200 from
    # purchased, an expiry of 300 — and a balance someone wrote by hand.
    for key, qty, bucket in (
        (f"admin_purchased:{uuid.uuid4()}", 5_000, "purchased"),
        (f"channel:{uuid.uuid4().hex[:8]}:purchased", 1_200, "purchased"),
        (f"credit_expired:{pid}:2026-01-01", 300, "purchased"),
        (f"channel:{uuid.uuid4().hex[:8]}:allocation", 999, "included"),
    ):
        await _exec(
            "INSERT INTO usage_ledger (id, partner_id, tenant_id, qty, bucket, idempotency_key) "
            "VALUES (:i, :p, :t, :q, :b, :k)",
            i=uuid.uuid4(),
            p=pid,
            t=tid,
            q=qty,
            b=bucket,
            k=key,
        )
    await _exec(
        "UPDATE partner_wallets SET purchased_remaining = 10000 WHERE partner_id = :p", p=pid
    )
    await _exec(
        "UPDATE partner_allocations SET cap = 8000, remaining = 0 WHERE tenant_id = :t", t=tid
    )

    up = _alembic("upgrade", _UNDER_TEST)
    assert up.returncode == 0, up.stderr

    kinds = dict(
        await _exec(
            "SELECT split_part(idempotency_key, ':', 1), kind FROM usage_ledger "
            "WHERE partner_id = :p AND kind <> 'opening_credit'",
            p=pid,
        )
    )
    assert kinds["admin_purchased"] == "credit_admin"
    assert kinds["credit_expired"] == "expiry"
    assert sorted(
        k
        for (k,) in await _exec(
            "SELECT kind FROM usage_ledger WHERE partner_id = :p AND idempotency_key LIKE 'channel:%'",
            p=pid,
        )
    ) == ["allocation_legacy", "debit"]

    # 10 000 stored minus (5 000 - 1 200 - 300) = 6 500 written by hand: one entry.
    opening = await _exec(
        "SELECT kind, qty FROM usage_ledger WHERE partner_id = :p AND kind LIKE 'opening_%'", p=pid
    )
    assert opening == [("opening_credit", 6_500)]
    rec = await reconcile_purchased(pid)
    assert rec is not None and rec.balanced, rec

    # The monthly regime starts whole.
    (remaining,) = (
        await _exec("SELECT remaining FROM partner_allocations WHERE tenant_id = :t", t=tid)
    )[0]
    assert remaining == 8_000

    # And it is reversible: down removes the opening entry and the column.
    assert _alembic("downgrade", _BEFORE).returncode == 0
    left = await _exec(
        "SELECT count(*) FROM usage_ledger WHERE partner_id = :p AND idempotency_key LIKE 'opening:%'",
        p=pid,
    )
    assert left == [(0,)]
