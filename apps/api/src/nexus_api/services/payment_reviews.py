"""Spec 025: payment reviews — open one, and resolve it from a button tap.

``open_review`` is what ``payments.request_review`` runs: it records the
review and queues, for every reviewer whose 24h window is open, the receipt
and a message with two buttons. ``resolve_tap`` is what the Meta webhook
runs when a reviewer taps one: the first tap wins, and three fixed texts are
queued — to the reviewer who tapped, to the other reviewers, and to the
customer. No model call: the outcome is decided by the button.

Every message is an outbound ``Message`` row in ``pending``; the
``nexus_outbound`` trigger wakes the dispatcher, which sends and meters it.
Nothing here talks to Meta.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.admin_gate import sender_is_admin
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    Conversation,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    PaymentReview,
    PaymentReviewNotice,
)
from nexus_api.db.models.payment_review import (
    DELIVERY_INTERACTIVE,
    DELIVERY_UNDELIVERED,
    METHOD_LINK,
    REVIEW_CONFIRMED,
    REVIEW_INFORMED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
)
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.agent_payment_review import Reviewer

log = structlog.get_logger(__name__)

SERVICE_WINDOW = timedelta(hours=24)
TAP_PREFIX = "prv:"
CONFIRM = "ok"
REJECT = "no"
#: WooCommerce statuses that mean the gateway already took the money.
PAID_ORDER_STATUSES = frozenset({"processing", "completed"})
#: How far back the receipt is looked for in the customer's conversation.
RECEIPT_LOOKBACK = 5

SUMMARY_FIELDS = ("product", "modality", "place", "date", "slot", "total", "customer_name")

# ── texts ────────────────────────────────────────────────────────────────

MSG_CUSTOMER_PENDING = (
    "Recibimos tu comprobante. Lo estamos verificando y te confirmo por acá en unos minutos."
)
MSG_CUSTOMER_LINK_PAID = "Tu pago ya figura en la tienda. El equipo prepara tu pedido."
MSG_CUSTOMER_CONFIRMED = "Tu pago está verificado. Tu pedido queda en preparación"
MSG_CUSTOMER_REJECTED = (
    "No pudimos verificar tu transferencia. Una persona del equipo te escribe en un momento "
    "para revisarlo contigo."
)


def now() -> datetime:
    return datetime.now(UTC)


def window_open(conversation: Conversation | None, *, at: datetime | None = None) -> bool:
    """WhatsApp's customer-service window: the other side wrote in the last 24h."""
    if conversation is None or conversation.last_inbound_at is None:
        return False
    return (at or now()) - conversation.last_inbound_at < SERVICE_WINDOW


def button_id(token: str, action: str) -> str:
    return f"{TAP_PREFIX}{token}:{action}"


def parse_tap(payload_id: str | None) -> tuple[str, str] | None:
    """``prv:<token>:ok|no`` → ``(token, action)``; anything else → ``None``."""
    if not payload_id or not payload_id.startswith(TAP_PREFIX):
        return None
    parts = payload_id[len(TAP_PREFIX) :].split(":")
    if len(parts) != 2 or parts[1] not in (CONFIRM, REJECT) or not parts[0]:
        return None
    return parts[0], parts[1]


