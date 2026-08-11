"""Inbound event dispatcher.

The Redis Stream consumer hands an ``InboundEvent`` to ``process_inbound``;
this module owns the per-turn lifecycle:

1. Open a tenant-scoped session, upsert customer + conversation, persist
   the inbound message row. Close the session before invoking the pipeline
   so we don't hold a transaction open across LLM calls.
2. Verify the tenant is ACTIVE. PAUSED / ARCHIVED tenants persist the
   inbound for audit but the pipeline is skipped — no outbound is
   generated until the operator resumes the tenant.
3. Build the LangGraph state and the canonical ``thread_id``.
4. Invoke the compiled pipeline. The pipeline's ``checkpoint`` node writes
   the outbound row in its own short transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.admin_gate import admin_only_suppresses, sender_is_admin
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, Conversation, Message, Tenant, TenantStatus
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.services.channel_routing import config_agent_enabled, config_role

from nexus_worker.metering.collector import usage_turn
from nexus_worker.multimodal import ProcessedMedia, get_media_processor
from nexus_worker.multimodal.media_fetch import fetch_inbound_media
from nexus_worker.observability.tracing import trace_turn, update_trace
from nexus_worker.persistence.messages import (
    persist_inbound_message,
    upsert_conversation_for_customer,
)
from nexus_worker.persistence.messages import upsert_customer as _upsert_customer
from nexus_worker.runtime.read_receipts import send_read_receipt
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

log = structlog.get_logger(__name__)

# Tenant statuses where the agent is muted — the inbound message is
# persisted for audit but the pipeline does NOT run. PAUSED is reversible
# (operator clicks Resume); ARCHIVED is one-way (soft delete); PROVISIONING
# (migration 0047, ADR-028) is a partner-provisioned tenant that has no
# agent config or channel yet.
_INACTIVE_STATUSES: frozenset[TenantStatus] = frozenset(
    {TenantStatus.PAUSED, TenantStatus.ARCHIVED, TenantStatus.PROVISIONING}
)


# The admin gate lives in ``nexus_api.core.admin_gate`` (single source of
# truth) so the Meta webhook can apply the SAME rule to read receipts —
# a non-admin on a coexistence line gets neither a reply nor a read receipt.
# Re-exported here under the historical name for the dispatcher's tests.
_sender_is_admin = sender_is_admin


def _build_operator_briefing(
    *,
    reason: str | None,
    notes: str | None,
    started_at: str | None,
    operator_id: str | None,
    operator_messages: list[str],
) -> str:
    """Format the operator-intervention briefing for the LLM.

    The briefing is prepended to ``user_message`` on the first turn after
    the operator reactivates the agent. It's wrapped in a clearly-delimited
    ``[Contexto interno]`` block so the model treats it as out-of-band
    instructions rather than as customer-authored text — the prompt
    library + system prompt instruct the LLM to never echo bracketed
    internal context back to the customer.
    """
    lines: list[str] = ["[Contexto interno — intervención humana en esta conversación]"]
    if started_at:
        lines.append(f"Pausa iniciada: {started_at}")
    if operator_id:
        lines.append(f"Operador: {operator_id}")
    if reason:
        lines.append(f"Razón: {reason}")
    if notes:
        lines.append(f"Notas: {notes}")
    if operator_messages:
        lines.append("Mensajes que el operador envió durante la pausa:")
        for idx, msg in enumerate(operator_messages, start=1):
            lines.append(f"  {idx}. {msg}")
    else:
        lines.append("(El operador no envió mensajes durante la pausa.)")
    lines.append("[Fin del contexto interno]")
    return "\n".join(lines)


@dataclass(frozen=True)
class InboundEvent:
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    user_id: str  # external identifier (phone number, etc.)
    content: str
    customer_name: str | None = None
    provider: str = "meta"
    # Block N: native WhatsApp metadata propagated end-to-end so the
    # persisted ``Message`` row carries the full picture (and the
    # multimodal pipeline can pick the media handle without re-parsing
    # the webhook payload).
    kind: str = "text"
    provider_message_id: str | None = None
    media_kind: str | None = None
    # WP-11 (D10): the webhook publishes the provider's media id; the runner
    # resolves bytes → S3 (``media_s3_key`` stays None until then).
    media_provider_id: str | None = None
    media_s3_key: str | None = None
    media_mime: str | None = None
    media_size_bytes: int | None = None
    media_filename: str | None = None
    media_sha256: str | None = None
    reaction_emoji: str | None = None
    reaction_target_wamid: str | None = None
    context_message_id: str | None = None
    location_latitude: float | None = None
    location_longitude: float | None = None
    location_name: str | None = None
    location_address: str | None = None
    # El webhook DECIDE si tocan los dos ticks azules (es donde están el
    # canal y las políticas del agente) y el runner los ENVÍA. Ver
    # runtime/read_receipts.py: dentro del ack costaba ~40% del tiempo de
    # respuesta al webhook de Meta.
    mark_read: bool = False


async def process_inbound(
    event: InboundEvent,
    *,
    pipeline: Any,
) -> dict[str, Any]:
    sm = get_sessionmaker()

    # Lo primero del turno: el acuse de lectura es cortesía y cuanto antes
    # llegue, mejor. Best-effort por contrato — no lanza, y un acuse
    # perdido nunca cuesta un turno.
    if event.mark_read:
        await send_read_receipt(
            provider=event.provider,
            tenant_id=event.tenant_id,
            channel_id=event.channel_id,
            wamid=event.provider_message_id,
        )

    # Block N: multimodal media processing. Run BEFORE persistence so
    # the transcript / vision summary can be stored on the inbound
    # message row alongside the S3 key. Failures are non-fatal — they
    # populate ``processed.error`` and the pipeline still runs with
    # the bare ``[media:...]`` prefix; the agent surfaces a "no pude
    # leerlo" reply.
    # WP-11 (D10): resolve the provider media id to S3 here, out of the
    # webhook's request path. Failure degrades to a text-only turn (the
    # agent asks the customer to resend) — same contract the webhook-side
    # download had, now without holding Meta's connection open for it.
    media_s3_key = event.media_s3_key
    media_mime = event.media_mime
    media_size_bytes = event.media_size_bytes
    if event.media_provider_id and not media_s3_key and event.media_kind:
        fetched = await fetch_inbound_media(
            tenant_id=event.tenant_id,
            channel_id=event.channel_id,
            provider_message_id=event.provider_message_id or f"noid-{event.user_id}",
            media_provider_id=event.media_provider_id,
            hint_mime=event.media_mime,
            hint_sha=event.media_sha256,
        )
        if fetched is not None:
            media_s3_key = fetched.s3_key
            media_mime = fetched.mime
            media_size_bytes = fetched.size_bytes

    processed_media: ProcessedMedia | None = None
    if event.media_kind and media_s3_key:
        try:
            processed_media = await get_media_processor().process(
                s3_key=media_s3_key,
                media_kind=event.media_kind,
                mime_type=media_mime,
                filename=event.media_filename,
            )
        except Exception as exc:
            log.warning(
                "pipeline.media_processor.failed",
                tenant_id=str(event.tenant_id),
                media_kind=event.media_kind,
                error=str(exc),
            )

    user_message = event.content
    media_transcript: str | None = None
    if processed_media is not None and processed_media.text:
        media_transcript = processed_media.text
        # Prepend a short header so the classifier can route on intent
        # while preserving the prefix tag for the response node to log.
        header = (
            "[transcripción de audio]: "
            if processed_media.kind in {"audio", "video"}
            else "[descripción de imagen]: "
            if processed_media.kind in {"image", "sticker"}
            else "[texto del documento]: "
        )
        user_message = f"{event.content}\n{header}{processed_media.text}"
    elif processed_media is not None and processed_media.error:
        user_message = f"{event.content}\n[media-processing-error]: {processed_media.error}"

    # Phase 1: persist inbound side. Short transaction, then close.
    # The tenant.status lookup uses the same scoped session — Tenant is the
    # one entity that doesn't carry tenant_id (it IS the tenant), so RLS on
    # tenants is global; reading it inside the scoped session keeps the
    # transaction count to one.
    async with sm() as session, tenant_scoped_session(session, event.tenant_id):
        tenant_status_raw = (
            await session.execute(sa.select(Tenant.status).where(Tenant.id == event.tenant_id))
        ).scalar_one_or_none()
        if tenant_status_raw is None:
            log.warning(
                "pipeline.skipped.tenant_unknown",
                tenant_id=str(event.tenant_id),
            )
            return {"skipped": "tenant_unknown"}

        customer = await _upsert_customer(
            session, identifier=event.user_id, name=event.customer_name
        )
        conversation = await upsert_conversation_for_customer(
            session, channel_id=event.channel_id, customer_id=customer.id
        )
        # Touch ``conversations.last_inbound_at`` so the 24h window check
        # in notification.send_text has a fresh reference. We update both
        # the in-memory ORM attribute and persist.
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        conversation.last_inbound_at = _dt.now(_UTC)
        inbound_msg = await persist_inbound_message(
            session,
            conversation_id=conversation.id,
            content=event.content,
            provider_message_id=event.provider_message_id,
            media_kind=event.media_kind,
            media_s3_key=media_s3_key,
            media_mime=media_mime,
            media_size_bytes=media_size_bytes,
            media_filename=event.media_filename,
            reaction_emoji=event.reaction_emoji,
            reaction_target_wamid=event.reaction_target_wamid,
            context_message_id=event.context_message_id,
        )
        # Persist the transcript / vision summary if we have one, so the
        # operator panel and downstream analytics can see what the LLM
        # actually read.
        if media_transcript:
            inbound_msg.media_transcript = media_transcript
            await session.flush()
        customer_id = customer.id
        conversation_id = conversation.id
        inbound_id = inbound_msg.id
        conversation_agent_active = conversation.agent_active
        # Send-only channel (``config.agent_enabled = false``): a number the
        # business uses to push notifications out, with nobody behind it to
        # answer what comes back. Read here, inside the session that is
        # already open, and consumed by the skip below.
        channel_config = (
            await session.scalar(sa.select(Channel.config).where(Channel.id == event.channel_id))
        ) or {}
        # Admin-only agents (e.g. cobranza_v1): read the active config's
        # policies while the session is open so the sender gate below can
        # check the whitelist without another transaction.
        active_agent = (
            await session.execute(
                sa.select(AgentConfig.id, AgentConfig.policies)
                .where(AgentConfig.tenant_id == event.tenant_id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                .order_by(AgentConfig.version.desc())
                .limit(1)
            )
        ).first()
        agent_policies: dict[str, Any] = (active_agent[1] if active_agent else None) or {}
        # WP-17: qué VERSIÓN de agente consumió. Es lo que responde si el
        # prompt nuevo salió más caro que el viejo.
        agent_config_id: uuid.UUID | None = active_agent[0] if active_agent else None
        # A tenant with NO agent_config at all is send-only by design (it
        # uses the outbound template API and never had an agent). One with
        # versions but none ACTIVE is a broken agent — see the skip below.
        ever_had_agent = True
        if active_agent is None:
            ever_had_agent = bool(
                await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(AgentConfig)
                    .where(AgentConfig.tenant_id == event.tenant_id)
                )
            )
        # Bloque C — Operator intervention. ``takeover_context`` is populated
        # by ``PATCH .../agent`` when the operator pauses the agent. The
        # first turn after the operator reactivates (i.e. ``agent_active``
        # is true again) consumes it to build a briefing that lets the LLM
        # pick up the conversation knowing what the human did.
        takeover_context = conversation.takeover_context
        operator_briefing: str | None = None
        if takeover_context is not None and conversation_agent_active:
            started_at_iso = takeover_context.get("started_at")
            stmt = (
                sa.select(Message.content, Message.created_at)
                .where(Message.conversation_id == conversation_id)
                .where(Message.actor_kind == "operator")
                .order_by(Message.created_at.asc())
            )
            if started_at_iso:
                from datetime import datetime as _dt2

                try:
                    started_at_dt = _dt2.fromisoformat(started_at_iso.replace("Z", "+00:00"))
                    stmt = stmt.where(Message.created_at >= started_at_dt)
                except ValueError:
                    # Malformed timestamp — fall back to "all operator
                    # messages on this conversation", which is still
                    # bounded by takeover_context.started_at semantics
                    # (this column is cleared on resume).
                    pass
            operator_rows = (await session.execute(stmt)).all()
            operator_briefing = _build_operator_briefing(
                reason=takeover_context.get("reason"),
                notes=takeover_context.get("notes"),
                started_at=started_at_iso,
                operator_id=takeover_context.get("operator_id"),
                operator_messages=[row[0] for row in operator_rows],
            )

    tenant_status = TenantStatus(tenant_status_raw)
    if tenant_status in _INACTIVE_STATUSES:
        # Inbound is captured, agent is muted. The operator panel surfaces
        # the message in the conversation view; resuming the tenant does NOT
        # auto-reply to backlog (next turn only). This matches the
        # consumer-side ack semantics: we still ack the Redis entry.
        log.info(
            "pipeline.skipped.tenant_inactive",
            tenant_id=str(event.tenant_id),
            tenant_status=tenant_status.value,
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_id),
        )
        return {
            "skipped": "tenant_inactive",
            "tenant_status": tenant_status.value,
            "conversation_id": str(conversation_id),
            "inbound_message_id": str(inbound_id),
        }

    if not config_agent_enabled(channel_config):
        # Send-only CHANNEL — the per-number sibling of the send-only tenant
        # skip below. A business running two numbers can have an agent on one
        # of them and a pure notifications line on the other; the tenant-level
        # check cannot express that, because ``agent_configs`` is per tenant.
        #
        # The inbound is persisted first (above) on purpose: a debtor replying
        # "ya pagué" to a reminder must still land in the operator panel. What
        # we skip is the reply, not the record. The Meta webhook applies the
        # same rule to read receipts, so the message also stays unread — on a
        # line nobody is watching, a blue tick would be a lie.
        log.info(
            "pipeline.skipped.send_only_channel",
            tenant_id=str(event.tenant_id),
            channel_id=str(event.channel_id),
            channel_role=config_role(channel_config),
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_id),
        )
        return {
            "skipped": "send_only_channel",
            "conversation_id": str(conversation_id),
            "inbound_message_id": str(inbound_id),
        }

    if active_agent is None and not ever_had_agent:
        # Send-only tenant: it uses the outbound template API and never had
        # an agent, so replies from its customers have nothing to run. The
        # inbound is persisted (the panel shows the conversation) and the
        # Redis entry is acked.
        #
        # Letting this fall through would raise IsolationViolation deep in
        # the loader, which the consumer logs as ``dispatch_failed`` and
        # leaves UNACKED — growing the pending list forever and burying
        # real incidents under a permanent stream of ERROR lines. A tenant
        # that HAS agent versions but no ACTIVE one still takes that path:
        # that one really is broken.
        log.info(
            "pipeline.skipped.no_agent",
            tenant_id=str(event.tenant_id),
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_id),
        )
        return {
            "skipped": "no_agent",
            "conversation_id": str(conversation_id),
            "inbound_message_id": str(inbound_id),
        }

    if not conversation_agent_active:
        # M.3 — operator has taken control of this thread. The inbound
        # is captured but the agent stays muted until the operator
        # reactivates via PATCH .../conversations/:id. No backlog
        # auto-reply on resume: next inbound only.
        log.info(
            "pipeline.skipped.human_takeover",
            tenant_id=str(event.tenant_id),
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_id),
        )
        return {
            "skipped": "human_takeover",
            "conversation_id": str(conversation_id),
            "inbound_message_id": str(inbound_id),
        }

    # Admin-only gate. When the active agent_config declares
    # ``policies.admin_access.admin_only``, ONLY whitelisted phones get a
    # reply. Everyone else's inbound is persisted for audit (the operator
    # panel still shows it) but the agent stays silent — no outbound, no
    # acknowledgement, no information leak. This is how the cobranza admin
    # agent ignores debtors and strangers. (The Meta webhook applies the same
    # rule to read receipts so non-admin messages also stay unread.)
    if admin_only_suppresses(agent_policies, event.user_id):
        log.info(
            "pipeline.skipped.not_admin",
            tenant_id=str(event.tenant_id),
            conversation_id=str(conversation_id),
            inbound_message_id=str(inbound_id),
        )
        return {
            "skipped": "not_admin",
            "conversation_id": str(conversation_id),
            "inbound_message_id": str(inbound_id),
        }

    # Bloque C — prepend the operator briefing (if any) so the LLM sees
    # the "what the human did while you were paused" context before the
    # customer's actual message. The briefing is delimited so the prompt
    # library treats it as out-of-band instructions and never echoes it
    # back to the customer.
    if operator_briefing is not None:
        user_message = f"{operator_briefing}\n\n[Mensaje del cliente]\n{user_message}"

    state = new_state(
        tenant_id=event.tenant_id,
        channel_id=event.channel_id,
        user_id=event.user_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        inbound_message_id=inbound_id,
        # Use the multimodal-enriched user_message so the classifier and
        # the handler nodes see "[transcripción de audio]: hola quiero un
        # turno" instead of just "[media:audio]". When the media is
        # text-only or processing failed, ``user_message`` falls back to
        # ``event.content`` upstream.
        user_message=user_message,
    )
    thread_id = make_thread_id(event.tenant_id, event.channel_id, event.user_id)
    config = {"configurable": {"thread_id": thread_id}}

    log.info(
        "pipeline.run.start",
        tenant_id=str(event.tenant_id),
        channel_id=str(event.channel_id),
        user_id=event.user_id,
        thread_id=thread_id,
    )
    # WP-17: el buffer de consumo del turno. Envuelve la invocación del
    # grafo porque ahí dentro caen TODAS las llamadas al LLM (classify,
    # respond, grader, multimodal) y el ContextVar viaja a las tareas que
    # LangGraph cree por debajo. El id del mensaje entrante hace de turn_id
    # — ya es único por turno y es lo que ancla la idempotencia. Publica al
    # salir, también si el turno revienta: esos tokens ya se gastaron.
    async with usage_turn(
        tenant_id=event.tenant_id,
        turn_id=str(inbound_id),
        conversation_id=conversation_id,
        agent_config_id=agent_config_id,
    ):
        with trace_turn(
            tenant_id=event.tenant_id,
            channel_id=event.channel_id,
            user_id_inside_channel=event.user_id,
            name="agent.turn",
            metadata={"thread_id": thread_id, "provider": event.provider},
        ):
            final = await pipeline.ainvoke(state, config=config)
        update_trace(
            output={
                "intent": final.get("intent"),
                "response_present": bool(final.get("response")),
                "tool_calls": [
                    {"tool": c.get("tool"), "status": c.get("status")}
                    for c in (final.get("tool_calls") or [])
                ],
            }
        )
    log.info(
        "pipeline.run.done",
        tenant_id=str(event.tenant_id),
        intent=final.get("intent"),
        response_present=bool(final.get("response")),
    )

    # Bloque C — pipeline ran successfully on a post-resume turn that
    # carried the operator briefing. Clear ``takeover_context`` so the
    # next turn doesn't replay the briefing. We keep the clear outside
    # the pipeline transaction on purpose: a pipeline failure leaves
    # ``takeover_context`` set so the next retry still receives the
    # briefing.
    if operator_briefing is not None:
        async with sm() as cleanup_session, tenant_scoped_session(cleanup_session, event.tenant_id):
            await cleanup_session.execute(
                sa.update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(takeover_context=None)
            )
            await cleanup_session.commit()

    return dict(final)
