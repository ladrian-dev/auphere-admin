"""A client's monthly fee paid outside the provider: recorded, never acted on."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog
from nexus_api.services import operator_identity

pytestmark = pytest.mark.asyncio


async def _operator_headers(db_session, admin_headers: dict[str, str]) -> dict[str, str]:
    async with db_session.begin():
        account = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(account.id)}


def _body(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "period_year": 2026,
        "period_month": 10,
        "amount_cents": 7500,
        "method": "transfer",
        "reference": "OP-889123",
        "paid_on": "2026-10-08",
    }
    payload.update(extra)
    return payload


async def test_a_payment_is_recorded_listed_and_audited_by_the_operator(
    client, admin_headers, seed_tenants, db_session
) -> None:
    headers = await _operator_headers(db_session, admin_headers)
    url = f"/admin/tenants/{seed_tenants['a']}/payments"

    created = await client.post(url, headers=headers, json=_body(note="  "))
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["amount_cents"] == 7500
    assert row["currency"] == "USD"
    assert row["note"] is None
    assert row["recorded_by"].endswith("@auphere.test")
    assert row["voided_at"] is None

    listed = await client.get(url, headers=admin_headers)
    assert [p["id"] for p in listed.json()] == [row["id"]]

    # The other client's list stays empty, and the month view names only A.
    other = await client.get(f"/admin/tenants/{seed_tenants['b']}/payments", headers=admin_headers)
    assert other.json() == []
    period = await client.get("/admin/tenant-payments?year=2026&month=10", headers=admin_headers)
    assert [p["tenant_id"] for p in period.json()] == [str(seed_tenants["a"])]

    audit = (
        await db_session.execute(
            sa.select(AuditLog).where(AuditLog.action == "tenant_payment.recorded")
        )
    ).scalar_one()
    assert audit.tenant_id == seed_tenants["a"]
    assert audit.actor.startswith("operator:ops-")
    assert audit.after_json["amount_cents"] == 7500


async def test_a_month_holds_one_live_payment_until_it_is_voided(
    client, admin_headers, seed_tenants, db_session
) -> None:
    headers = await _operator_headers(db_session, admin_headers)
    url = f"/admin/tenants/{seed_tenants['a']}/payments"

    first = await client.post(url, headers=headers, json=_body())
    assert first.status_code == 201, first.text
    again = await client.post(url, headers=headers, json=_body(amount_cents=9000))
    assert again.status_code == 409, again.text

    voided = await client.post(f"{url}/{first.json()['id']}/void", headers=headers)
    assert voided.status_code == 200, voided.text
    assert voided.json()["voided_by"].endswith("@auphere.test")
    twice = await client.post(f"{url}/{first.json()['id']}/void", headers=headers)
    assert twice.status_code == 409

    # The month is free again, and the voided row is still on the record.
    redo = await client.post(url, headers=headers, json=_body(amount_cents=9000))
    assert redo.status_code == 201, redo.text
    listed = (await client.get(url, headers=admin_headers)).json()
    assert len(listed) == 2
    period = await client.get("/admin/tenant-payments?year=2026&month=10", headers=admin_headers)
    assert [p["amount_cents"] for p in period.json()] == [9000]


async def test_a_payment_of_another_client_cannot_be_voided_through_this_one(
    client, admin_headers, seed_tenants, db_session
) -> None:
    headers = await _operator_headers(db_session, admin_headers)
    created = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/payments", headers=headers, json=_body()
    )
    r = await client.post(
        f"/admin/tenants/{seed_tenants['b']}/payments/{created.json()['id']}/void",
        headers=headers,
    )
    assert r.status_code == 404


async def test_recording_needs_an_operator_and_a_sane_body(
    client, admin_headers, seed_tenants, db_session
) -> None:
    url = f"/admin/tenants/{seed_tenants['a']}/payments"
    assert (await client.post(url, headers=admin_headers, json=_body())).status_code == 400
    assert (await client.post(url, json=_body())).status_code == 401

    headers = await _operator_headers(db_session, admin_headers)
    for bad in ({"amount_cents": 0}, {"period_month": 13}, {"method": "barter"}):
        r = await client.post(url, headers=headers, json=_body(**bad))
        assert r.status_code == 422, (bad, r.text)
    missing = await client.post(
        f"/admin/tenants/{uuid.uuid4()}/payments", headers=headers, json=_body()
    )
    assert missing.status_code == 404
