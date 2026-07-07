"""Integration tests for Phase 2 owner-backchannel slash commands.

Exercises the dispatch path end-to-end through ``/webhook/meta`` against
a real Postgres + RLS scope: a signed Cloud API payload whose
``metadata.phone_number_id`` matches a registered ``auphere_owner_channels``
row is routed into ``nexus_api.services.owner_channel_flow.handle_owner_inbound``.
``_send_owner_reply`` is monkeypatched to a recorder so we never reach
the Meta Graph API but can still assert the exact ack texts.

Each test seeds the minimum graph (tenant + channel + customer +
conversation + owner_phone_index + open consultation) needed to land on
the dispatch branch, posts the webhook, and asserts on:

- the JSON status the webhook returns,
- the side effect on the DB row (consultation status, agent_active,
  tenant.status),
- the reply message the owner would have received (when applicable),
- the fanout XADD when a consultation is answered.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuphereOwnerChannel,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    OwnerConsultation,
    OwnerPhoneIndex,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_api.services.owner_channel_flow import OWNER_FANOUT_STREAM

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

META_APP_SECRET = "dev-meta-app-secret-change-me"
OWNER_PHONE_NUMBER_ID = "PNOWNER1"


@pytest.fixture
def reply_recorder(monkeypatch) -> list[dict[str, Any]]:
    """Swap ``_send_owner_reply`` for a recorder. Returns the list of
    replies so tests can assert what the owner would have received."""
    import nexus_api.services.owner_channel_flow as flow

    sent: list[dict[str, Any]] = []

    async def _record(*, channel: Any, to_phone: str, text: str) -> None:
        sent.append(
            {
                "channel": channel.display_name,
                "to_phone": to_phone,
                "text": text,
            }
        )

    monkeypatch.setattr(flow, "_send_owner_reply", _record)
    return sent


async def _seed_full_backchannel(
    db_session: Any,
    *,
    owner_phone: str = "+56999111222",
) -> dict[str, Any]:
    """Set up a tenant + channel + Auphere number + open consultation
    that the webhook can route a slash command into."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name=f"slash-{tenant_id.hex[:6]}",
            slug=f"slash-{tenant_id.hex[:6]}",
            plan=TenantPlan.INTERNAL,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()

    db_session.add(
        AuphereOwnerChannel(
            phone_e164="+56222000001",
            display_name="slash-test",
            provider="meta",
            provider_phone_id=OWNER_PHONE_NUMBER_ID,
            is_default=True,
            active=True,
        )
    )
    business_channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"biz-{tenant_id.hex[:6]}",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(business_channel)
    await db_session.commit()
    await db_session.refresh(business_channel)

    customer = Customer(
        tenant_id=tenant_id,
        identifier="+56987654321",
        preferences={},
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)

    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=business_channel.id,
        customer_id=customer.id,
        agent_active=True,
    )
    db_session.add(conv)
    db_session.add(
        OwnerPhoneIndex(
            phone_e164=owner_phone,
            tenant_id=tenant_id,
            added_at=datetime.now(UTC),
            active=True,
            # Phase 2 TOFU — existing slash-command tests assume a
            # confirmed owner. The TOFU-specific tests in ``TestTOFU``
            # override this back to NULL.
            confirmed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    await db_session.refresh(conv)

    consultation = OwnerConsultation(
        tenant_id=tenant_id,
        conversation_id=conv.id,
        correlation_id=f"REF{tenant_id.hex[:8]}"[:12],
        asked_at=datetime.now(UTC),
        question_text="¿Confirmamos el envío?",
        urgency="normal",
        expected_reply_kind="free_text",
        template_name="auphere_owner_consult",
        template_params_json={},
        status="sent",
        sent_at=datetime.now(UTC),
        created_by="agent:test",
    )
    db_session.add(consultation)
    await db_session.commit()
    await db_session.refresh(consultation)
    return {
        "tenant_id": tenant_id,
        "owner_phone": owner_phone,
        "conv_id": conv.id,
        "consultation_id": consultation.id,
        "correlation_id": consultation.correlation_id,
    }


def _meta_payload(text: str, *, owner_phone: str) -> bytes:
    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_AUPHERE",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "56222000001",
                                    "phone_number_id": OWNER_PHONE_NUMBER_ID,
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Owner"},
                                        "wa_id": owner_phone.lstrip("+"),
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": owner_phone.lstrip("+"),
                                        "id": f"wamid.{uuid.uuid4().hex}",
                                        "timestamp": "1700000000",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()


async def _post(client, text: str, *, owner_phone: str):
    body = _meta_payload(text, owner_phone=owner_phone)
    return await client.post(
        "/webhook/meta",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body),
        },
    )


async def _read_consultation(tenant_id: uuid.UUID, consultation_id: uuid.UUID):
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return await session.get(OwnerConsultation, consultation_id)


