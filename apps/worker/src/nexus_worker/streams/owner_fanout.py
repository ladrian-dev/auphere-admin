"""Owner-response fanout — consume ``nexus:owner_fanout`` and re-enter
the pipeline so the agent answers the customer with the owner's input.

Flow (spec ``architecture/owner-backchannel.md`` §6):

1. Read ``{tenant_id, consultation_id}`` from the stream.
2. Open a tenant-scoped session, fetch the row, the conversation, and
   the related customer + channel.
3. Build a ``system_addendum`` describing what the owner answered
   ("[OPERATOR_NOTE] El owner respondió a tu consulta …"). The agent's
   prompt instructs it to use the info as if it knew it directly —
   never to surface "owner" or "backchannel" to the customer.
4. Clear ``conversation.awaiting_owner_response``.
5. Synthesize an :class:`AgentState` and invoke the compiled pipeline
   with ``user_message=""`` and the system addendum. The classify node
   sees an empty user message + the synthetic note and routes to the
   right intent; ``respond`` produces the final text the outbound
   dispatcher will deliver to the customer.

Failure handling: same as the inbound consumer — on exception we DO
NOT ack so the entry is redelivered. The consultation row stays at
``status='answered'`` so a duplicate fanout re-renders the same note;
the LLM is idempotent enough that the customer would just receive a
similar reply twice in the worst case (Phase 2 dedupes via a
``fanout_completed_at`` column).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, Conversation, Customer, OwnerConsultation
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import select

from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

log = structlog.get_logger(__name__)


OWNER_FANOUT_STREAM = "nexus:owner_fanout"
OWNER_FANOUT_GROUP = "nexus_owner_fanout"


def _build_addendum(row: OwnerConsultation) -> str:
    """Render the system note the pipeline injects on re-entry.

    Wording matches the spec §6.1 verbatim. The agent's seed prompt
    references the ``[OPERATOR_NOTE]`` marker so it knows the source
    without leaking it to the customer.
    """
    response = row.owner_response_text or ""
    return (
        "[OPERATOR_NOTE] El owner respondió a tu consulta "
        f"(ref {row.correlation_id}, pregunta: {row.question_text!r}): "
        f"{response!r}. Procedé con el cliente con esa información — "
        "no cites la consulta ni la palabra 'owner', redactalo como si "
        "lo supieras directamente."
    )


async def _ensure_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(OWNER_FANOUT_STREAM, OWNER_FANOUT_GROUP, id="$", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _decode_fields(raw: dict[bytes | str, bytes | str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = k.decode() if isinstance(k, bytes) else k
        vs = v.decode() if isinstance(v, bytes) else v
        out[ks] = vs
    return out


async def process_owner_fanout(
    *,
    pipeline: Any,
    tenant_id: uuid.UUID,
    consultation_id: uuid.UUID,
) -> dict[str, Any]:
    """Re-enter the pipeline for a single consultation. Exposed so unit
    tests can drive a fanout without spinning a Redis consumer."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = await session.get(OwnerConsultation, consultation_id)
        if row is None or row.status != "answered":
            log.info(
                "owner_fanout.skipped.row_not_answered",
                tenant_id=str(tenant_id),
                consultation_id=str(consultation_id),
                status=getattr(row, "status", None),
            )
            return {"skipped": "not_answered"}
        conv = await session.get(Conversation, row.conversation_id)
        if conv is None:
            log.info(
                "owner_fanout.skipped.conversation_missing",
                tenant_id=str(tenant_id),
                conversation_id=str(row.conversation_id),
            )
            return {"skipped": "conversation_missing"}
        # Look up the customer's identifier for the synthesized state —
        # the pipeline persists outbound replies; the outbound dispatcher
        # picks them up by walking from message → conversation → channel
        # + customer, so the agent state just needs the IDs.
        customer = await session.get(Customer, conv.customer_id)
        channel = await session.get(Channel, conv.channel_id)
        if customer is None or channel is None:
            log.warning(
                "owner_fanout.skipped.relations_missing",
                tenant_id=str(tenant_id),
                conversation_id=str(conv.id),
            )
            return {"skipped": "relations_missing"}

        conv.awaiting_owner_response = False
        conv.awaiting_owner_correlation_id = None
        addendum = _build_addendum(row)
        identity = (
            tenant_id,
            channel.id,
            customer.identifier,
            conv.id,
            customer.id,
            row.id,
        )

    tenant_uuid, channel_id, user_id, conv_id, customer_id, inbound_id = identity
    state = new_state(
        tenant_id=tenant_uuid,
        channel_id=channel_id,
        user_id=user_id,
        conversation_id=conv_id,
        customer_id=customer_id,
        # The pipeline expects a UUID for the inbound message; the fanout
        # has no "real" inbound message, so we reuse the consultation id
        # as a stable identifier for traces. The downstream persistence
        # never reads this UUID for FK lookups (it persists the OUTBOUND
        # row, not the inbound), so reusing is safe.
        inbound_message_id=inbound_id,
        user_message="",
        system_addendum=addendum,
    )
    thread_id = make_thread_id(tenant_uuid, channel_id, user_id)
    config = {"configurable": {"thread_id": thread_id}}
    log.info(
        "owner_fanout.invoke",
        tenant_id=str(tenant_uuid),
        consultation_id=str(consultation_id),
        thread_id=thread_id,
    )
    final = await pipeline.ainvoke(state, config=config)
    return dict(final)


