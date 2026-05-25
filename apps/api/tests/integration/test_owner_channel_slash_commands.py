"""Integration tests for Phase 2 owner-backchannel slash commands.

Exercises the dispatch path inside ``apps/api/.../webhooks/owner_channel.py``
end-to-end against a real Postgres + RLS scope, with the YCloud adapter
patched to a recording stub so we never reach the network.

Each test seeds the minimum graph (tenant + channel + customer +
conversation + owner_phone_index + open consultation) needed to land on
the dispatch branch, posts the webhook, and asserts on:

- the JSON status the webhook returns,
- the side effect on the DB row (consultation status, agent_active,
  tenant.status),
- the ack message the adapter would have sent (when applicable).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
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

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class _RecordingAdapter:
    """Stand-in for WhatsAppYCloudAdapter. Records every send_text call
    so the test can assert what message the owner would have received."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_text(
        self,
        *,
        from_phone: str,
        recipient: str,
        text: str,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        context_message_id: str | None = None,
    ) -> Any:
        self.sent.append(
            {
                "from_phone": from_phone,
                "recipient": recipient,
                "text": text,
                "tenant_id": str(tenant_id),
            }
        )

        class _Result:
            provider_message_id = "stub-wamid"

        return _Result()


def _bypass_signature_and_adapter(monkeypatch):
    """Disable the HMAC check + swap the adapter for a recorder. Returns
    the recorder so tests can assert sent messages."""
    import nexus_api.api.webhooks.owner_channel as oc

    def _noop(secret, body, sig, *, tolerance_seconds):
        return True

    monkeypatch.setattr(oc, "verify_ycloud_signature", _noop)
    rec = _RecordingAdapter()
    monkeypatch.setattr(oc, "_build_ycloud_adapter", lambda: rec)
    return rec


async def _seed_full_backchannel(
    db_session: Any,
    *,
    to_phone: str = "+56222000001",
    owner_phone: str = "+56999111222",
) -> dict[str, Any]:
    """Set up a tenant + channel + Auphere number + open consultation
    that the webhook can route a slash command into."""
    from nexus_api.db.models import AuphereOwnerChannel

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
            phone_e164=to_phone,
            display_name="slash-test",
            provider="ycloud",
            is_default=True,
            active=True,
        )
    )
    business_channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="ycloud",
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
            # confirmed owner. The TOFU-specific tests in
            # ``TestTOFU*`` override this back to NULL.
            confirmed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    await db_session.refresh(conv)

    consultation = OwnerConsultation(
        tenant_id=tenant_id,
        conversation_id=conv.id,
        correlation_id=f"REF{tenant_id.hex[:8]}",
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
        "to_phone": to_phone,
        "owner_phone": owner_phone,
        "conv_id": conv.id,
        "consultation_id": consultation.id,
    }


def _post_payload(text: str, *, to_phone: str, owner_phone: str) -> str:
    return json.dumps(
        {
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "to": to_phone,
                "from": owner_phone,
                "text": {"body": text},
            },
        }
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


class TestHelpCommand:
    async def test_help_replies_with_command_list_without_open_consultation(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)
        # Cancel the consultation so /help doesn't accidentally touch it.
        # ck_owner_consultations_lifecycle requires cancelled_at on cancel.
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, ctx["tenant_id"]):
            row = await session.get(OwnerConsultation, ctx["consultation_id"])
            row.status = "cancelled"
            row.cancelled_at = datetime.now(UTC)
            await session.commit()

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/help",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "help_sent"
        assert len(rec.sent) == 1
        assert "/yes" in rec.sent[0]["text"]
        assert "/handoff" in rec.sent[0]["text"]
        assert "/pause" in rec.sent[0]["text"]