def _clean(summary: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in SUMMARY_FIELDS:
        value = summary.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def _pretty_phone(identifier: str) -> str:
    digits = "".join(ch for ch in identifier if ch.isdigit())
    return f"+{digits}" if digits else identifier


def notice_body(
    *,
    business: str,
    summary: dict[str, str],
    customer_phone: str,
    method: str,
    order_id: str | None,
    order_status: str | None,
    receipts: int,
) -> str:
    """The text the reviewers read. Lines are omitted when unknown."""
    lines = [f"*Pago por revisar · {business}*"]
    who = summary.get("customer_name")
    phone = _pretty_phone(customer_phone)
    lines.append(f"Cliente: {who} ({phone})" if who else f"Cliente: {phone}")
    if summary.get("product"):
        lines.append(summary["product"])
    where = " · ".join(
        part
        for part in (
            " a ".join(p for p in (summary.get("modality"), summary.get("place")) if p),
            summary.get("date"),
            summary.get("slot"),
        )
        if part
    )
    if where:
        lines.append(where)
    if method == METHOD_LINK:
        state = order_status or "sin estado"
        pay = (
            f"Pago en línea · pedido {order_id} · {state}"
            if order_id
            else f"Pago en línea · {state}"
        )
    else:
        pay = "Transferencia"
    lines.append(f"Total: {summary['total']} · {pay}" if summary.get("total") else pay)
    if method != METHOD_LINK and receipts == 0:
        lines.append("El comprobante no llegó como archivo, revisa la conversación.")
    if not summary.get("product"):
        lines.append("Pedido sin completar en el chat.")
    return "\n".join(lines)


def customer_confirmed_text(summary: dict[str, Any]) -> str:
    clean = _clean(summary)
    when = ", ".join(p for p in (clean.get("date"), clean.get("slot")) if p)
    return f"{MSG_CUSTOMER_CONFIRMED} para el {when}." if when else f"{MSG_CUSTOMER_CONFIRMED}."


# ── open ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OpenedReview:
    review: PaymentReview
    notified: int
    unreachable: int
    already_pending: bool
    message_to_customer: str


def _outbound(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    content: str,
    *,
    interactive: dict[str, Any] | None = None,
    media_from: Message | None = None,
) -> Message:
    return Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=content,
        tool_calls=[{"tool": "payments.request_review"}],
        actor_kind="system",
        interactive_payload=interactive,
        media_kind=media_from.media_kind if media_from else None,
        media_s3_key=media_from.media_s3_key if media_from else None,
        media_mime=media_from.media_mime if media_from else None,
        media_filename=media_from.media_filename if media_from else None,
    )


async def _recent_receipts(session: AsyncSession, conversation_id: uuid.UUID) -> list[Message]:
    """The files the customer sent since the agent last spoke: that is the
    receipt. A product photo from earlier in the chat is not forwarded."""
    rows = (
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(RECEIPT_LOOKBACK)
            )
        )
        .scalars()
        .all()
    )
    out: list[Message] = []
    for m in rows:
        if m.direction == MessageDirection.OUTBOUND:
            break
        if m.media_s3_key and m.media_kind in ("image", "document"):
            out.append(m)
    return list(reversed(out))


async def _reviewer_conversation(
    session: AsyncSession, *, channel_id: uuid.UUID, phone: str
) -> Conversation:
    from nexus_worker.persistence.messages import (
        upsert_conversation_for_customer,
        upsert_customer,
    )

    identifier = "".join(ch for ch in phone if ch.isdigit())
    customer = await upsert_customer(session, identifier=identifier)
    conversation: Conversation = await upsert_conversation_for_customer(
        session, channel_id=channel_id, customer_id=customer.id
    )
    return conversation