async def run_owner_fanout_consumer(
    redis: Redis,
    pipeline: Any,
    *,
    consumer_name: str,
    block_ms: int = 5_000,
    stop: asyncio.Event | None = None,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    await _ensure_group(redis)
    log.info(
        "owner_fanout.consumer.start",
        stream=OWNER_FANOUT_STREAM,
        group=OWNER_FANOUT_GROUP,
        consumer=consumer_name,
    )

    while stop is None or not stop.is_set():
        try:
            response = await redis.xreadgroup(
                groupname=OWNER_FANOUT_GROUP,
                consumername=consumer_name,
                streams={OWNER_FANOUT_STREAM: ">"},
                count=10,
                block=block_ms,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("owner_fanout.consumer.xreadgroup_failed", error=str(exc))
            await asyncio.sleep(1.0)
            continue

        if not response:
            continue

        for _stream_name, entries in response:
            for entry_id, raw_fields in entries:
                entry_id_str = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                fields = _decode_fields(raw_fields)
                try:
                    tenant_id = uuid.UUID(fields["tenant_id"])
                    consultation_id = uuid.UUID(fields["consultation_id"])
                except (KeyError, ValueError) as exc:
                    log.warning(
                        "owner_fanout.consumer.malformed_entry",
                        entry_id=entry_id_str,
                        error=str(exc),
                    )
                    await redis.xack(OWNER_FANOUT_STREAM, OWNER_FANOUT_GROUP, entry_id_str)
                    continue
                try:
                    await process_owner_fanout(
                        pipeline=pipeline,
                        tenant_id=tenant_id,
                        consultation_id=consultation_id,
                    )
                except Exception as exc:
                    log.error(
                        "owner_fanout.consumer.dispatch_failed",
                        entry_id=entry_id_str,
                        tenant_id=str(tenant_id),
                        consultation_id=str(consultation_id),
                        error=str(exc),
                    )
                    continue
                await redis.xack(OWNER_FANOUT_STREAM, OWNER_FANOUT_GROUP, entry_id_str)

    log.info(
        "owner_fanout.consumer.stopped",
        stream=OWNER_FANOUT_STREAM,
        group=OWNER_FANOUT_GROUP,
    )


async def lookup_open_consultation_id(redis: Redis, tenant_id: uuid.UUID) -> uuid.UUID | None:
    """Helper for the timeout sweep — find one open consultation for the
    tenant. Kept out of the consumer hot path; the sweep loop uses it."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = await session.execute(
            select(OwnerConsultation.id)
            .where(OwnerConsultation.status.in_(("pending", "sent")))
            .order_by(OwnerConsultation.asked_at.asc())
            .limit(1)
        )
        result = row.scalar_one_or_none()
        return result if result is not None else None


# Re-exported helper kept for test ergonomics — silences linters when
# the module is imported only for the fanout helper.
_ = contextlib
