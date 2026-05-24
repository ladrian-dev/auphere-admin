"""Bloque C — pub/sub fanout for per-conversation live updates.

The admin operator panel opens an ``EventSource`` to
``GET .../conversations/{conv_id}/stream`` to receive new-message
notifications without polling. Producers (the API endpoints that write
to a conversation, the worker pipeline checkpoint, the outbound
dispatcher) call ``publish_conversation_event`` to push an event onto
the per-conversation pub/sub channel; the SSE endpoint reads from the
same channel and re-emits each event to the browser.

Pub/Sub vs Streams: pub/sub is the right primitive here because
(1) each browser tab is its own short-lived subscriber, (2) the panel
hydrates the full message list on connect anyway, so missed events on
reconnect don't break correctness — they just delay a few seconds.
Streams would force us to track per-tab consumer state, which is
overkill for a live-view feature.

The channel name uses the conversation UUID — there is no tenant
scoping at the channel level because the GET endpoint already enforces
the ``tenant_id`` path check before subscribing. A leaked channel name
without a valid admin token is unreachable from the outside.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)


def conversation_channel(conversation_id: uuid.UUID) -> str:
    return f"conv:{conversation_id}:events"


async def publish_conversation_event(
    redis: Redis,
    *,
    conversation_id: uuid.UUID,
    event: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Publish ``event`` to the per-conversation channel.

    The wire format is a JSON object with ``event`` (string discriminator)
    and the merged payload fields. ``default=str`` handles UUIDs and
    datetimes without callers having to pre-serialise.

    Failures are non-fatal: live updates are a UX nicety, not a
    correctness boundary. We log and move on so the calling write path
    (operator-send, agent-toggle, pipeline checkpoint) is never blocked
    by a transient Redis hiccup.
    """
    channel = conversation_channel(conversation_id)
    body = {"event": event}
    if payload:
        body.update(payload)
    try:
        await redis.publish(channel, json.dumps(body, default=str))
    except Exception as exc:
        log.warning(
            "conversation_stream.publish_failed",
            conversation_id=str(conversation_id),
            event_name=event,
            error=str(exc),
        )
