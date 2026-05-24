"""Unit tests for the schema surface introduced by Bloque C — operator
intervention. Covers:

- ``MessageOut.actor_kind`` / ``actor_id`` (NULL on inbound + back-compat
  rows; populated on outbound rows from migration 0041 onwards).
- ``ConversationOut.takeover_context`` (operator notes captured at pause)
  and ``ConversationOut.agent_active_version`` (optimistic-locking counter).

The DB-level CHECK constraint on ``messages.actor_kind`` is verified by
the integration tests in PR-C2 (where we have a session + tenant scope).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from nexus_api.schemas.conversation import ConversationOut, MessageOut


def _msg(**overrides: object) -> MessageOut:
    base = dict(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        created_at=datetime.now(UTC),
        direction="outbound",
        content="hola",
        intent=None,
        cost_usd=None,
        latency_ms=None,
        model=None,
        trace_id=None,
        tool_calls=[],
        status="sent",
    )
    base.update(overrides)
    return MessageOut.model_validate(base)


def _conv(**overrides: object) -> ConversationOut:
    base = dict(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        status="open",
        agent_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    base.update(overrides)
    return ConversationOut.model_validate(base)


class TestMessageOutActorFields:
    def test_actor_fields_default_to_none(self) -> None:
        """Back-compat: rows written before 0041 have NULL actor_* fields.
        ``MessageOut`` mirrors that — both fields are optional and default
        to ``None`` so the admin UI can show "agente" without an explicit
        actor_kind on legacy rows."""
        m = _msg()
        assert m.actor_kind is None
        assert m.actor_id is None

    def test_actor_kind_accepts_known_values(self) -> None:
        for kind in ("agent", "operator", "owner", "system"):
            assert _msg(actor_kind=kind).actor_kind == kind

    def test_actor_id_round_trips(self) -> None:
        admin_uuid = uuid.uuid4()
        m = _msg(actor_kind="operator", actor_id=admin_uuid)
        assert m.actor_id == admin_uuid
        dumped = m.model_dump()
        assert dumped["actor_kind"] == "operator"
        assert dumped["actor_id"] == admin_uuid


class TestConversationOutBloqueCFields:
    def test_takeover_context_defaults_to_none(self) -> None:
        c = _conv()
        assert c.takeover_context is None

    def test_agent_active_version_defaults_to_zero(self) -> None:
        """Server default + Pydantic default both 0. The optimistic-lock
        compare-and-swap on PATCH .../agent always sees a concrete int."""
        c = _conv()
        assert c.agent_active_version == 0

    def test_takeover_context_round_trips_jsonb(self) -> None:
        ctx = {
            "reason": "queja del cliente",
            "notes": "está enojado, intervengo yo",
            "started_at": "2026-05-25T12:00:00Z",
            "operator_id": str(uuid.uuid4()),
        }
        c = _conv(takeover_context=ctx, agent_active=False)
        assert c.takeover_context == ctx
        dumped = c.model_dump()
        assert dumped["takeover_context"]["reason"] == "queja del cliente"
        assert dumped["agent_active"] is False

    def test_agent_active_version_increments_in_payload(self) -> None:
        """The version is opaque to the schema — any non-negative int
        round-trips. The endpoint is what enforces monotonic increments."""
        c = _conv(agent_active_version=7)
        assert c.agent_active_version == 7
