"""Spec 033 — the money is exact.

A top-up is one transaction and at most once; it is never spend; every
credit, debit and expiry is in the book and the book balances; a client never
reads more balance than its partner has; the cap refills once per calendar
month; the gate and the charge look at the same pocket.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, PartnerWallet
from nexus_api.db.models.partner_wallet import UsageLedger
from nexus_api.metering.wallet import (
    add_purchased,
    allow_channel_turn,
    credit_burn,
    debit_wallet,
    reconcile_purchased,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

#: 1 US$ = 100 000 credits; 1 cent = 1 000 (billing/pricing.py).
CENT = 1_000


async def _operator(db_session) -> str:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return str(account.id)


async def _set_wallet(partner_id: uuid.UUID, *, purchased: int, included: int = 0) -> None:
    sm = get_sessionmaker()
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        row = await s.get(PartnerWallet, partner_id)
        if row is None:
            row = PartnerWallet(partner_id=partner_id)
            s.add(row)
        row.purchased_remaining = purchased
        row.included_remaining = included
        row.included_expires_at = datetime.now(UTC) + timedelta(days=3)


async def _ledger(partner_id: uuid.UUID) -> list[UsageLedger]:
    sm = get_sessionmaker()
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        return list(
            (await s.execute(sa.select(UsageLedger).where(UsageLedger.partner_id == partner_id)))
            .scalars()
            .all()
        )


# ── R3: the admin top-up ────────────────────────────────────────────────


async def test_a_topup_in_dollars_lands_once_with_its_entry_and_its_audit(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    await _set_wallet(a["partner_id"], purchased=10_000 * CENT)  # US$ 100
    op = await _operator(db_session)
    key = str(uuid.uuid4())
    headers = {**admin_headers, "X-Operator-Id": op}
    url = f"/admin/partners/{a['partner_id']}/wallet/purchased"

    first = await client.post(
        url, headers=headers, json={"amount_cents": 5_000, "idempotency_key": key}
    )
    assert first.status_code == 200, first.text
    assert first.json()["purchased_cents"] == 15_000
    assert first.json()["duplicate"] is False

    # The same key again — a double click, a network retry — credits nothing.
    for _ in range(4):
        again = await client.post(
            url, headers=headers, json={"amount_cents": 5_000, "idempotency_key": key}
        )
        assert again.status_code == 200, again.text
        assert again.json()["purchased_cents"] == 15_000
        assert again.json()["duplicate"] is True

    entries = [e for e in await _ledger(a["partner_id"]) if e.kind == "credit_admin"]
    assert [(e.qty, e.bucket) for e in entries] == [(5_000 * CENT, "purchased")]
    audits = (
        (
            await db_session.execute(
                sa.select(AuditLog).where(AuditLog.action == "wallet.admin_purchased")
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].actor.startswith("operator:op-")
    assert audits[0].after_json["amount_cents"] == 5_000


@pytest.mark.parametrize("amount", [0, -1, 1_000_001])
async def test_an_amount_out_of_range_is_refused(
    client, console_world, admin_headers, db_session, amount
) -> None:
    a = console_world["a"]
    op = await _operator(db_session)
    res = await client.post(
        f"/admin/partners/{a['partner_id']}/wallet/purchased",
        headers={**admin_headers, "X-Operator-Id": op},
        json={"amount_cents": amount, "idempotency_key": str(uuid.uuid4())},
    )
    assert res.status_code == 422


async def test_a_topup_without_an_operator_is_refused(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    res = await client.post(
        f"/admin/partners/{a['partner_id']}/wallet/purchased",
        headers=admin_headers,
        json={"amount_cents": 100, "idempotency_key": str(uuid.uuid4())},
    )
    assert res.status_code == 400


async def test_the_old_qty_body_is_refused(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    op = await _operator(db_session)
    res = await client.post(
        f"/admin/partners/{a['partner_id']}/wallet/purchased",
        headers={**admin_headers, "X-Operator-Id": op},
        json={"qty": 1000},
    )
    assert res.status_code == 422


# ── R2.3: a top-up and an expiry are never spend ───────────────────────


async def test_a_topup_and_an_expiry_are_not_spend(console_world) -> None:
    a = console_world["a"]
    pid, tid = a["partner_id"], a["tenant_id"]
    await _set_wallet(pid, purchased=0)
    since = datetime.now(UTC) - timedelta(minutes=1)
    await add_purchased(
        pid, 900 * CENT, kind="credit_admin", idempotency_key=f"admin_purchased:{pid}:x"
    )
    await add_purchased(pid, 100 * CENT, kind="credit_stripe", idempotency_key="stripe_credit:cs_x")
    sm = get_sessionmaker()
    async with sm() as s, s.begin():
        await apply_partner_to_session(s, pid)
        s.add(
            UsageLedger(
                partner_id=pid,
                qty=5 * CENT,
                bucket="purchased",
                kind="expiry",
                idempotency_key=f"credit_expired:{pid}:x",
            )
        )
    await debit_wallet(
        partner_id=pid,
        tenant_id=tid,
        qty=3 * CENT,
        idempotency_key="channel:t1",
        allow_included=False,
    )

    burn = await credit_burn(pid, [tid], since)
    assert burn.get(None, 0) == 0  # nothing "outside clients"
    assert burn[tid] == 3 * CENT


# ── R2.4: the book balances ─────────────────────────────────────────────


async def test_the_book_balances_after_any_sequence(console_world) -> None:
    a = console_world["a"]
    pid, tid = a["partner_id"], a["tenant_id"]
    await _set_wallet(pid, purchased=0, included=50 * CENT)
    rng = random.Random(33)
    for i in range(60):
        move = rng.choice(["admin", "stripe", "debit", "debit", "debit_included"])
        qty = rng.randint(1, 4_000)
        if move == "admin":
            await add_purchased(
                pid, qty, kind="credit_admin", idempotency_key=f"admin_purchased:{pid}:{i}"
            )
        elif move == "stripe":
            await add_purchased(
                pid, qty, kind="credit_stripe", idempotency_key=f"stripe_credit:cs_{i}"
            )
        elif move == "debit":
            await debit_wallet(
                partner_id=pid,
                tenant_id=tid,
                qty=qty,
                idempotency_key=f"channel:{i}",
                allow_included=False,
            )
        else:
            await debit_wallet(partner_id=pid, qty=qty, idempotency_key=f"companion:{i}")
        # Replays never change the result.
        if rng.random() < 0.2:
            await debit_wallet(
                partner_id=pid,
                tenant_id=tid,
                qty=qty,
                idempotency_key=f"channel:{i}",
                allow_included=False,
            )
    rec = await reconcile_purchased(pid)
    assert rec is not None
    assert rec.balanced, rec


async def test_the_reconciliation_shows_a_hand_edit(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    await _set_wallet(pid, purchased=0)
    await add_purchased(
        pid, 1_000 * CENT, kind="credit_admin", idempotency_key=f"admin_purchased:{pid}:y"
    )
    ok = (await client.get(f"/admin/partners/{pid}/wallet/reconcile", headers=admin_headers)).json()
    assert ok["balanced"] is True
    assert ok["stored_cents"] == 1_000
    # Someone edits the balance by hand: the book says so, to the credit.
    await _set_wallet(pid, purchased=1_000 * CENT + 7)
    off = (
        await client.get(f"/admin/partners/{pid}/wallet/reconcile", headers=admin_headers)
    ).json()
    assert off["balanced"] is False
    assert off["difference_credits"] == 7


# ── R5: the gate looks at the recharged balance ────────────────────────


async def test_with_only_the_weekly_pool_a_client_turn_does_not_open(console_world) -> None:
    """The follow-up of doble-cobro-del-tope: turns passed without being
    charged when only the included pool had balance."""
    a = console_world["a"]
    await _set_wallet(a["partner_id"], purchased=0, included=1_000 * CENT)
    assert await allow_channel_turn(a["tenant_id"]) is False
    await _set_wallet(a["partner_id"], purchased=1 * CENT, included=0)
    assert await allow_channel_turn(a["tenant_id"]) is True


# ── R6.2: a client never reads more than the money there is ───────────


async def test_a_client_balance_never_exceeds_the_partners_recharged_balance() -> None:
    from nexus_api.services.lite_home import balance_of

    # Cap 30 US$, remaining 30 US$, partner has 5 US$: the client reads 5.
    shown = balance_of((3_000 * CENT, 3_000 * CENT), 0, purchased=500 * CENT)
    assert shown.remaining_cents == 500
    assert shown.cap_cents == 3_000
    # Partner richer than the cap: the cap rules.
    assert (
        balance_of((3_000 * CENT, 1_200 * CENT), 0, purchased=9_000 * CENT).remaining_cents == 1_200
    )
    # Partner at zero: zero.
    assert balance_of((3_000 * CENT, 3_000 * CENT), 0, purchased=0).remaining_cents == 0
