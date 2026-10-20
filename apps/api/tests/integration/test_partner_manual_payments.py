"""A partner's payment outside Stripe credits its balance (owner, 2026-10-20).

The partner pays Auphere, not its client: recording the payment in the
partner's Facturas credits its recharged balance once; voiding it takes the
credit back, unless the partner already spent it.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.billing.pricing import CREDITS_PER_CENT
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, PartnerWallet, UsageLedger
from nexus_api.metering.wallet import reconcile_purchased
from nexus_api.services import operator_identity

pytestmark = pytest.mark.asyncio


async def _op(db_session, admin_headers) -> dict[str, str]:
    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id)}


def _body(tenant_id: uuid.UUID, **extra: object) -> dict[str, object]:
    return {
        "tenant_id": str(tenant_id),
        "period_year": 2026,
        "period_month": 10,
        "amount_cents": 7500,
        "method": "crypto",
        "paid_on": "2026-10-10",
        "reference": "Binance",
        **extra,
    }


async def _purchased(partner_id: uuid.UUID) -> int:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        w = await s.get(PartnerWallet, partner_id)
        return int(w.purchased_remaining) if w else 0


async def _set_purchased(partner_id: uuid.UUID, credits: int) -> None:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        await s.execute(
            sa.update(PartnerWallet)
            .where(PartnerWallet.partner_id == partner_id)
            .values(purchased_remaining=credits)
        )


async def test_recording_a_payment_credits_the_partner_once_and_the_book_balances(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    start = await _purchased(pid)
    headers = await _op(db_session, admin_headers)
    url = f"/admin/partners/{pid}/payments"

    made = await client.post(url, headers=headers, json=_body(a["tenant_id"]))
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["credited_cents"] == 7500
    assert body["client_name"] == "Client A One"
    assert await _purchased(pid) == start + 7500 * CREDITS_PER_CENT

    # One entry of the new kind, keyed by the payment.
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        kinds = (
            await s.scalars(
                sa.select(UsageLedger.kind).where(
                    UsageLedger.idempotency_key == f"tenant_payment:{body['id']}"
                )
            )
        ).all()
    assert kinds == ["credit_manual"]

    rec = await reconcile_purchased(pid)
    assert rec is not None and rec.balanced, rec

    listed = await client.get(url, headers=admin_headers)
    assert [p["id"] for p in listed.json()] == [body["id"]]

    # The same month twice is a conflict, and credits nothing more.
    again = await client.post(url, headers=headers, json=_body(a["tenant_id"]))
    assert again.status_code == 409
    assert await _purchased(pid) == start + 7500 * CREDITS_PER_CENT

    # Retrying the credit of a credited payment does nothing.
    retry = await client.post(f"{url}/{body['id']}/credit", headers=headers)
    assert retry.status_code == 409
    assert await _purchased(pid) == start + 7500 * CREDITS_PER_CENT

    audit = (
        await db_session.execute(
            sa.select(AuditLog).where(
                AuditLog.action == "wallet.admin_purchased",
                AuditLog.target == f"partner:{pid}",
            )
        )
    ).scalar_one()
    assert audit.after_json["amount_cents"] == 7500
    assert audit.actor.startswith("operator:")


async def test_voiding_takes_the_credit_back_unless_it_was_spent(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    await _set_purchased(pid, 0)
    headers = await _op(db_session, admin_headers)
    url = f"/admin/partners/{pid}/payments"

    first = (await client.post(url, headers=headers, json=_body(a["tenant_id"]))).json()
    assert await _purchased(pid) == 7500 * CREDITS_PER_CENT
    voided = await client.post(f"{url}/{first['id']}/void", headers=headers)
    assert voided.status_code == 200, voided.text
    assert voided.json()["voided_at"] is not None
    assert await _purchased(pid) == 0
    rec = await reconcile_purchased(pid)
    assert rec is not None and rec.balanced, rec
    reversed_row = (
        await db_session.execute(
            sa.select(AuditLog).where(AuditLog.action == "wallet.payment_reversed")
        )
    ).scalar_one()
    assert reversed_row.after_json["amount_cents"] == 7500

    # The month is free again; this time the partner spends part of it.
    second = (await client.post(url, headers=headers, json=_body(a["tenant_id"]))).json()
    await _set_purchased(pid, 1000 * CREDITS_PER_CENT)  # spent 65 US$ of the 75
    refused = await client.post(f"{url}/{second['id']}/void", headers=headers)
    assert refused.status_code == 409
    assert "gastó" in refused.json()["detail"]
    still = await client.get(url, headers=admin_headers)
    live = next(p for p in still.json() if p["id"] == second["id"])
    assert live["voided_at"] is None
    assert await _purchased(pid) == 1000 * CREDITS_PER_CENT


async def test_another_partner_cannot_record_or_void_for_this_client(
    client, console_world, admin_headers, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    headers = await _op(db_session, admin_headers)
    wrong_client = await client.post(
        f"/admin/partners/{b['partner_id']}/payments", headers=headers, json=_body(a["tenant_id"])
    )
    assert wrong_client.status_code == 404

    made = (
        await client.post(
            f"/admin/partners/{a['partner_id']}/payments",
            headers=headers,
            json=_body(a["tenant_id"]),
        )
    ).json()
    cross = await client.post(
        f"/admin/partners/{b['partner_id']}/payments/{made['id']}/void", headers=headers
    )
    assert cross.status_code == 404

    anon = await client.post(
        f"/admin/partners/{a['partner_id']}/payments",
        headers=admin_headers,
        json=_body(a["tenant_id"], period_month=11),
    )
    assert anon.status_code == 400