async def _read_conv(tenant_id: uuid.UUID, conv_id: uuid.UUID):
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return await session.get(Conversation, conv_id)


async def _read_tenant(tenant_id: uuid.UUID):
    sm = get_sessionmaker()
    async with sm() as session:
        return await session.get(Tenant, tenant_id)


async def _fanout_entries(fake_redis) -> list[dict[str, str]]:
    entries = await fake_redis.xrange(OWNER_FANOUT_STREAM, count=50)
    return [fields for _id, fields in entries]


class TestHelpCommand:
    async def test_help_replies_with_command_list_without_open_consultation(
        self, client, db_session, reply_recorder
    ):
        ctx = await _seed_full_backchannel(db_session)
        # Cancel the consultation so /help doesn't accidentally touch it.
        # ck_owner_consultations_lifecycle requires cancelled_at on cancel.
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, ctx["tenant_id"]):
            row = await session.get(OwnerConsultation, ctx["consultation_id"])
            row.status = "cancelled"
            row.cancelled_at = datetime.now(UTC)
            await session.commit()

        r = await _post(client, "/help", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200
        assert r.json()["status"] == "owner_channel:help_sent"
        assert len(reply_recorder) == 1
        assert "/yes" in reply_recorder[0]["text"]
        assert "/handoff" in reply_recorder[0]["text"]
        assert "/pause" in reply_recorder[0]["text"]


class TestUnknownSlash:
    async def test_unknown_verb_replies_with_help(self, client, db_session, reply_recorder):
        ctx = await _seed_full_backchannel(db_session)

        r = await _post(client, "/blabla", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200
        assert r.json()["status"] == "owner_channel:unknown_command_replied"
        assert len(reply_recorder) == 1
        assert "No reconozco el comando" in reply_recorder[0]["text"]
        assert "/help" in reply_recorder[0]["text"]


class TestYesNoDone:
    async def test_slash_yes_marks_consultation_answered_and_acks(
        self, client, db_session, reply_recorder
    ):
        ctx = await _seed_full_backchannel(db_session)

        r = await _post(client, "/yes", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "owner_channel:queued_for_fanout"
        row = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert row.status == "answered"
        assert row.owner_command_kind == "yes"
        assert any("confirmada" in s["text"] for s in reply_recorder)

    async def test_slash_done_marks_done(self, client, db_session, reply_recorder):
        ctx = await _seed_full_backchannel(db_session)

        await _post(client, "/done lo confirmé por teléfono", owner_phone=ctx["owner_phone"])
        row = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert row.owner_command_kind == "done"
        assert row.status == "answered"
        assert any("resuelta" in s["text"] for s in reply_recorder)


class TestFreeTextWithRef:
    async def test_free_text_with_ref_answers_consultation_and_enqueues_fanout(
        self, client, db_session, reply_recorder, fake_redis
    ):
        ctx = await _seed_full_backchannel(db_session)

        r = await _post(
            client,
            f"sí, dale, confirmado (ref {ctx['correlation_id']})",
            owner_phone=ctx["owner_phone"],
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "owner_channel:queued_for_fanout"
        assert r.json()["side_effect"] == "none"

        row = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert row.status == "answered"
        assert row.owner_command_kind == "free_text"
        assert "confirmado" in (row.owner_response_text or "")

        # Fanout XADD carries tenant + consultation for the worker.
        entries = await _fanout_entries(fake_redis)
        assert len(entries) == 1
        assert entries[0]["tenant_id"] == str(ctx["tenant_id"])
        assert entries[0]["consultation_id"] == str(ctx["consultation_id"])

        # Free text gets no ack reply — the agent's downstream message
        # is what the customer sees.
        assert reply_recorder == []


class TestHandoff:
    async def test_handoff_pauses_conversation_and_acks(
        self, client, db_session, reply_recorder, fake_redis
    ):
        ctx = await _seed_full_backchannel(db_session)

        r = await _post(client, "/handoff", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200, r.text
        assert r.json()["side_effect"] == "handoff_applied"
        conv = await _read_conv(ctx["tenant_id"], ctx["conv_id"])
        assert conv.agent_active is False
        assert conv.agent_active_version == 1
        assert conv.takeover_context is not None
        assert conv.takeover_context["reason"] == "owner /handoff"
        assert any("Tomaste control" in s["text"] for s in reply_recorder)
        # The answered consultation still fans out.
        assert len(await _fanout_entries(fake_redis)) == 1


class TestPause:
    async def test_pause_sets_tenant_status_paused(self, client, db_session, reply_recorder):
        ctx = await _seed_full_backchannel(db_session)

        r = await _post(client, "/pause", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200, r.text
        assert r.json()["side_effect"] == "tenant_paused"
        tenant = await _read_tenant(ctx["tenant_id"])
        assert tenant.status == TenantStatus.PAUSED
        assert any("Pausé todos tus agentes" in s["text"] for s in reply_recorder)


class TestNoOpenConsultation:
    """Phase 2 — when the owner texts in but has no open consultation to
    apply the message to, we reply explaining instead of dropping silent.
    Covers both free-text and slash-command branches."""

    async def _seed_without_open_consultation(self, db_session):
        ctx = await _seed_full_backchannel(db_session)
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, ctx["tenant_id"]):
            row = await session.get(OwnerConsultation, ctx["consultation_id"])
            row.status = "cancelled"
            row.cancelled_at = datetime.now(UTC)
            await session.commit()
        return ctx

    async def test_free_text_without_open_consultation_replies(
        self, client, db_session, reply_recorder
    ):
        ctx = await self._seed_without_open_consultation(db_session)
        r = await _post(client, "hola che", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "owner_channel:no_open_consultation_replied"
        assert len(reply_recorder) == 1
        assert "consulta abierta" in reply_recorder[0]["text"]
        assert "/help" in reply_recorder[0]["text"]

    async def test_slash_yes_without_open_consultation_replies(
        self, client, db_session, reply_recorder
    ):
        ctx = await self._seed_without_open_consultation(db_session)
        r = await _post(client, "/yes", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200
        assert r.json()["status"] == "owner_channel:no_open_consultation_replied"
        assert any("consulta abierta" in s["text"] for s in reply_recorder)

    async def test_slash_handoff_without_open_consultation_replies(
        self, client, db_session, reply_recorder
    ):
        """/handoff without an open consultation can't pick a conversation
        to apply to — reply explaining instead of leaking ambiguity."""
        ctx = await self._seed_without_open_consultation(db_session)
        r = await _post(client, "/handoff", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200
        assert r.json()["status"] == "owner_channel:no_open_consultation_replied"
        # Confirm the conversation was NOT paused.
        conv = await _read_conv(ctx["tenant_id"], ctx["conv_id"])
        assert conv.agent_active is True


class TestTOFU:
    """Phase 2 TOFU — the registered phone must explicitly confirm
    before the webhook unlocks consultations / slash side effects."""

    async def _set_unconfirmed(self, db_session, owner_phone):
        sm = get_sessionmaker()
        async with sm() as session:
            row = await session.get(OwnerPhoneIndex, owner_phone)
            row.confirmed_at = None
            await session.commit()

    async def test_first_yes_confirms_and_replies_welcome(self, client, db_session, reply_recorder):
        ctx = await _seed_full_backchannel(db_session)
        await self._set_unconfirmed(db_session, ctx["owner_phone"])

        r = await _post(client, "/yes", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "owner_channel:tofu_confirmed"
        assert len(reply_recorder) == 1
        assert "Confirmado" in reply_recorder[0]["text"]

        # confirmed_at populated; the open consultation is UNTOUCHED
        # (the /yes here was the TOFU yes, not the consultation yes).
        sm = get_sessionmaker()
        async with sm() as session:
            row = await session.get(OwnerPhoneIndex, ctx["owner_phone"])
            assert row.confirmed_at is not None
        cons = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert cons.status == "sent"  # not answered

    async def test_non_yes_message_replies_welcome_instead_of_processing(
        self, client, db_session, reply_recorder
    ):
        ctx = await _seed_full_backchannel(db_session)
        await self._set_unconfirmed(db_session, ctx["owner_phone"])

        r = await _post(client, "hola che", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200
        assert r.json()["status"] == "owner_channel:tofu_pending"
        assert len(reply_recorder) == 1
        assert "registrado como dueño" in reply_recorder[0]["text"]

        # Consultation untouched.
        cons = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert cons.status == "sent"

    async def test_slash_pause_blocked_until_confirmation(self, client, db_session, reply_recorder):
        """Slash side effects are blocked behind TOFU — a /pause from
        an unconfirmed phone must NOT change the tenant status."""
        ctx = await _seed_full_backchannel(db_session)
        await self._set_unconfirmed(db_session, ctx["owner_phone"])

        r = await _post(client, "/pause", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200
        assert r.json()["status"] == "owner_channel:tofu_pending"
        tenant = await _read_tenant(ctx["tenant_id"])
        assert tenant.status == TenantStatus.ACTIVE  # unchanged
        assert any("registrado como dueño" in s["text"] for s in reply_recorder)

    async def test_confirmed_owner_skips_tofu(self, client, db_session, reply_recorder):
        """Control case — once confirmed_at is set, the webhook proceeds
        to the normal slash-command dispatch."""
        ctx = await _seed_full_backchannel(db_session)
        # confirmed_at is already set by the seed helper.

        r = await _post(client, "/help", owner_phone=ctx["owner_phone"])
        assert r.status_code == 200
        assert r.json()["status"] == "owner_channel:help_sent"
        assert any("/yes" in s["text"] for s in reply_recorder)
