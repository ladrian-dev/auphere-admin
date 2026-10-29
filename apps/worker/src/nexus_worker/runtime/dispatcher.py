"""Inbound event dispatcher — guardar primero, y un turno por ráfaga.

Spec 047, ola 1 (requisitos 1 y 2; research D8, D9 y D43). Dos tiempos:

1. **``accept_inbound``** — lo primero, siempre: el entrante se guarda (con su
   adjunto ya en S3) antes de decidir nada. Ni la bolsa vacía, ni la pausa, ni
   el número con problemas impiden que quede guardado. Hasta la 047 la puerta
   de saldo iba antes y, sin saldo, el mensaje se perdía sin rastro.
2. **``run_turn``** — el turno de la conversación (``runtime/turns.py``): toma
   con el candado todos los entrantes sin turno —la ráfaga entera—, pasa las
   puertas y, si se puede, corre el grafo. Si una puerta no deja contestar, la
   conversación guarda su motivo (``contracts/events.md`` §2), va a la Bandeja
   como «Espera a una persona» (salvo fuera de la audiencia) y se avisa a quien
   toca.

``process_inbound`` hace las dos cosas seguidas: es el camino de las pruebas y
del reclamador del stream. El consumidor hace la primera y programa la segunda
a ``+ventana`` en la cola diferida, que es lo que convierte «hola» / «quiero
cita» / «mañana por la tarde» en una sola respuesta.

Las puertas, en este orden (la primera que cierra gana):

====================  ======================  =================================
puerta                ``skipped`` (de hoy)    motivo (``waiting_reason``)
====================  ======================  =================================
cliente en pausa      ``tenant_inactive``     ``paused_client``
cliente archivado     ``tenant_inactive``     ``archived_client``
cliente en alta       ``tenant_inactive``     ``agent_unpublished``
canal en pausa        ``channel_paused``      ``paused_channel``
canal desvinculado    ``channel_problem``     ``channel_problem``
número solo de envío  ``send_only_channel``   — (no lo atiende nadie)
cliente sin agente    ``no_agent``            ``agent_unpublished``
agente sin publicar   ``agent_unpublished``   ``agent_unpublished``
fuera de la audiencia ``not_admin``           ``out_of_audience``
lo lleva una persona  ``human_takeover``      ``human_takeover``
bolsa vacía           ``wallet_empty``        ``no_balance``
sin proxy de modelos  ``llm_proxy_unavailable`` ``no_model``
presupuesto duro      ``budget_hard_limit``   ``turn_limit``
====================  ======================  =================================

El canal **con problemas de calidad** (``degraded``) sigue contestando
(Historia 1, escenario 3). El tope y la pausa del agente llegan con sus
columnas (olas 7 y 4); sus motivos ya están en la lista cerrada.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.admin_gate import admin_only_suppresses, audience_suppresses, sender_is_admin
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentStatus,
    Channel,
    ChannelStatus,
    Conversation,
    Customer,
    Message,
    Tenant,
    TenantStatus,
)
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.services import conversation_control, inbox_lifecycle, push_events, reception
from nexus_api.services.channel_config import gate_audience
from nexus_api.services.channel_routing import config_agent_enabled, config_role
from nexus_api.services.inbox_stream import publish_inbox_event

from nexus_worker.metering.budget import evaluate as evaluate_budget
from nexus_worker.metering.collector import record_media_unit, usage_turn
from nexus_worker.multimodal import ProcessedMedia, get_media_processor
from nexus_worker.multimodal.media_fetch import fetch_inbound_media
from nexus_worker.observability.tracing import trace_turn, update_trace
from nexus_worker.persistence.messages import (
    persist_inbound_message,
    persist_outbound_message,
    upsert_conversation_for_customer,
)
from nexus_worker.persistence.messages import upsert_customer as _upsert_customer
from nexus_worker.runtime import turns
from nexus_worker.runtime.budget_gate import apply_hard_cutoff
from nexus_worker.runtime.read_receipts import send_read_receipt
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

log = structlog.get_logger(__name__)


def suppression_reason(agent_policies: dict[str, Any] | None, sender: str | None) -> str | None:
    """Spec 024: the ``messages.skipped_reason`` value for an inbound the
    agent will not answer, or ``None`` when it will. Today only the
    admin-only gate leaves a reason; it is the same test the gate runs."""
    return "not_admin" if admin_only_suppresses(agent_policies, sender) else None


# Tenant statuses where the agent is muted — the inbound message is
# persisted and waits for a person, but the pipeline does NOT run. PAUSED is
# reversible (operator clicks Resume); ARCHIVED is one-way (soft delete);
# PROVISIONING (migration 0047, ADR-028) is a partner-provisioned tenant that
# has no agent config or channel yet.
_INACTIVE_STATUSES: dict[TenantStatus, str] = {
    TenantStatus.PAUSED: "paused_client",
    TenantStatus.ARCHIVED: "archived_client",
    TenantStatus.PROVISIONING: "agent_unpublished",
}


# The admin gate lives in ``nexus_api.core.admin_gate`` (single source of
# truth) so the Meta webhook can apply the SAME rule to read receipts —
# a non-admin on a coexistence line gets neither a reply nor a read receipt.
# Re-exported here under the historical name for the dispatcher's tests.
_sender_is_admin = sender_is_admin


#: Quien escribe a mano mientras el agente está en pausa: el operador de
#: Auphere desde el admin (Bloque C) o la persona del cliente desde la Bandeja
#: (spec 030). El resumen de la devolución cuenta lo de los dos.
_HUMAN_ACTORS = ("operator", "member")

#: Spec 047 (requisito 2.5): sin Bandeja, el mensaje de espera del canal sale
#: como mucho una vez en esta ventana por conversación (la regla de hoy de
#: ``budget_gate``).
WAIT_MESSAGE_WINDOW = "6 hours"
#: Los motivos con los que el contacto recibe el mensaje de espera. No los de
#: un cliente o un canal en pausa (nadie quiere que un número en pausa hable),
#: ni el presupuesto duro, que ya contesta con su propio traspaso.
_WAIT_MESSAGE_REASONS = frozenset(
    {"no_balance", "agent_cap", "paused_agent", "agent_unpublished", "no_model", "provider_failure"}
)


async def takeover_messages(
    session: Any, conversation_id: uuid.UUID, started_at_iso: str | None
) -> list[str]:
    """Lo que escribieron las personas desde que tomaron el control, en orden."""
    stmt = (
        sa.select(Message.content)
        .where(Message.conversation_id == conversation_id)
        .where(Message.actor_kind.in_(_HUMAN_ACTORS))
        .order_by(Message.created_at.asc())
    )
    if started_at_iso:
        from datetime import datetime as _dt2

        try:
            started_at_dt = _dt2.fromisoformat(started_at_iso.replace("Z", "+00:00"))
            stmt = stmt.where(Message.created_at >= started_at_dt)
        except ValueError:
            # Malformed timestamp — fall back to "all human messages on this
            # conversation", still bounded by takeover_context semantics
            # (this column is cleared on resume).
            pass
    return [str(content or "") for (content,) in (await session.execute(stmt)).all()]


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
    # Spec 050: how Meta identifies the person. ``user_id`` stays the phone
    # when there is one (today's key); a BSUID-only person arrives with
    # ``user_id`` = BSUID.
    customer_phone: str | None = None
    customer_bsuid: str | None = None
    customer_username: str | None = None
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


# ── 1. Guardar ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AcceptedInbound:
    """Lo que dejó ``accept_inbound``: el entrante ya está en la base."""

    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    #: El stream lo volvió a entregar y ya estaba guardado (mismo ``wamid``).
    duplicate: bool = False
    #: ``tenant_unknown``: no hay cliente al que guardárselo.
    skipped: str | None = None


_PRIOR_INBOUND_SQL = sa.text(
    "SELECT id, conversation_id FROM messages "
    "WHERE provider_message_id = :wamid AND direction = 'inbound' LIMIT 1"
)


async def accept_inbound(event: InboundEvent) -> AcceptedInbound:
    """Guarda el entrante, sea cual sea el estado del cliente, del agente, del
    canal o de la bolsa (requisito 2.1). No decide nada más."""
    # Lo primero: el acuse de lectura es cortesía y cuanto antes llegue,
    # mejor. Best-effort por contrato — no lanza, y un acuse perdido nunca
    # cuesta un turno.
    if event.mark_read:
        await send_read_receipt(
            provider=event.provider,
            tenant_id=event.tenant_id,
            channel_id=event.channel_id,
            wamid=event.provider_message_id,
        )

    # WP-11 (D10): resolve the provider media id to S3 here, out of the
    # webhook's request path. Before the gates: a person who reads the
    # conversation in the Inbox has to see the receipt even when the agent
    # does not answer. Failure degrades to a text-only row (the agent asks
    # the customer to resend). Transcribing it — which costs — waits for the
    # turn, behind the gates.
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

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, event.tenant_id):
        # Tenant is the one entity without tenant_id (it IS the tenant): RLS on
        # ``tenants`` is global and reading it here keeps one transaction.
        known = await session.scalar(sa.select(Tenant.id).where(Tenant.id == event.tenant_id))
        if known is None:
            log.warning("pipeline.skipped.tenant_unknown", tenant_id=str(event.tenant_id))
            return AcceptedInbound(event.tenant_id, event.channel_id, skipped="tenant_unknown")

        # The unique index on ``provider_message_id`` carries ``created_at``
        # (``messages`` is partitioned) and does not stop a second row: a
        # redelivered entry reuses the one it already saved.
        if event.provider_message_id:
            prior = (
                await session.execute(_PRIOR_INBOUND_SQL, {"wamid": event.provider_message_id})
            ).first()
            if prior is not None:
                return AcceptedInbound(
                    event.tenant_id,
                    event.channel_id,
                    conversation_id=prior[1],
                    message_id=prior[0],
                    duplicate=True,
                )

        customer = await _upsert_customer(
            session,
            identifier=event.user_id,
            name=event.customer_name,
            bsuid=event.customer_bsuid,
            phone=event.customer_phone,
            username=event.customer_username,
        )
        conversation = await upsert_conversation_for_customer(
            session, channel_id=event.channel_id, customer_id=customer.id
        )
        # ``conversations.last_inbound_at`` feeds the 24h window check in
        # notification.send_text. Spec 049: on Instagram a comment is not a
        # direct message and does not open the DM window — only the private
        # reply may answer it.
        if not (event.context_message_id or "").startswith("comment:"):
            conversation.last_inbound_at = datetime.now(UTC)
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
        inbound_msg.origin = "customer"
        await session.flush()
        accepted = AcceptedInbound(
            event.tenant_id,
            event.channel_id,
            conversation_id=conversation.id,
            message_id=inbound_msg.id,
        )
        # Spec 049: Instagram / Messenger events carry no name; it is read
        # once per person, after this transaction (a Graph call).
        needs_profile = customer.name is None
        customer_id = customer.id

    if needs_profile and event.provider in _profile_fetchers:
        await fill_profile(event, customer_id=customer_id)
    return accepted


# Spec 049: provider → ``fetch_profile(recipient, tenant_id, channel_id)``,
# injected by bootstrap like the media fetcher.
_profile_fetchers: dict[str, Any] = {}


def set_profile_fetcher(provider: str, fetcher: Any | None) -> None:
    if fetcher is None:
        _profile_fetchers.pop(provider, None)
    else:
        _profile_fetchers[provider] = fetcher


async def fill_profile(event: InboundEvent, *, customer_id: uuid.UUID) -> None:
    """Best-effort: no name, no harm — the inbox shows a generic one."""
    fetcher = _profile_fetchers.get(event.provider)
    if fetcher is None:
        return
    try:
        name = await fetcher(
            recipient=event.user_id, tenant_id=event.tenant_id, channel_id=event.channel_id
        )
    except Exception as exc:
        log.info("pipeline.profile_unavailable", provider=event.provider, error=type(exc).__name__)
        return
    if not name:
        return
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, event.tenant_id):
        await session.execute(
            sa.update(Customer)
            .where(Customer.id == customer_id, Customer.name.is_(None))
            .values(name=name)
        )


# ── 2. Las puertas ────────────────────────────────────────────────────────────


#: Spec 047 (T140): the waiting reasons a routed turn may end with
#: (``contracts/events.md`` §2). Any other reason is a provider failure.
_ROUTER_REASONS: frozenset[str] = frozenset(
    {"provider_failure", "no_model", "turn_limit", "escalated"}
)


@dataclass(frozen=True)
class Gate:
    """Una puerta cerrada: el código de hoy (``skipped``) y su motivo."""

    skipped: str
    reason: str | None


@dataclass(frozen=True)
class TurnFacts:
    """Lo que deciden las puertas de la base, leído en una sola transacción."""

    tenant_status: TenantStatus
    channel_status: ChannelStatus | None
    send_only_channel: bool
    has_active_agent: bool
    ever_had_agent: bool
    agent_active: bool
    out_of_audience: bool
    #: Spec 047 (0190): el agente del número está en pausa, con este motivo.
    agent_pause_reason: str | None = None


#: El motivo de la Bandeja de cada pausa del agente (``events.md`` §2).
_AGENT_PAUSE_WAITING: dict[str, str] = {
    "manual": "paused_agent",
    "no_balance": "no_balance",
    "agent_cap": "agent_cap",
    "client_paused": "paused_client",
    "client_archived": "archived_client",
}


def gate_for(facts: TurnFacts) -> Gate | None:
    """Las puertas que salen de la base, en orden. ``None``: puede contestar
    (falta la bolsa, el modelo y el presupuesto, que se miran después)."""
    if facts.tenant_status in _INACTIVE_STATUSES:
        return Gate("tenant_inactive", _INACTIVE_STATUSES[facts.tenant_status])
    if facts.channel_status == ChannelStatus.PAUSED:
        return Gate("channel_paused", "paused_channel")
    if facts.channel_status == ChannelStatus.DISCONNECTED:
        return Gate("channel_problem", "channel_problem")
    if facts.send_only_channel:
        # Send-only CHANNEL: a number the business uses to push notifications
        # out, with nobody behind it to answer what comes back. Kept, not
        # answered, and not an Inbox conversation (spec 045).
        return Gate("send_only_channel", None)
    if not facts.has_active_agent:
        # No published version: a client that never had an agent (send-only
        # tenant) or an agent still in draft / with only archived versions.
        # Before 047 the last case reached the loader, raised, and died in the
        # DLQ — a message lost to the Inbox.
        return Gate(
            "agent_unpublished" if facts.ever_had_agent else "no_agent", "agent_unpublished"
        )
    if facts.agent_pause_reason is not None:
        # Spec 047 (27.2): a paused agent does not answer; the message is kept
        # and goes to the Inbox with the reason of its pause.
        return Gate(
            "agent_paused", _AGENT_PAUSE_WAITING.get(facts.agent_pause_reason, "paused_agent")
        )
    if facts.out_of_audience:
        # Spec 024: an admin-only agent ignores everyone else (cobranza).
        # Before the takeover: a silenced message never notifies the person
        # in control either (spec 045, R2.3).
        return Gate("not_admin", "out_of_audience")
    if not facts.agent_active:
        # M.3 — a person has taken control of this thread.
        return Gate("human_takeover", "human_takeover")
    return None


async def money_and_model_gate(tenant_id: uuid.UUID) -> tuple[Gate | None, uuid.UUID | None]:
    """La bolsa y el proxy de modelos del partner, en ese orden. Devuelve la
    puerta (si cierra) y el partner, para abrir el turno con su clave virtual."""
    from nexus_api.metering.wallet import allow_channel_turn

    if not await allow_channel_turn(tenant_id):
        log.info("pipeline.skipped.wallet_empty", tenant_id=str(tenant_id))
        return Gate("wallet_empty", "no_balance"), None

    from nexus_api.core.llm_proxy import (
        LLM_PROXY_UNAVAILABLE,
        LLMProxyUnavailable,
        partner_id_for_tenant_standalone,
        resolve_litellm_proxy_optional,
    )

    partner_id = await partner_id_for_tenant_standalone(tenant_id)
    if partner_id is not None:
        try:
            resolve_litellm_proxy_optional(partner_id)
        except LLMProxyUnavailable as exc:
            # Solo se llega aquí con ``llm_proxy_required``: un error de
            # configuración del despliegue. Tiene que verse en el log y en las
            # alarmas, y la conversación espera a una persona («Sin modelo
            # disponible») en vez de perderse.
            log.error(
                "pipeline.skipped.llm_proxy_unavailable",
                tenant_id=str(tenant_id),
                reason=exc.reason,
            )
            return Gate(LLM_PROXY_UNAVAILABLE, "no_model"), partner_id
    return None, partner_id


# ── 3. El turno ───────────────────────────────────────────────────────────────


@dataclass
class _Turn:
    """Lo que el turno leyó de la base al empezar."""

    ref: turns.TurnRef
    facts: TurnFacts
    channel_id: uuid.UUID
    channel_provider: str
    channel_config: dict[str, Any]
    customer_id: uuid.UUID
    user_id: str
    agent_id: uuid.UUID | None
    agent_config_id: uuid.UUID | None
    messages: list[dict[str, Any]] = field(default_factory=list)
    operator_briefing: str | None = None


async def _load_turn(ref: turns.TurnRef) -> _Turn | None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ref.tenant_id):
        tenant_status_raw = await session.scalar(
            sa.select(Tenant.status).where(Tenant.id == ref.tenant_id)
        )
        conversation = await session.get(Conversation, ref.conversation_id)
        if tenant_status_raw is None or conversation is None:
            return None
        customer = await session.get(Customer, conversation.customer_id)
        channel = (
            await session.execute(
                sa.select(Channel.config, Channel.agent_id, Channel.status, Channel.provider).where(
                    Channel.id == conversation.channel_id
                )
            )
        ).first()
        channel_config: dict[str, Any] = (channel[0] if channel else None) or {}
        # Spec 030: the agent that answers on this number. A number without
        # one (every number before spec 030, the Playground's) answers with
        # the principal agent — the oldest active one of the client.
        channel_agent_id: uuid.UUID | None = channel[1] if channel else None
        turn_agent_id: uuid.UUID | None = channel_agent_id or await session.scalar(
            sa.select(Agent.id)
            .where(Agent.status == AgentStatus.ACTIVE.value)
            .order_by(Agent.is_default.desc(), Agent.created_at, Agent.id)
            .limit(1)
        )
        # Spec 047 (requisito 53): Recepción derivó la conversación; desde entonces
        # contesta el destino, con sus puertas (su pausa, su tope, su versión).
        # Vuelve a Recepción al resolverla, tras 24 h sin mensajes o si el
        # destino se archivó.
        handled = await reception.current_handler(
            session, conversation, turn_message_ids=ref.message_ids
        )
        if handled is not None:
            turn_agent_id = handled
        turn_agent = await session.get(Agent, turn_agent_id) if turn_agent_id else None
        agent_pause_reason = (
            (turn_agent.pause_reason or "manual")
            if turn_agent is not None and turn_agent.lifecycle == "paused"
            else None
        )
        active_agent = (
            await session.execute(
                sa.select(AgentConfig.id, AgentConfig.policies)
                .where(AgentConfig.tenant_id == ref.tenant_id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                .where(AgentConfig.agent_id == turn_agent_id)
                .order_by(AgentConfig.version.desc())
                .limit(1)
            )
        ).first()
        ever_had_agent = active_agent is not None or bool(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(AgentConfig)
                .where(AgentConfig.tenant_id == ref.tenant_id)
            )
        )
        policies: dict[str, Any] = (active_agent[1] if active_agent else None) or {}
        user_id = customer.identifier if customer is not None else ""
        rows = (
            (
                await session.execute(
                    sa.select(Message)
                    .where(Message.conversation_id == ref.conversation_id)
                    .where(Message.id.in_(ref.message_ids))
                    .order_by(Message.created_at, Message.id)
                )
            )
            .scalars()
            .all()
        )
        messages = [
            {
                "id": m.id,
                "content": m.content or "",
                "created_at": m.created_at,
                "media_kind": m.media_kind.value
                if hasattr(m.media_kind, "value")
                else m.media_kind,
                "media_s3_key": m.media_s3_key,
                "media_mime": m.media_mime,
                "media_filename": m.media_filename,
                "media_transcript": m.media_transcript,
                "provider_message_id": m.provider_message_id,
            }
            for m in rows
        ]
        # Spec 047 (30.11): el relevo de un eco de la app dura 2 h desde el
        # último; vencido, este mensaje ya lo atiende el agente. Un relevo sin
        # plazo (una persona desde la Bandeja) no caduca.
        if (
            not conversation.agent_active
            and conversation.takeover_until is not None
            and conversation.takeover_until <= datetime.now(UTC)
        ):
            conversation_control.resume(conversation)
            conversation.takeover_until = None
            if conversation.waiting_reason == "human_takeover":
                conversation.waiting_reason = None
        # Bloque C — Operator intervention. ``takeover_context`` is populated
        # by ``PATCH .../agent`` when the operator pauses the agent. The first
        # turn after the operator reactivates consumes it to brief the LLM.
        operator_briefing: str | None = None
        takeover_context = conversation.takeover_context
        if takeover_context is not None and conversation.agent_active:
            started_at_iso = takeover_context.get("started_at")
            operator_briefing = _build_operator_briefing(
                reason=takeover_context.get("reason"),
                notes=takeover_context.get("notes"),
                started_at=started_at_iso,
                operator_id=takeover_context.get("operator_id"),
                operator_messages=await takeover_messages(
                    session, ref.conversation_id, started_at_iso
                ),
            )
        channel_status = ChannelStatus(channel[2]) if channel and channel[2] else None
        facts = TurnFacts(
            tenant_status=TenantStatus(tenant_status_raw),
            channel_status=channel_status,
            send_only_channel=not config_agent_enabled(channel_config),
            has_active_agent=active_agent is not None,
            ever_had_agent=ever_had_agent,
            agent_active=conversation.agent_active,
            # Spec 047 (requisito 32): el canal decide a quién se responde; se
            # lee en cada turno, así un cambio vale desde el siguiente mensaje.
            out_of_audience=audience_suppresses(
                await gate_audience(session, conversation.channel_id),
                policies,
                user_id,
            ),
            agent_pause_reason=agent_pause_reason,
        )
        return _Turn(
            ref=ref,
            facts=facts,
            channel_id=conversation.channel_id,
            channel_provider=str(channel[3]) if channel and channel[3] else "meta",
            channel_config=channel_config,
            customer_id=conversation.customer_id,
            user_id=user_id,
            agent_id=turn_agent_id,
            agent_config_id=active_agent[0] if active_agent else None,
            messages=messages,
            operator_briefing=operator_briefing,
        )


def _mark_attended(conversation: Conversation, messages: list[Message]) -> None:
    """Spec 045 (R1): the Inbox shows what the agent attends or attended. With
    047 that includes a conversation that waits for a person because of a
    gate: it is exactly the one somebody has to see."""
    for msg in messages:
        if conversation.attended_at is None:
            conversation.attended_at = msg.created_at
        if (
            conversation.last_attended_inbound_at is None
            or msg.created_at > conversation.last_attended_inbound_at
        ):
            conversation.last_attended_inbound_at = msg.created_at


_WAIT_SENT_SQL = sa.text(
    "SELECT 1 FROM messages WHERE conversation_id = :c AND direction = 'outbound' "
    "AND content = :body AND created_at > now() - interval '" + WAIT_MESSAGE_WINDOW + "' LIMIT 1"
)


async def _apply_gate(
    turn: _Turn, gate: Gate, *, mark_waiting: bool = True, fresh: bool = True
) -> None:
    """Una puerta no deja contestar: el motivo, la Bandeja y los avisos.

    Todo lo de la base en una transacción; los avisos, después del commit
    (requisitos 2.3 a 2.5, ``contracts/events.md`` §3). ``fresh=False`` es un
    turno que ya se abrió (el modelo falló a mitad): sus mensajes ya están
    atendidos y publicados, y el contacto ya recibió la respuesta neutra.
    """
    ref = turn.ref
    attended = fresh and gate.reason is not None and gate.reason != "out_of_audience"
    mark: inbox_lifecycle.WaitingMark | None = None
    wait_sent = False
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ref.tenant_id):
        conversation = await session.get(Conversation, ref.conversation_id)
        if conversation is None:  # pragma: no cover - borrada a mitad de turno
            return
        rows = list(
            (
                await session.execute(
                    sa.select(Message)
                    .where(Message.conversation_id == ref.conversation_id)
                    .where(Message.id.in_(ref.message_ids))
                    .order_by(Message.created_at, Message.id)
                )
            )
            .scalars()
            .all()
        )
        if gate.reason == "out_of_audience":
            # Spec 024: Conversaciones dice «sin responder · número no permitido».
            for msg in rows:
                msg.skipped_reason = "not_admin"
        if attended:
            _mark_attended(conversation, rows)
        if gate.reason == "human_takeover":
            # Spec 031 (R8.3): la persona que la lleva se entera en su teléfono.
            for msg in rows:
                await push_events.enqueue_message_for_you(session, conversation, inbound_id=msg.id)
        inbox = await inbox_lifecycle.tenant_has_inbox(session, ref.tenant_id)
        if gate.reason is not None and mark_waiting:
            mark = await inbox_lifecycle.mark_waiting_reason(
                session, conversation, reason=gate.reason, inbox=inbox
            )
        if mark is not None and not inbox:
            # Requisito 2.5: sin Bandeja, los destinatarios de escalado del canal.
            await inbox_lifecycle.tell_escalation_recipients(
                session, conversation, reason=mark.reason or gate.reason or ""
            )
        wait_text = str(turn.channel_config.get("wait_message") or "").strip()
        if (
            fresh
            and not inbox
            and wait_text
            and gate.reason in _WAIT_MESSAGE_REASONS
            and turn.facts.tenant_status == TenantStatus.ACTIVE
            and turn.facts.channel_status != ChannelStatus.PAUSED
            and not await session.scalar(
                _WAIT_SENT_SQL, {"c": ref.conversation_id, "body": wait_text}
            )
        ):
            await persist_outbound_message(
                session,
                conversation_id=ref.conversation_id,
                content=wait_text,
                intent=None,
                model=None,
                tool_calls=[],
                actor_kind="system",
            )
            wait_sent = True
        await session.flush()

    for msg_row in turn.messages if fresh else []:
        log.info(
            "inbound.persisted",
            tenant_id=str(ref.tenant_id),
            agent_id=str(turn.agent_id) if turn.agent_id else None,
            conversation_id=str(ref.conversation_id),
            channel_id=str(turn.channel_id),
            message_id=str(msg_row["id"]),
            gate=gate.reason or gate.skipped,
        )
    log.info(
        f"pipeline.skipped.{gate.skipped}",
        tenant_id=str(ref.tenant_id),
        conversation_id=str(ref.conversation_id),
        turn_id=str(ref.turn_id),
        reason=gate.reason,
        channel_role=config_role(turn.channel_config)
        if gate.skipped == "send_only_channel"
        else None,
        wait_message=wait_sent,
    )
    if mark is not None:
        await inbox_lifecycle.announce_waiting(mark)
    if attended:
        # Spec 030: the Inbox shows the new inbound live, without a body.
        for msg_row in turn.messages:
            await publish_inbox_event(
                None,
                tenant_id=ref.tenant_id,
                event="message.new",
                conversation_id=ref.conversation_id,
                message_id=str(msg_row["id"]),
                direction="inbound",
            )
    if gate.reason == "no_balance":
        # Spec 016 (R2.2) y 047 (requisito 2.4): el partner (campana y correo)
        # y la gente del cliente (campana, correo y push), uno por cliente y
        # día. El aviso nunca tumba el turno.
        try:
            from nexus_api.services.wallet_alerts import notify_client_out_of_quota_detached

            await notify_client_out_of_quota_detached(ref.tenant_id)
        except Exception as exc:
            log.warning(
                "pipeline.out_of_quota_notice_failed",
                tenant_id=str(ref.tenant_id),
                error=str(exc),
            )


async def _open_turn(turn: _Turn) -> None:
    """La puerta está abierta: la conversación se atiende y deja de esperar por
    un motivo de puerta que ya no es cierto."""
    ref = turn.ref
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ref.tenant_id):
        conversation = await session.get(Conversation, ref.conversation_id)
        if conversation is None:  # pragma: no cover
            return
        rows = list(
            (
                await session.execute(
                    sa.select(Message).where(
                        Message.conversation_id == ref.conversation_id,
                        Message.id.in_(ref.message_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        _mark_attended(conversation, rows)
        await inbox_lifecycle.release_reason(session, conversation)
    for msg_row in turn.messages:
        log.info(
            "inbound.persisted",
            tenant_id=str(ref.tenant_id),
            agent_id=str(turn.agent_id) if turn.agent_id else None,
            conversation_id=str(ref.conversation_id),
            channel_id=str(turn.channel_id),
            message_id=str(msg_row["id"]),
            gate="open",
        )
        await publish_inbox_event(
            None,
            tenant_id=ref.tenant_id,
            event="message.new",
            conversation_id=ref.conversation_id,
            message_id=str(msg_row["id"]),
            direction="inbound",
        )


_MEDIA_HEADERS = {
    "audio": "[transcripción de audio]: ",
    "video": "[transcripción de audio]: ",
    "image": "[descripción de imagen]: ",
    "sticker": "[descripción de imagen]: ",
}


async def _process_media(turn: _Turn) -> dict[uuid.UUID, str]:
    """Block N: transcribe / describe the turn's attachments, behind the gates
    (it costs). Failures are non-fatal: the agent answers «no pude leerlo»."""
    notes: dict[uuid.UUID, str] = {}
    transcripts: dict[uuid.UUID, str] = {}
    for row in turn.messages:
        if not (row["media_kind"] and row["media_s3_key"]):
            continue
        if row["media_transcript"]:
            # A retried turn: what the first attempt read, without paying again.
            header = _MEDIA_HEADERS.get(row["media_kind"], "[texto del documento]: ")
            notes[row["id"]] = f"{header}{row['media_transcript']}"
            continue
        processed: ProcessedMedia | None = None
        # CP-23 (0083): the processor's own ``record_*`` calls only land inside
        # an open usage turn — the media leg gets its own, keyed by the
        # provider message id (stable across a replay → idempotent rows).
        media_turn_id = f"media:{row['provider_message_id'] or uuid.uuid4().hex}"
        try:
            async with usage_turn(tenant_id=turn.ref.tenant_id, turn_id=media_turn_id):
                processed = await get_media_processor().process(
                    s3_key=row["media_s3_key"],
                    media_kind=row["media_kind"],
                    mime_type=row["media_mime"],
                    filename=row["media_filename"],
                )
        except Exception as exc:
            log.warning(
                "pipeline.media_processor.failed",
                tenant_id=str(turn.ref.tenant_id),
                media_kind=row["media_kind"],
                error=str(exc),
            )
        # One inbound attachment = one ``media.<kind>`` unit (+ seconds for
        # audio when the provider reported them), processed or not.
        await record_media_unit(
            tenant_id=turn.ref.tenant_id,
            kind=row["media_kind"],
            provider=turn.channel_provider,
            provider_message_id=row["provider_message_id"],
            audio_seconds=processed.duration_seconds if processed else None,
        )
        if processed is not None and processed.text:
            header = _MEDIA_HEADERS.get(processed.kind, "[texto del documento]: ")
            notes[row["id"]] = f"{header}{processed.text}"
            transcripts[row["id"]] = processed.text
        elif processed is not None and processed.error:
            notes[row["id"]] = f"[media-processing-error]: {processed.error}"
    if transcripts:
        # What the LLM actually read, for the panel and analytics.
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, turn.ref.tenant_id):
            for message_id, text in transcripts.items():
                await session.execute(
                    sa.update(Message)
                    .where(Message.id == message_id)
                    .values(media_transcript=text)
                    .execution_options(synchronize_session=False)
                )
    return notes


def _user_message(turn: _Turn, notes: dict[uuid.UUID, str]) -> str:
    """Los mensajes de la ráfaga, en orden, cada uno con lo que se leyó de su
    adjunto. Es lo que el agente contesta, de una vez."""
    parts: list[str] = []
    for row in turn.messages:
        text = row["content"]
        note = notes.get(row["id"])
        parts.append(f"{text}\n{note}" if note else text)
    return "\n".join(p for p in parts if p)


def _coalesce_window_ms() -> int:
    """La ventana de agrupación de la plataforma, para el evento ``turn.coalesced``."""
    try:
        from nexus_worker.config import get_worker_settings

        return int(get_worker_settings().runner_coalesce_window_ms)
    except Exception:  # pragma: no cover - el evento no puede tumbar el turno
        return 0


@dataclass(frozen=True)
class _Outcome:
    payload: dict[str, Any]
    state: str
    reason: str | None = None


async def run_turn(
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    pipeline: Any,
    provider: str = "meta",
) -> dict[str, Any]:
    """El turno de la conversación: toma, puertas y grafo (ver el módulo).

    Devuelve ``{"turn": "busy"}`` si otro worker la está atendiendo y
    ``{"turn": "none"}`` si otro turno ya se llevó sus mensajes. Un fallo se
    reintenta con el mismo ``turn_id`` (``TurnRetry``); al agotar los intentos
    la conversación pasa a una persona con ``provider_failure``.
    """
    claim = await turns.claim_turn(tenant_id, conversation_id)
    if claim.kind != "claimed" or claim.turn is None:
        return {"turn": claim.kind, "conversation_id": str(conversation_id)}
    ref = claim.turn
    heartbeat = asyncio.create_task(turns.keep_alive(ref))
    try:
        with turns.turn_scope(ref):
            outcome = await _run_claimed(ref, pipeline=pipeline, provider=provider)
    except Exception as exc:
        heartbeat.cancel()
        if ref.attempt >= turns.MAX_TURN_ATTEMPTS:
            # Requisito 1.5: nada de turnos a medias sin rastro.
            log.error(
                "turn.failed",
                tenant_id=str(tenant_id),
                conversation_id=str(conversation_id),
                turn_id=str(ref.turn_id),
                attempt=ref.attempt,
                error=str(exc),
            )
            await turns.finish_turn(ref, state="failed", reason="provider_failure")
            loaded = await _load_turn(ref)
            if loaded is not None:
                with turns.turn_scope(ref):
                    await _apply_gate(loaded, Gate("turn_failed", "provider_failure"))
            return {
                "failed": True,
                "reason": "provider_failure",
                "turn_id": str(ref.turn_id),
                "conversation_id": str(conversation_id),
            }
        await turns.release_for_retry(ref, error=str(exc))
        raise turns.TurnRetry(ref.turn_id, ref.attempt, str(exc)) from exc
    heartbeat.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await heartbeat
    await turns.finish_turn(ref, state=outcome.state, reason=outcome.reason)
    return outcome.payload


def _skipped_payload(turn: _Turn, gate: Gate, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "skipped": gate.skipped,
        "reason": gate.reason,
        "turn_id": str(turn.ref.turn_id),
        "conversation_id": str(turn.ref.conversation_id),
        "inbound_message_id": str(turn.messages[-1]["id"]) if turn.messages else None,
    }
    if gate.skipped == "tenant_inactive":
        payload["tenant_status"] = turn.facts.tenant_status.value
    payload.update(extra)
    return payload


async def _run_claimed(ref: turns.TurnRef, *, pipeline: Any, provider: str) -> _Outcome:
    turn = await _load_turn(ref)
    if turn is None:
        log.warning("pipeline.skipped.tenant_unknown", tenant_id=str(ref.tenant_id))
        return _Outcome({"skipped": "tenant_unknown"}, "gated", None)
    ref.agent_id = turn.agent_id
    if len(turn.messages) > 1:
        log.info(
            "turn.coalesced",
            tenant_id=str(ref.tenant_id),
            agent_id=str(turn.agent_id) if turn.agent_id else None,
            turn_id=str(ref.turn_id),
            conversation_id=str(ref.conversation_id),
            message_count=len(turn.messages),
            window_ms=_coalesce_window_ms(),
        )

    gate = gate_for(turn.facts)
    partner_id: uuid.UUID | None = None
    if gate is None:
        gate, partner_id = await money_and_model_gate(ref.tenant_id)
    if gate is not None:
        await _apply_gate(turn, gate)
        return _Outcome(_skipped_payload(turn, gate), "gated", gate.reason)

    # WP-20 — presupuesto, ANTES de abrir el turno: es el único punto en el
    # que todavía no se ha gastado nada. El veredicto agrega tenant y partner y
    # gana el más restrictivo. Import diferido: ligar ``get_redis`` al cargar el
    # módulo esquivaría cualquier sustitución del cliente (fixtures, runbooks).
    from nexus_api.core.redis_client import get_redis

    budget = await evaluate_budget(get_redis(), tenant_id=ref.tenant_id)
    if budget.is_hard:
        # No se abre turno, pero el cliente final NO se queda sin respuesta
        # (``runtime/budget_gate.py``), y la conversación espera a una persona
        # con su motivo (requisito 44.8): lo marca el propio corte.
        gate = Gate("budget_hard_limit", "turn_limit")
        await _apply_gate(turn, gate, mark_waiting=False)
        warned = await apply_hard_cutoff(
            tenant_id=ref.tenant_id, conversation_id=ref.conversation_id, verdict=budget
        )
        return _Outcome(_skipped_payload(turn, gate, handoff_sent=warned), "gated", gate.reason)

    await _open_turn(turn)
    if partner_id is not None:
        from nexus_api.core.llm_proxy import llm_proxy_partner_scope

        with llm_proxy_partner_scope(partner_id):
            return await _invoke(turn, pipeline=pipeline, provider=provider, budget=budget)
    return await _invoke(turn, pipeline=pipeline, provider=provider, budget=budget)


@dataclass(frozen=True)
class _Handover:
    """Recepción derivó en esta pasada: quién contesta ahora y qué le llega."""

    agent_id: uuid.UUID
    agent_config_id: uuid.UUID
    brief: str


async def _handed_over(turn: _Turn) -> _Handover | None:
    """Spec 047 (requisito 53.2): ¿cambió en esta pasada quién contesta en la
    conversación? Lo dice la base —la herramienta de Recepción ya confirmó—, no
    el estado del grafo. ``None``: nadie derivó, o el destino ya no puede
    contestar (sin versión publicada)."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, turn.ref.tenant_id):
        conversation = await session.get(Conversation, turn.ref.conversation_id)
        if conversation is None:  # pragma: no cover - borrada a mitad de turno
            return None
        now_answers = await reception.agent_for_conversation(session, conversation)
        if now_answers is None or now_answers == turn.agent_id:
            return None
        config_id = await session.scalar(
            sa.select(AgentConfig.id).where(
                AgentConfig.agent_id == now_answers, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
        if config_id is None:
            return None
        payload = await reception.last_handoff(session, conversation.id, to_agent_id=now_answers)
    return _Handover(
        agent_id=now_answers, agent_config_id=config_id, brief=reception.brief(payload)
    )


async def _invoke(turn: _Turn, *, pipeline: Any, provider: str, budget: Any) -> _Outcome:
    ref = turn.ref
    user_message = _user_message(turn, await _process_media(turn))
    # Bloque C — prepend the operator briefing (if any) so the LLM sees the
    # "what the human did while you were paused" context before the
    # customer's message. Delimited so the model never echoes it back.
    if turn.operator_briefing is not None:
        user_message = f"{turn.operator_briefing}\n\n[Mensaje del cliente]\n{user_message}"

    final = await _run_graph(
        turn,
        pipeline=pipeline,
        provider=provider,
        budget=budget,
        user_message=user_message,
        usage_key=str(ref.turn_id),
    )
    # Spec 047 (requisito 53.2): si Recepción derivó, en este mismo turno
    # contesta el destino —mismo número, mismo hilo, mismo mensaje—, con su
    # versión, sus herramientas y su conocimiento, y con el resumen del motivo.
    # Cada pasada mide con su agente y su clave (53.7). Como mucho
    # ``MAX_HOPS`` pasadas más: la siguiente derivación ya la corta la
    # herramienta y pasa la conversación a una persona.
    for hop in range(1, reception.MAX_HOPS + 1):
        handover = await _handed_over(turn)
        if handover is None:
            break
        turn = replace(turn, agent_id=handover.agent_id, agent_config_id=handover.agent_config_id)
        ref.agent_id = handover.agent_id
        final = await _run_graph(
            turn,
            pipeline=pipeline,
            provider=provider,
            budget=budget,
            user_message=user_message,
            usage_key=f"{ref.turn_id}:handoff:{hop}",
            addendum=handover.brief,
        )
    return await _close_turn(turn, final)


async def _run_graph(
    turn: _Turn,
    *,
    pipeline: Any,
    provider: str,
    budget: Any,
    user_message: str,
    usage_key: str,
    addendum: str | None = None,
) -> dict[str, Any]:
    """Una pasada del grafo con el agente de ``turn``. ``usage_key`` ancla la
    medición de la pasada; ``addendum``, lo que el agente lee antes del mensaje
    (el resumen de Recepción en una derivación)."""
    ref = turn.ref
    state = new_state(
        tenant_id=ref.tenant_id,
        channel_id=turn.channel_id,
        user_id=turn.user_id,
        conversation_id=ref.conversation_id,
        customer_id=turn.customer_id,
        # The turn's id is its first message: what the history loader leaves
        # out, and what anchors usage idempotency (``{turn}:{seq}:{meter}``)
        # and the channel debit (``channel:{turn}``) across retries.
        inbound_message_id=ref.turn_id,
        user_message=user_message,
        system_addendum=addendum,
    )
    if turn.agent_id is not None:
        # Spec 030: the pipeline loads THIS agent's prompt, tools and version.
        state["agent_id"] = str(turn.agent_id)
    if budget.level == "soft":
        # Degradación: modelo barato y/o grader apagado. El cliente final no
        # percibe más que, quizá, una respuesta algo menos pulida.
        state["budget_degrade_model"] = budget.degrade_model
        state["budget_disable_grader"] = budget.disable_grader
        log.info(
            "budget.soft_degrade",
            tenant_id=str(ref.tenant_id),
            scope=budget.scope,
            action=budget.soft_action,
        )
    thread_id = make_thread_id(ref.tenant_id, turn.channel_id, turn.user_id)
    config = {"configurable": {"thread_id": thread_id}}

    log.info(
        "pipeline.run.start",
        tenant_id=str(ref.tenant_id),
        channel_id=str(turn.channel_id),
        turn_id=str(ref.turn_id),
        attempt=ref.attempt,
        thread_id=thread_id,
    )
    # WP-17: el buffer de consumo del turno envuelve la invocación del grafo:
    # ahí dentro caen TODAS las llamadas al LLM (classify, respond, grader,
    # multimodal). Publica al salir, también si el turno revienta: esos tokens
    # ya se gastaron. El ``turn_id`` es el mismo en cada reintento. Spec 047
    # (53.7): la pasada del destino de Recepción lleva su propia clave
    # (``{turno}:handoff:{n}``) y su agente: su gasto es suyo y no se deduplica
    # contra el de Recepción.
    async with usage_turn(
        tenant_id=ref.tenant_id,
        turn_id=usage_key,
        conversation_id=ref.conversation_id,
        agent_config_id=turn.agent_config_id,
        agent_id=turn.agent_id,
    ):
        with trace_turn(
            tenant_id=ref.tenant_id,
            channel_id=turn.channel_id,
            user_id_inside_channel=turn.user_id,
            name="agent.turn",
            metadata={"thread_id": thread_id, "provider": provider},
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
        tenant_id=str(ref.tenant_id),
        turn_id=str(ref.turn_id),
        intent=final.get("intent"),
        response_present=bool(final.get("response")),
    )
    out: dict[str, Any] = final
    return out


async def _close_turn(turn: _Turn, final: dict[str, Any]) -> _Outcome:
    """Lo que queda del turno tras la última pasada del grafo."""
    ref = turn.ref
    # Requisito 1.5: el modelo (o su proveedor) falló sin recuperación —el
    # router agotó reintentos y alternativas—. El contacto ya tiene la
    # respuesta neutra del agente; la conversación pasa a una persona con su
    # motivo y se avisa a quien toca. Solo en el camino de canal: el
    # Playground no tiene Bandeja.
    # Spec 047 (T140): a turn that went through the router may also end in a
    # ``handoff`` with its own reason (no model, turn limit, escalated). Only
    # the reasons the router gives are taken; anything else is a provider
    # failure, as before. Today's agents never carry a reason.
    failure = final.get("turn_failure")
    reason: str | None = None
    if isinstance(failure, dict) and failure.get("kind") in ("llm_failed", "handoff"):
        given = failure.get("reason")
        reason = given if given in _ROUTER_REASONS else "provider_failure"
        await _apply_gate(turn, Gate(str(failure["kind"]), reason), fresh=False)

    # Bloque C — the briefing was delivered: clear ``takeover_context`` so the
    # next turn doesn't replay it. Outside the pipeline on purpose: a failure
    # leaves it set so the retry still receives the briefing.
    if turn.operator_briefing is not None:
        sm = get_sessionmaker()
        async with sm() as cleanup_session, tenant_scoped_session(cleanup_session, ref.tenant_id):
            await cleanup_session.execute(
                sa.update(Conversation)
                .where(Conversation.id == ref.conversation_id)
                .values(takeover_context=None)
            )

    payload = dict(final)
    payload.setdefault("turn_id", str(ref.turn_id))
    return _Outcome(payload, "done", reason)


# ── 4. Las dos cosas seguidas ─────────────────────────────────────────────────


async def process_inbound(
    event: InboundEvent,
    *,
    pipeline: Any,
) -> dict[str, Any]:
    """Guarda el entrante y corre el turno de su conversación ahora, sin ventana.

    Si otro worker está atendiendo esa conversación, el mensaje queda guardado
    sin turno y devuelve ``{"turn": "busy"}``: quien llama lo programa (el
    consumidor) o lo recoge el siguiente turno de la conversación.
    """
    return await _process_inbound(event, pipeline=pipeline)


async def _process_inbound(
    event: InboundEvent,
    *,
    pipeline: Any,
) -> dict[str, Any]:
    accepted = await accept_inbound(event)
    if accepted.skipped is not None or accepted.conversation_id is None:
        return {"skipped": accepted.skipped or "tenant_unknown"}
    result = await run_turn(
        tenant_id=event.tenant_id,
        conversation_id=accepted.conversation_id,
        pipeline=pipeline,
        provider=event.provider,
    )
    result.setdefault("conversation_id", str(accepted.conversation_id))
    if accepted.message_id is not None:
        result.setdefault("inbound_message_id", str(accepted.message_id))
    return result


__all__ = [
    "AcceptedInbound",
    "Gate",
    "InboundEvent",
    "TurnFacts",
    "accept_inbound",
    "gate_for",
    "money_and_model_gate",
    "process_inbound",
    "run_turn",
    "suppression_reason",
    "takeover_messages",
]
