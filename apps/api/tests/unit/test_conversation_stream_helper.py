"""Unit tests for ``publish_conversation_event``.

The helper is what every write path (operator-send, agent-toggle,
pipeline checkpoint) calls to push a live update onto the per-conv
pub/sub channel. The tests use a stub Redis to avoid pulling docker
into a unit test.
"""

from __future__ import annotations

import json
import uuid

import pytest

from nexus_api.services.conversation_stream import (
    conversation_channel,
    publish_conversation_event,
)


class _StubRedis:
    def __init__(self, *, raise_on_publish: bool = False) -> None:
        self.published: list[tuple[str, str]] = []
        self.raise_on_publish = raise_on_publish

    async def publish(self, channel: str, body: str) -> int:
        if self.raise_on_publish:
            raise RuntimeError("redis is on fire")
        self.published.append((channel, body))
        return 1


class TestConversationChannel:
    def test_channel_name_uses_conv_uuid(self) -> None:
        cid = uuid.uuid4()
        assert conversation_channel(cid) == f"conv:{cid}:events"


class TestPublishConversationEvent:
    @pytest.mark.asyncio
    async def test_emits_event_and_payload(self) -> None:
        redis = _StubRedis()
        cid = uuid.uuid4()
        await publish_conversation_event(
            redis,
            conversation_id=cid,
            event="message.new",
            payload={"message_id": "abc", "direction": "outbound"},
        )
        assert len(redis.published) == 1
        chan, body = redis.published[0]
        assert chan == f"conv:{cid}:events"
        parsed = json.loads(body)
        assert parsed == {
            "event": "message.new",
            "message_id": "abc",
            "direction": "outbound",
        }

    @pytest.mark.asyncio
    async def test_payload_optional(self) -> None:
        redis = _StubRedis()
        cid = uuid.uuid4()
        await publish_conversation_event(redis, conversation_id=cid, event="agent.toggled")
        assert json.loads(redis.published[0][1]) == {"event": "agent.toggled"}

    @pytest.mark.asyncio
    async def test_uuid_in_payload_serialises(self) -> None:
        redis = _StubRedis()
        cid = uuid.uuid4()
        msg_id = uuid.uuid4()
        await publish_conversation_event(
            redis,
            conversation_id=cid,
            event="message.new",
            payload={"message_id": msg_id},
        )
        parsed = json.loads(redis.published[0][1])
        assert parsed["message_id"] == str(msg_id)

    @pytest.mark.asyncio
    async def test_publish_failure_swallowed(self) -> None:
        """Live updates are best-effort: a transient Redis failure must
        NOT block the calling write path."""
        redis = _StubRedis(raise_on_publish=True)
        # Must NOT raise.
        await publish_conversation_event(
            redis,
            conversation_id=uuid.uuid4(),
            event="message.new",
        )
