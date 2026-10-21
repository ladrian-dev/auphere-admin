"""Consumo ilimitado de un cliente de partner (owner, 2026-10-20).

Encendido desde el Admin: el agente no se para por saldo ni por tope y el
turno se anota como ``absorbed`` — medido, pero sin tocar el saldo del
partner ni el tope del cliente. El partner lo ve en su consola, solo lectura.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nexus_api.db.models import AuditLog, PartnerAllocation, PartnerWallet, Tenant, UsageLedger
from nexus_api.metering.wallet import allow_channel_turn, quota_state, reconcile_purchased
from nexus_api.services import operator_identity

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TURN_QTY = 2_000
ROWS: list[dict[str, Any]] = [{"meter": "llm.input_tokens", "source": "channel", "agent_id": None}]


@pytest.fixture
def consumer(monkeypatch: pytest.MonkeyPatch):
    from nexus_worker.metering import consumer as module

    turn = f"turn-{uuid.uuid4().hex[:8]}"

    async def _no_catalog() -> list[Any]:
        return []

    monkeypatch.setattr(module, "_turn_quota", lambda rows, weights: {turn: TURN_QTY})
    monkeypatch.setattr(module, "get_catalog", _no_catalog)
    monkeypatch.setattr(module, "lane_weights_from", lambda catalog: {})
    module._partner_of.clear()
    module.TURN = turn  # type: ignore[attr-defined]
    yield module
    module._partner_of.clear()


async def _op(db_session, admin_headers) -> dict[str, str]:
    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id)}


async def _setup(db_session, w: dict[str, Any], *, purchased: int, cap: int) -> None:
    values = {
        "included_remaining": 0,
        "included_expires_at": datetime.now(UTC) + timedelta(days=20),
        "purchased_remaining": purchased,
    }
    await db_session.execute(
        pg_insert(PartnerWallet)
        .values(partner_id=w["partner_id"], **values)
        .on_conflict_do_update(index_elements=[PartnerWallet.partner_id], set_=values)
    )
    await db_session.execute(
        sa.update(PartnerAllocation)
        .where(PartnerAllocation.tenant_id == w["tenant_id"])
        .values(cap=cap, remaining=cap)
    )
    await db_session.commit()


async def _figures(db_session, w: dict[str, Any]) -> tuple[int, int]:
    purchased = await db_session.scalar(
        sa.select(PartnerWallet.purchased_remaining).where(
            PartnerWallet.partner_id == w["partner_id"]
        )
    )
    remaining = await db_session.scalar(
        sa.select(PartnerAllocation.remaining).where(PartnerAllocation.tenant_id == w["tenant_id"])
    )
    return int(purchased), int(remaining)


async def test_the_switch_opens_the_gate_and_the_turn_is_absorbed(
    client, console_world, admin_headers, db_session, consumer
) -> None:
    w = console_world["a"]
    tid = w["tenant_id"]
    url = f"/admin/tenants/{tid}/consumption"
    # No balance and the cap spent: the agent is stopped.
    await _setup(db_session, w, purchased=0, cap=0)
    assert await allow_channel_turn(tid) is False
    assert (await quota_state(w["partner_id"], [tid]))[tid] is True

    # Only an identified operator can change it.
    assert (
        await client.put(url, headers=admin_headers, json={"unlimited": True})
    ).status_code == 400
    headers = await _op(db_session, admin_headers)
    on = await client.put(url, headers=headers, json={"unlimited": True})
    assert on.status_code == 200, on.text
    assert on.json()["unlimited"] is True
    assert on.json()["absorbed_month_cents"] == 0

    assert await allow_channel_turn(tid) is True
    assert (await quota_state(w["partner_id"], [tid]))[tid] is False

    await consumer._debit_channel_wallet(tid, ROWS)
    # Nothing moved for the partner: not the balance, not the cap.
    assert await _figures(db_session, w) == (0, 0)
    entries = (
        await db_session.execute(
            sa.select(UsageLedger.kind, UsageLedger.qty, UsageLedger.idempotency_key).where(
                UsageLedger.tenant_id == tid
            )
        )
    ).all()
    assert [(k, int(q), key) for k, q, key in entries] == [
        ("absorbed", TURN_QTY, f"channel:{consumer.TURN}:absorbed")
    ]
    # The same turn again, as absorbed or as a debit, writes nothing more.
    await consumer._debit_channel_wallet(tid, ROWS)
    assert (
        len(
            (
                await db_session.execute(
                    sa.select(UsageLedger.id).where(UsageLedger.tenant_id == tid)
                )
            ).all()
        )
        == 1
    )
    rec = await reconcile_purchased(w["partner_id"])
    assert rec is not None and rec.balanced, rec

    seen = await client.get(url, headers=admin_headers)
    assert seen.json()["absorbed_month_cents"] == 2  # 2 000 credits = 2 cents

    audit = (
        await db_session.execute(
            sa.select(AuditLog).where(AuditLog.action == "client_consumption.unlimited_on")
        )
    ).scalar_one()
    assert audit.tenant_id == tid
    assert audit.actor.startswith("operator:")

    # The partner sees it, read-only.
    listed = await client.get("/console/clients", headers=w["headers"]())
    row = next(c for c in listed.json()["items"] if c["external_client_ref"] == w["ref"])
    assert row["unlimited_consumption"] is True

    # Off again: the gate reads the balance and the cap again.
    off = await client.put(url, headers=headers, json={"unlimited": False})
    assert off.json()["unlimited"] is False
    assert await allow_channel_turn(tid) is False
    # Same value twice writes one audit row per real change.
    await client.put(url, headers=headers, json={"unlimited": False})
    offs = (
        await db_session.execute(
            sa.select(AuditLog.id).where(AuditLog.action == "client_consumption.unlimited_off")
        )
    ).all()
    assert len(offs) == 1


async def test_a_direct_client_has_nothing_to_lift(client, admin_headers, db_session) -> None:
    tenant = Tenant(name="Directo", slug=f"directo-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.commit()
    headers = await _op(db_session, admin_headers)
    res = await client.put(
        f"/admin/tenants/{tenant.id}/consumption", headers=headers, json={"unlimited": True}
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "no_partner"
    missing = await client.get(f"/admin/tenants/{uuid.uuid4()}/consumption", headers=admin_headers)
    assert missing.status_code == 404
