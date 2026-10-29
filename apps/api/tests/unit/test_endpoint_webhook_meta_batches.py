"""Spec 050, requirement 1 — the WhatsApp webhook processes every element.

A batch of N messages, statuses or echoes is N envelopes for the handlers;
one broken element does not stop the rest; a person who writes with only a
BSUID is answered like anyone else; ``warning`` / ``deleted`` statuses are
recognised; an unknown field is acked without data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy import text

from nexus_api.api.webhooks import meta as meta_route
from nexus_api.db.models import MessageStatus

pytestmark = pytest.mark.asyncio

APP_SECRET = "dev-meta-app-secret-change-me"
FIXTURES = Path(__file__).resolve().parents[3] / "channels" / "tests" / "fixtures" / "meta_webhooks"
BUSINESS = "+34600000001"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _signed(payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    return body, {
        "X-Hub-Signature-256": sign_meta_request(APP_SECRET, body),
        "Content-Type": "application/json",
    }


async def _seed(db_session, tenant_id) -> None:
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=BUSINESS,
                status=ChannelStatus.ACTIVE,
                audience_mode="everyone",
                config={"waba_id": "102290129340398", "phone_number_id": "106540352242922"},
            )
        )


async def _entries(fake_redis) -> list[dict[str, str]]:
    raw = await fake_redis.xrange("nexus:inbound:standard", count=100)
    return [
        {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in f.items()
        }
        for _id, f in raw
    ]


async def test_a_batch_of_five_messages_enqueues_five_turns(
    client, db_session, fake_redis, seed_tenants
):
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_load("batch_messages"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200, r.text
    ids = sorted(
        e["provider_message_id"]
        for e in await _entries(fake_redis)
        if e["provider_message_id"].startswith("wamid.BATCH")
    )
    assert ids == [f"wamid.BATCH{i}" for i in range(1, 6)]


async def test_a_batch_of_statuses_reaches_the_handler_once_per_status(
    client, monkeypatch, seed_tenants
):
    seen: list[str] = []

    async def record(payload, **_: Any):
        [status] = payload["entry"][0]["changes"][0]["value"]["statuses"]
        seen.append(status["id"])
        return {"status": "ok"}

    monkeypatch.setattr(meta_route, "_handle_status_callback", record)
    body, headers = _signed(_load("batch_statuses"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200
    assert seen == [f"wamid.OUT{i}" for i in range(1, 6)]


async def test_one_broken_element_does_not_stop_the_rest(client, monkeypatch, seed_tenants):
    seen: list[str] = []

    async def flaky(payload, **_: Any):
        [status] = payload["entry"][0]["changes"][0]["value"]["statuses"]
        if status["id"] == "wamid.OUT2":
            raise RuntimeError("boom")
        seen.append(status["id"])
        return {"status": "ok"}

    monkeypatch.setattr(meta_route, "_handle_status_callback", flaky)
    body, headers = _signed(_load("batch_statuses"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200
    assert seen == ["wamid.OUT1", "wamid.OUT3", "wamid.OUT4", "wamid.OUT5"]


async def test_a_person_with_only_a_bsuid_is_enqueued(client, db_session, fake_redis, seed_tenants):
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_load("message_bsuid_only"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200, r.text
    [entry] = [e for e in await _entries(fake_redis) if e["provider_message_id"] == "wamid.BATCH1"]
    assert entry["user_id"] == "ES.200000000000000002"
    assert entry["customer_bsuid"] == "ES.200000000000000002"
    assert "customer_phone" not in entry
    assert entry["customer_username"] == "@sheena"


async def test_phone_and_bsuid_both_travel(client, db_session, fake_redis, seed_tenants):
    await _seed(db_session, seed_tenants["a"])
    body, headers = _signed(_load("message_phone_and_bsuid"))

    await client.post("/webhook/meta", content=body, headers=headers)

    [entry] = [e for e in await _entries(fake_redis) if e["provider_message_id"] == "wamid.BATCH9"]
    assert entry["user_id"] == "34611000001"
    assert entry["customer_phone"] == "34611000001"
    assert entry["customer_bsuid"] == "ES.100000000000000001"


async def test_warning_deleted_and_played_statuses_are_recognised() -> None:
    # ``played`` (voice note listened to) implies read; ``warning`` and
    # ``deleted`` do not move the message but are recorded.
    assert meta_route._map_status("played") is MessageStatus.READ
    assert frozenset({"warning", "deleted"}) == meta_route.ANNOTATED_STATUSES


async def test_warning_and_deleted_statuses_are_acked(client, seed_tenants):
    body, headers = _signed(_load("status_warning_deleted"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200


async def test_an_unknown_field_is_acked(client, seed_tenants):
    body, headers = _signed(_load("unknown_field"))

    r = await client.post("/webhook/meta", content=body, headers=headers)

    assert r.status_code == 200
    assert r.json()["status"] == "ignored"
