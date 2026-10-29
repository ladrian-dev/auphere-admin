"""Spec 050, historia 4 — una baja se respeta siempre (requisitos 5.1 a 5.5, CE-005).

- Meta's ``user_preferences`` ``stop`` is an opt-out of marketing by the
  person (with or without a phone); ``resume`` lifts it and leaves a trace.
- A stop word is an opt-out of marketing too, and the message reaches the
  Inbox, marked, without a turn of the agent.
- A marketing opt-out blocks broadcasts and MARKETING templates; a UTILITY
  one still goes. A row from before spec 050 (``scope='all'``) blocks all.
- The operator lifts a stop word's opt-out with a reason; Meta's answers 409.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Customer,
    Message,
    WhatsAppOptOut,
)
from nexus_api.services import whatsapp_opt_outs

from ..business._business_world import Biz

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

META_APP_SECRET = "dev-meta-app-secret-change-me"
FIXTURES = Path(__file__).resolve().parents[4] / "channels" / "tests" / "fixtures" / "meta_webhooks"
NUMBER = "+34600000001"
PHONE = "34611000001"
BSUID = "ES.100000000000000001"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


async def _post(client: Any, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode()
    resp = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
    )
    assert resp.status_code == 200, resp.text


async def _rows(db: AsyncSession, biz: Biz) -> list[WhatsAppOptOut]:
    async with tenant_scoped_session(db, biz.tenant_id):
        rows = (
            await db.scalars(
                sa.select(WhatsAppOptOut)
                .order_by(WhatsAppOptOut.opted_out_at)
                .execution_options(populate_existing=True)
            )
        ).all()
    return list(rows)


@pytest.fixture
async def line(db_session: AsyncSession, biz: Biz) -> uuid.UUID:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = Channel(
            tenant_id=biz.tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=NUMBER,
            config={"phone_number_id": "106540352242922", "waba_id": "102290129340398"},
            status=ChannelStatus.ACTIVE,
            audience_mode="everyone",
        )
        db_session.add(channel)
        await db_session.flush()
        channel_id = channel.id
    await db_session.commit()
    return channel_id


async def _customer(db: AsyncSession, biz: Biz, **kw: Any) -> uuid.UUID:
    async with tenant_scoped_session(db, biz.tenant_id):
        row = Customer(tenant_id=biz.tenant_id, **kw)
        db.add(row)
        await db.flush()
        customer_id = row.id
    await db.commit()
    return customer_id


# ── Meta's user_preferences ──────────────────────────────────────────────────


async def test_meta_stop_is_an_opt_out_of_marketing_by_the_person(
    client: Any, db_session: AsyncSession, biz: Biz, line: uuid.UUID
) -> None:
    customer_id = await _customer(db_session, biz, identifier=PHONE, phone=PHONE, bsuid=BSUID)
    await _post(client, _load("user_preferences_stop"))
    await _post(client, _load("user_preferences_stop"))  # Meta retries: one row
    [row] = await _rows(db_session, biz)
    assert (row.scope, row.source, row.customer_id) == ("marketing", "meta", customer_id)
    assert row.opted_in_at is None


async def test_meta_stop_without_a_phone_finds_the_person_by_bsuid(
    client: Any, db_session: AsyncSession, biz: Biz, line: uuid.UUID
) -> None:
    customer_id = await _customer(db_session, biz, identifier=BSUID, bsuid=BSUID)
    payload = copy.deepcopy(_load("user_preferences_stop"))
    pref = payload["entry"][0]["changes"][0]["value"]["user_preferences"][0]
    del pref["wa_id"]
    await _post(client, payload)
    [row] = await _rows(db_session, biz)
    assert (row.customer_id, row.recipient_phone) == (customer_id, None)


async def test_meta_resume_lifts_it_and_leaves_a_trace(
    client: Any, db_session: AsyncSession, biz: Biz, line: uuid.UUID
) -> None:
    await _customer(db_session, biz, identifier=PHONE, phone=PHONE, bsuid=BSUID)
    await _post(client, _load("user_preferences_stop"))
    await _post(client, _load("user_preferences_resume"))
    [row] = await _rows(db_session, biz)
    assert row.opted_in_at is not None and row.lifted_by == "meta"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        actions = (
            await db_session.scalars(
                sa.select(AuditLog.action).where(AuditLog.target == f"opt_out:{row.id}")
            )
        ).all()
    assert sorted(actions) == ["customer.opt_out.lifted", "customer.opt_out.recorded"]
    # And the person can stop again later: the row comes back to life.
    await _post(client, _load("user_preferences_stop"))
    [again] = await _rows(db_session, biz)
    assert again.id == row.id and again.opted_in_at is None


# ── the stop word ────────────────────────────────────────────────────────────


async def test_a_stop_word_is_marketing_and_reaches_the_inbox_without_a_turn(
    client: Any, db_session: AsyncSession, biz: Biz, line: uuid.UUID, fake_redis: Any
) -> None:
    from nexus_worker.runtime.dispatcher import InboundEvent, accept_inbound

    payload = copy.deepcopy(_load("message_phone_and_bsuid"))
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message["text"] = {"body": "BAJA"}
    message["id"] = "wamid.BAJA1"
    await _post(client, payload)

    [row] = await _rows(db_session, biz)
    assert (row.scope, row.source, row.recipient_phone) == ("marketing", "keyword", PHONE)
    raw = await fake_redis.xrange("nexus:inbound:standard", count=100)
    entries = [
        {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in f.items()
        }
        for _id, f in raw
    ]
    [entry] = [e for e in entries if e["provider_message_id"] == "wamid.BAJA1"]
    assert entry["opted_out"] == "true" and "mark_read" not in entry

    accepted = await accept_inbound(
        InboundEvent(
            tenant_id=biz.tenant_id,
            channel_id=line,
            user_id=PHONE,
            content="BAJA",
            customer_phone=PHONE,
            customer_bsuid=BSUID,
            provider_message_id="wamid.BAJA1",
            opted_out=True,
        )
    )
    assert accepted.no_turn and accepted.message_id is not None
    async with tenant_scoped_session(db_session, biz.tenant_id):
        msg = await db_session.get(Message, accepted.message_id)
        assert msg is not None and msg.skipped_reason == "opted_out"
    [row] = await _rows(db_session, biz)
    assert row.customer_id is not None  # the worker tied it to the person


# ── what an opt-out blocks ───────────────────────────────────────────────────


async def test_marketing_is_blocked_utility_goes_and_an_old_row_blocks_all(
    db_session: AsyncSession, biz: Biz, line: uuid.UUID
) -> None:
    from nexus_worker.streams.outbound import _is_marketing

    customer_id = await _customer(db_session, biz, identifier=PHONE, phone=PHONE)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await whatsapp_opt_outs.record(
            db_session,
            tenant_id=biz.tenant_id,
            channel_id=line,
            customer_id=customer_id,
            phone=PHONE,
            scope="marketing",
            source="meta",
            reason="user_request",
            actor="meta",
        )

        async def blocks(marketing: bool, **who: Any) -> bool:
            return await whatsapp_opt_outs.blocks(
                db_session, channel_id=line, marketing=marketing, **who
            )

        assert await blocks(True, customer_id=customer_id)
        assert not await blocks(False, customer_id=customer_id)
        assert await blocks(True, phone=f"+{PHONE}")

        # A pre-050 row: scope 'all' blocks a reply too.
        db_session.add(
            WhatsAppOptOut(
                tenant_id=biz.tenant_id,
                channel_id=line,
                recipient_phone="34622000002",
                scope="all",
                source="keyword",
                reason="keyword_stop",
                opted_out_at=datetime.now(UTC),
            )
        )
        await db_session.flush()
        assert await blocks(False, phone="34622000002")

        def msg(payload: dict[str, Any] | None) -> Message:
            return Message(template_payload=payload)

        cfg = {"waba_id": "102290129340398"}
        assert await _is_marketing(db_session, msg({"name": "x", "broadcast": True}), cfg)
        assert await _is_marketing(db_session, msg({"name": "x", "category": "MARKETING"}), cfg)
        assert not await _is_marketing(db_session, msg({"name": "x", "category": "UTILITY"}), cfg)
        assert not await _is_marketing(db_session, msg(None), cfg)


# ── the operator ─────────────────────────────────────────────────────────────


async def test_the_operator_lifts_a_stop_word_with_a_reason_never_metas(
    client: Any, db_session: AsyncSession, biz: Biz, line: uuid.UUID, admin_headers: Any
) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        keyword = await whatsapp_opt_outs.record(
            db_session,
            tenant_id=biz.tenant_id,
            channel_id=line,
            customer_id=None,
            phone="34633000003",
            scope="marketing",
            source="keyword",
            reason="keyword_stop",
            actor="customer",
        )
        meta = await whatsapp_opt_outs.record(
            db_session,
            tenant_id=biz.tenant_id,
            channel_id=line,
            customer_id=None,
            phone="34644000004",
            scope="marketing",
            source="meta",
            reason="user_request",
            actor="meta",
        )
        assert keyword is not None and meta is not None
        keyword_id, meta_id = keyword.id, meta.id
    await db_session.commit()
    base = f"/admin/tenants/{biz.tenant_id}/opt-outs"

    listed = await client.get(base, headers=admin_headers)
    assert listed.status_code == 200, listed.text
    by_id = {r["id"]: r for r in listed.json()}
    assert by_id[str(keyword_id)]["liftable"] is True
    assert by_id[str(meta_id)]["liftable"] is False

    no_reason = await client.post(
        f"{base}/{keyword_id}/lift", json={"reason": ""}, headers=admin_headers
    )
    assert no_reason.status_code == 422
    lifted = await client.post(
        f"{base}/{keyword_id}/lift", json={"reason": "Lo pidió por teléfono"}, headers=admin_headers
    )
    assert lifted.status_code == 200, lifted.text
    assert lifted.json()["opted_in_at"] is not None
    refused = await client.post(
        f"{base}/{meta_id}/lift", json={"reason": "Lo pidió por teléfono"}, headers=admin_headers
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == "lifted_by_person_only"