class TestUnknownSlash:
    async def test_unknown_verb_replies_with_help(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/blabla",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "unknown_command_replied"
        assert len(rec.sent) == 1
        assert "No reconozco el comando" in rec.sent[0]["text"]
        assert "/help" in rec.sent[0]["text"]


class TestYesNoDone:
    async def test_slash_yes_marks_consultation_answered_and_acks(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/yes",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "queued_for_fanout"
        row = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert row.status == "answered"
        assert row.owner_command_kind == "yes"
        assert any("confirmada" in s["text"] for s in rec.sent)

    async def test_slash_done_marks_done(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)

        await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/done lo confirmé por teléfono",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        row = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert row.owner_command_kind == "done"
        assert row.status == "answered"
        assert any("resuelta" in s["text"] for s in rec.sent)


class TestHandoff:
    async def test_handoff_pauses_conversation_and_acks(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/handoff",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["side_effect"] == "handoff_applied"
        conv = await _read_conv(ctx["tenant_id"], ctx["conv_id"])
        assert conv.agent_active is False
        assert conv.agent_active_version == 1
        assert conv.takeover_context is not None
        assert conv.takeover_context["reason"] == "owner /handoff"
        assert any("Tomaste control" in s["text"] for s in rec.sent)


class TestPause:
    async def test_pause_sets_tenant_status_paused(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/pause",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["side_effect"] == "tenant_paused"
        tenant = await _read_tenant(ctx["tenant_id"])
        assert tenant.status == TenantStatus.PAUSED
        assert any("Pausé todos tus agentes" in s["text"] for s in rec.sent)


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
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await self._seed_without_open_consultation(db_session)
        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "hola che",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "no_open_consultation_replied"
        assert len(rec.sent) == 1
        assert "No tenés ninguna consulta abierta" in rec.sent[0]["text"]
        assert "/help" in rec.sent[0]["text"]

    async def test_slash_yes_without_open_consultation_replies(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await self._seed_without_open_consultation(db_session)
        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/yes",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "no_open_consultation_replied"
        assert any("No tenés ninguna consulta abierta" in s["text"] for s in rec.sent)

    async def test_slash_handoff_without_open_consultation_replies(
        self, client, db_session, monkeypatch
    ):
        """/handoff without an open consultation can't pick a conversation
        to apply to — reply explaining instead of leaking ambiguity."""
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await self._seed_without_open_consultation(db_session)
        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/handoff",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "no_open_consultation_replied"
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

    async def test_first_yes_confirms_and_replies_welcome(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)
        await self._set_unconfirmed(db_session, ctx["owner_phone"])

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/yes",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "tofu_confirmed"
        assert len(rec.sent) == 1
        assert "Confirmado" in rec.sent[0]["text"]

        # confirmed_at populated; the open consultation is UNTOUCHED
        # (the /yes here was the TOFU yes, not the consultation yes).
        sm = get_sessionmaker()
        async with sm() as session:
            row = await session.get(OwnerPhoneIndex, ctx["owner_phone"])
            assert row.confirmed_at is not None
        cons = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert cons.status == "sent"  # not answered

    async def test_non_yes_message_replies_welcome_instead_of_processing(
        self, client, db_session, monkeypatch
    ):
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)
        await self._set_unconfirmed(db_session, ctx["owner_phone"])

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "hola che",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "tofu_pending"
        assert len(rec.sent) == 1
        assert "registrado como dueño" in rec.sent[0]["text"]

        # Consultation untouched.
        cons = await _read_consultation(ctx["tenant_id"], ctx["consultation_id"])
        assert cons.status == "sent"

    async def test_slash_pause_blocked_until_confirmation(
        self, client, db_session, monkeypatch
    ):
        """Slash side effects are blocked behind TOFU — a /pause from
        an unconfirmed phone must NOT change the tenant status."""
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)
        await self._set_unconfirmed(db_session, ctx["owner_phone"])

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/pause",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "tofu_pending"
        tenant = await _read_tenant(ctx["tenant_id"])
        assert tenant.status == TenantStatus.ACTIVE  # unchanged
        assert any("registrado como dueño" in s["text"] for s in rec.sent)

    async def test_confirmed_owner_skips_tofu(
        self, client, db_session, monkeypatch
    ):
        """Control case — once confirmed_at is set, the webhook proceeds
        to the normal slash-command dispatch."""
        rec = _bypass_signature_and_adapter(monkeypatch)
        ctx = await _seed_full_backchannel(db_session)
        # confirmed_at is already set by the seed helper.

        r = await client.post(
            "/webhook/ycloud/owner-channel",
            content=_post_payload(
                "/help",
                to_phone=ctx["to_phone"],
                owner_phone=ctx["owner_phone"],
            ),
            headers={"YCloud-Signature": "ignored"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "help_sent"
        assert any("/yes" in s["text"] for s in rec.sent)
