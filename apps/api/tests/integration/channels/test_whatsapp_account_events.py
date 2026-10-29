"""Spec 050, historia 3 — la cuenta avisa antes de romperse (requisitos 4.1 a 4.4,
2.5, 8.4).

De punta a punta: el webhook firmado de Meta llega a ``/webhook/meta`` y la base
queda como pide ``contracts/webhook-events.md``. Las cargas son las de
``channels/tests/fixtures/meta_webhooks``: su WABA es ``102290129340398`` y su
número ``+34600000001``. Un segundo negocio, con otra WABA, nunca cambia.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    ConsoleNotification,
    WhatsAppTemplateStatus,
)

from ..business._business_world import Biz, new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

META_APP_SECRET = "dev-meta-app-secret-change-me"
FIXTURES = Path(__file__).resolve().parents[4] / "channels" / "tests" / "fixtures" / "meta_webhooks"
WABA = "102290129340398"
NUMBER = "+34600000001"
PNID = "106540352242922"

TEMPLATE_EVENTS = [
    "approved",
    "rejected",
    "pending",
    "paused",
    "disabled",
    "pending_deletion",
    "deleted",
    "archived",
    "unarchived",
    "flagged",
    "in_appeal",
    "limit_exceeded",
    "locked",
    "reinstated",
]


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


async def _line(db: AsyncSession, biz: Biz, *, number: str, waba: str, pnid: str) -> uuid.UUID:
    async with tenant_scoped_session(db, biz.tenant_id):
        channel = Channel(
            tenant_id=biz.tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=number,
            config={"phone_number_id": pnid, "waba_id": waba, "mode": "cloud_api"},
            status=ChannelStatus.ACTIVE,
            audience_mode="everyone",
        )
        db.add(channel)
        await db.flush()
        channel_id = channel.id
    await db.commit()
    return channel_id


async def _channel(db: AsyncSession, biz: Biz, channel_id: uuid.UUID) -> Channel:
    async with tenant_scoped_session(db, biz.tenant_id):
        row = await db.get(Channel, channel_id, populate_existing=True)
    assert row is not None
    return row


async def _kinds(db: AsyncSession, biz: Biz) -> list[str]:
    rows = await db.scalars(
        sa.select(ConsoleNotification.kind).where(
            ConsoleNotification.partner_id == biz.partner_id,
            ConsoleNotification.audience == "partner",
        )
    )
    return sorted(rows.all())


async def _template(db: AsyncSession) -> WhatsAppTemplateStatus:
    row = await db.scalar(
        sa.select(WhatsAppTemplateStatus)
        .where(
            WhatsAppTemplateStatus.waba_id == WABA,
            WhatsAppTemplateStatus.template_name == "recordatorio_cita",
        )
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


@pytest.fixture
async def world(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> dict[str, Any]:
    mine = await new_business(client, db_session, console_world, name="Barbería Cultor")
    other = await new_business(client, db_session, console_world, name="Floristería Lis", label="b")
    return {
        "biz": mine,
        "channel": await _line(db_session, mine, number=NUMBER, waba=WABA, pnid=PNID),
        "other": other,
        "other_channel": await _line(
            db_session, other, number="+34600000099", waba="WABA_OTHER", pnid="PN_OTHER"
        ),
    }


# ── plantillas ──────────────────────────────────────────────────────────────


async def test_every_template_state_is_stored_under_the_wabas_business(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    biz: Biz = world["biz"]
    for event in TEMPLATE_EVENTS:
        payload = _load(f"template_status_{event}")
        await _post(client, payload)
        row = await _template(db_session)
        assert row.status == event.upper(), event
        assert row.tenant_id == biz.tenant_id, event
    paused = _load("template_status_paused")["entry"][0]["changes"][0]["value"]
    await _post(client, _load("template_status_paused"))
    row = await _template(db_session)
    assert row.category == paused["message_template_category"]


async def test_a_template_that_can_no_longer_be_sent_warns_and_clears_the_cache(
    client: Any, db_session: AsyncSession, world: dict[str, Any], monkeypatch: Any
) -> None:
    from nexus_api.services import whatsapp_account_events

    cleared: list[str] = []
    monkeypatch.setattr(whatsapp_account_events, "invalidate_template_cache", cleared.append)
    biz: Biz = world["biz"]

    await _post(client, _load("template_status_approved"))
    assert await _kinds(db_session, biz) == []
    for event in ("paused", "disabled", "rejected", "locked", "deleted"):
        await _post(client, _load(f"template_status_{event}"))

    assert sorted(set(await _kinds(db_session, biz))) == [
        "template.disabled",
        "template.paused",
        "template.rejected",
    ]
    assert cleared.count(WABA) >= 6
    assert await _kinds(db_session, world["other"]) == []


async def test_quality_falling_to_yellow_warns(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    await _post(client, _load("template_status_approved"))
    await _post(client, _load("template_quality_yellow"))
    assert (await _template(db_session)).quality == "YELLOW"
    assert await _kinds(db_session, world["biz"]) == ["template.quality_dropped"]


async def test_a_recategorisation_is_announced_then_applied(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    await _post(client, _load("template_status_approved"))
    await _post(client, _load("template_category_impending"))
    row = await _template(db_session)
    assert row.pending_category == "MARKETING"
    await _post(client, _load("template_category_completed"))
    row = await _template(db_session)
    assert (row.category, row.previous_category, row.pending_category) == (
        "MARKETING",
        "UTILITY",
        None,
    )
    notices = (
        await db_session.scalars(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.partner_id == world["biz"].partner_id,
                ConsoleNotification.kind == "template.recategorized",
                ConsoleNotification.audience == "partner",
            )
        )
    ).all()
    assert [n.payload["category"] for n in notices] == ["MARKETING", "MARKETING"]


# ── cuenta ──────────────────────────────────────────────────────────────────


async def test_a_partner_event_with_only_the_waba_reaches_that_wabas_numbers(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    biz: Biz = world["biz"]
    await _post(client, _load("account_update_partner_removed"))
    channel = await _channel(db_session, biz, world["channel"])
    assert (channel.status, channel.problem_reason) == (ChannelStatus.DEGRADED, "auth_expired")
    assert channel.config["problem_source"] == "account"
    other = await _channel(db_session, world["other"], world["other_channel"])
    assert (other.status, other.problem_reason) == (ChannelStatus.ACTIVE, None)

    await _post(client, _load("account_update_reconnected"))
    channel = await _channel(db_session, biz, world["channel"])
    assert (channel.status, channel.problem_reason) == (ChannelStatus.ACTIVE, None)
    assert "problem_source" not in channel.config


async def test_the_pricing_tier_is_kept(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    await _post(client, _load("account_update_pricing_tier"))
    channel = await _channel(db_session, world["biz"], world["channel"])
    assert channel.config["pricing_tier"]["tier"] == "25000001:50000000"
    assert channel.status is ChannelStatus.ACTIVE


async def test_a_critical_active_alert_is_a_problem_an_informative_one_is_not(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    biz: Biz = world["biz"]
    await _post(client, _load("account_alerts_info"))
    channel = await _channel(db_session, biz, world["channel"])
    assert channel.status is ChannelStatus.ACTIVE
    assert [a["type"] for a in channel.config["alerts"]] == ["PROFILE_PICTURE_LOST"]

    await _post(client, _load("account_alerts_critical"))
    channel = await _channel(db_session, biz, world["channel"])
    assert (channel.status, channel.problem_reason) == (ChannelStatus.DEGRADED, "account_alert")
    assert len(channel.config["alerts"]) == 2
    assert "channel.account_alert" in await _kinds(db_session, biz)


async def test_a_rejected_account_review_is_a_problem(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    biz: Biz = world["biz"]
    await _post(client, _load("account_review_rejected"))
    channel = await _channel(db_session, biz, world["channel"])
    assert (channel.status, channel.problem_reason) == (ChannelStatus.DEGRADED, "account_review")
    assert channel.config["account_review"] == "REJECTED"
    assert "channel.account_review" in await _kinds(db_session, biz)


async def test_limits_are_written_from_capability_and_quality_updates(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    biz: Biz = world["biz"]
    await _post(client, _load("business_capability_update"))
    channel = await _channel(db_session, biz, world["channel"])
    assert (channel.config["messaging_limit"], channel.config["max_phone_numbers_per_waba"]) == (
        "TIER_2K",
        25,
    )
    await _post(client, _load("phone_number_quality_update"))
    channel = await _channel(db_session, biz, world["channel"])
    assert channel.config["messaging_limit"] == "TIER_10K"
    other = await _channel(db_session, world["other"], world["other_channel"])
    assert "messaging_limit" not in other.config


async def test_a_rejected_display_name_warns_with_the_reason(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    biz: Biz = world["biz"]
    await _post(client, _load("phone_number_name_rejected"))
    channel = await _channel(db_session, biz, world["channel"])
    assert channel.config["name_decision"] == "REJECTED"
    assert channel.config["requested_name"] == "Barbería Cultor SL"
    assert channel.config["name_rejection_reason"] == "NAME_FORMAT_UNACCEPTABLE"
    notice = await db_session.scalar(
        sa.select(ConsoleNotification).where(
            ConsoleNotification.partner_id == biz.partner_id,
            ConsoleNotification.kind == "channel.name_rejected",
        )
    )
    assert notice is not None and notice.payload["reason"] == "NAME_FORMAT_UNACCEPTABLE"


async def test_the_business_username_is_written(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    await _post(client, _load("business_username_approved"))
    channel = await _channel(db_session, world["biz"], world["channel"])
    assert (channel.config["username"], channel.config["username_status"]) == (
        "barberiacultor",
        "approved",
    )