async def open_review(
    session: AsyncSession,
    *,
    conversation: Conversation,
    reviewers: list[Reviewer],
    business: str,
    method: str,
    summary: dict[str, Any],
    order_id: str | None = None,
    order_status: str | None = None,
) -> OpenedReview:
    """Record a review and queue the notices. The caller commits."""
    tenant_id = require_current_tenant()
    receipts = await _recent_receipts(session, conversation.id)

    pending = (
        await session.execute(
            select(PaymentReview).where(
                PaymentReview.conversation_id == conversation.id,
                PaymentReview.status == REVIEW_PENDING,
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        known = set(pending.receipt_message_ids or [])
        added = [m.id for m in receipts if m.id not in known]
        if added:
            pending.receipt_message_ids = [*pending.receipt_message_ids, *added]
        return OpenedReview(
            review=pending,
            notified=0,
            unreachable=0,
            already_pending=True,
            message_to_customer=MSG_CUSTOMER_PENDING,
        )

    clean = _clean(summary)
    paid_link = method == METHOD_LINK and (order_status or "").lower() in PAID_ORDER_STATUSES
    review = PaymentReview(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        channel_id=conversation.channel_id,
        token=secrets.token_hex(6),
        method=method,
        status=REVIEW_INFORMED if paid_link else REVIEW_PENDING,
        summary=clean,
        order_id=order_id,
        order_status=order_status,
        receipt_message_ids=[m.id for m in receipts],
    )
    session.add(review)
    await session.flush()

    customer = await session.get(Customer, conversation.customer_id)
    body = notice_body(
        business=business,
        summary=clean,
        customer_phone=customer.identifier if customer else "",
        method=method,
        order_id=order_id,
        order_status=order_status,
        receipts=len(receipts),
    )
    buttons = None
    if not paid_link:
        buttons = {
            "body": body[:1024],
            "buttons": [
                {"id": button_id(review.token, CONFIRM), "title": "Confirmar pago"},
                {"id": button_id(review.token, REJECT), "title": "Rechazar pago"},
            ],
        }

    notified = unreachable = 0
    for reviewer in reviewers:
        conv = await _reviewer_conversation(
            session, channel_id=conversation.channel_id, phone=reviewer.phone
        )
        if not window_open(conv):
            unreachable += 1
            session.add(
                PaymentReviewNotice(
                    tenant_id=tenant_id,
                    review_id=review.id,
                    reviewer_phone=reviewer.phone,
                    reviewer_name=reviewer.name,
                    reviewer_conversation_id=conv.id,
                    delivery=DELIVERY_UNDELIVERED,
                    reason="window_closed",
                )
            )
            continue
        for receipt in receipts:
            session.add(_outbound(tenant_id, conv.id, "[comprobante]", media_from=receipt))
        main = _outbound(tenant_id, conv.id, body, interactive=buttons)
        session.add(main)
        await session.flush()
        session.add(
            PaymentReviewNotice(
                tenant_id=tenant_id,
                review_id=review.id,
                reviewer_phone=reviewer.phone,
                reviewer_name=reviewer.name,
                reviewer_conversation_id=conv.id,
                delivery=DELIVERY_INTERACTIVE,
                message_id=main.id,
            )
        )
        notified += 1

    await AuditRepository(session).record(
        actor="system:agent",
        action="payment_review.opened",
        target=f"conversation:{conversation.id}",
        after={
            "review_id": str(review.id),
            "method": method,
            "status": review.status,
            "notified": notified,
            "unreachable": unreachable,
        },
    )
    await session.flush()
    log.info(
        "payment_review.opened",
        review_id=str(review.id),
        method=method,
        notified=notified,
        unreachable=unreachable,
    )
    return OpenedReview(
        review=review,
        notified=notified,
        unreachable=unreachable,
        already_pending=False,
        message_to_customer=MSG_CUSTOMER_LINK_PAID if paid_link else MSG_CUSTOMER_PENDING,
    )


# ── resolve ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TapOutcome:
    """What a tap did. ``resolved`` is False for a late or foreign tap."""

    handled: bool
    resolved: bool = False
    status: str | None = None


def _verb(status: str) -> str:
    return "confirmó" if status == REVIEW_CONFIRMED else "rechazó"


async def resolve_tap(
    session: AsyncSession,
    *,
    payload_id: str,
    sender: str,
) -> TapOutcome:
    """Resolve a review from a reviewer's button tap. The caller commits.

    Runs inside the session of the tenant that owns the business number the
    tap arrived on: a token from another tenant simply does not exist (RLS).
    """
    parsed = parse_tap(payload_id)
    if parsed is None:
        return TapOutcome(handled=False)
    token, action = parsed
    tenant_id = require_current_tenant()

    review = (
        await session.execute(select(PaymentReview).where(PaymentReview.token == token))
    ).scalar_one_or_none()
    if review is None:
        log.info("payment_review.tap_unknown_token")
        return TapOutcome(handled=True)

    notices = (
        (
            await session.execute(
                select(PaymentReviewNotice).where(PaymentReviewNotice.review_id == review.id)
            )
        )
        .scalars()
        .all()
    )
    mine = next((n for n in notices if sender_is_admin(sender, [n.reviewer_phone])), None)
    if mine is None or mine.reviewer_conversation_id is None:
        log.warning("payment_review.tap_from_stranger", review_id=str(review.id))
        return TapOutcome(handled=True)

    new_status = REVIEW_CONFIRMED if action == CONFIRM else REVIEW_REJECTED
    at = now()
    # The tap is an inbound from the reviewer: their 24h window is open again,
    # which is what lets the acknowledgement below go out as free text.
    tapper_conv = await session.get(Conversation, mine.reviewer_conversation_id)
    if tapper_conv is not None:
        tapper_conv.last_inbound_at = at
    won = (
        await session.execute(
            update(PaymentReview)
            .where(PaymentReview.id == review.id, PaymentReview.status == REVIEW_PENDING)
            .values(
                status=new_status,
                resolved_at=at,
                resolved_by_phone=mine.reviewer_phone,
                resolved_by_name=mine.reviewer_name,
                updated_at=at,
            )
            .returning(PaymentReview.id)
        )
    ).scalar_one_or_none()

    if won is None:
        await session.refresh(review)
        who = review.resolved_by_name or review.resolved_by_phone or "otra persona"
        text = (
            f"Este pago ya lo {_verb(review.status)} {who}."
            if review.status in (REVIEW_CONFIRMED, REVIEW_REJECTED)
            else "Este pago no necesita revisión."
        )
        session.add(_outbound(tenant_id, mine.reviewer_conversation_id, text))
        return TapOutcome(handled=True, resolved=False, status=review.status)

    summary = review.summary or {}
    client = summary.get("customer_name") or "el cliente"
    me = mine.reviewer_name or mine.reviewer_phone
    ack = (
        "Confirmado. Ya le avisamos al cliente."
        if new_status == REVIEW_CONFIRMED
        else "Rechazado. El agente deja la conversación para que la tome una persona."
    )
    session.add(_outbound(tenant_id, mine.reviewer_conversation_id, ack))
    for other in notices:
        if other.id == mine.id or other.delivery != DELIVERY_INTERACTIVE:
            continue
        if other.reviewer_conversation_id is None:
            continue
        session.add(
            _outbound(
                tenant_id,
                other.reviewer_conversation_id,
                f"{me} {_verb(new_status)} el pago de {client}.",
            )
        )

    customer_conv = await session.get(Conversation, review.conversation_id)
    notified = window_open(customer_conv, at=at)
    if customer_conv is not None and notified:
        text = (
            customer_confirmed_text(summary)
            if new_status == REVIEW_CONFIRMED
            else MSG_CUSTOMER_REJECTED
        )
        session.add(_outbound(tenant_id, customer_conv.id, text))
    if customer_conv is not None and new_status == REVIEW_REJECTED:
        customer_conv.agent_active = False
        customer_conv.agent_active_version = (customer_conv.agent_active_version or 0) + 1
        customer_conv.takeover_context = {
            "reason": "payment_rejected",
            "notes": f"{me} rechazó el pago por WhatsApp.",
            "started_at": at.isoformat(),
            "operator_id": "payment_review",
        }
    await session.execute(
        update(PaymentReview)
        .where(PaymentReview.id == review.id)
        .values(customer_notified=notified)
    )
    await AuditRepository(session).record(
        actor=f"reviewer:{mine.reviewer_phone}",
        action="payment_review.resolved",
        target=f"conversation:{review.conversation_id}",
        before={"status": REVIEW_PENDING},
        after={
            "review_id": str(review.id),
            "status": new_status,
            "by": mine.reviewer_name,
            "customer_notified": notified,
        },
    )
    log.info(
        "payment_review.resolved",
        review_id=str(review.id),
        status=new_status,
        customer_notified=notified,
    )
    return TapOutcome(handled=True, resolved=True, status=new_status)


__all__ = [
    "MSG_CUSTOMER_LINK_PAID",
    "MSG_CUSTOMER_PENDING",
    "MSG_CUSTOMER_REJECTED",
    "OpenedReview",
    "TapOutcome",
    "button_id",
    "customer_confirmed_text",
    "notice_body",
    "open_review",
    "parse_tap",
    "resolve_tap",
    "window_open",
]
