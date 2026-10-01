"""Spec 025: a review opens with buttons, and the first tap resolves it.

Runs against Postgres with RLS on (``nexus_app`` role), the way the tool and
the webhook run in production. No Meta call is made: every message is a
pending outbound row the dispatcher would send.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    PaymentReview,
    PaymentReviewNotice,
)
from nexus_api.services.agent_payment_review import Reviewer
from nexus_api.services.payment_reviews import (
    MSG_CUSTOMER_LINK_PAID,
    MSG_CUSTOMER_PENDING,
    MSG_CUSTOMER_REJECTED,
    button_id,
    open_review,
    parse_tap,
    resolve_tap,
)

pytestmark = pytest.mark.asyncio

DANIELA = Reviewer(phone="+56991280655", name="Daniela")
PEDRO = Reviewer(phone="+56989829063", name="Pedro")
SUMMARY = {
    "product": "Ramo de 12 rosas rojas",
    "modality": "Envío",
    "place": "Ñuñoa",
    "date": "viernes 3 de octubre",
    "slot": "13:00 a 17:00",
    "total": "$34.990",
    "customer_name": "Camila",
}


async def _scope(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(text("SET LOCAL ROLE nexus_app"))


async def _world(session, tenant_id: uuid.UUID, *, open_for: tuple[str, ...]) -> Conversation:
    """A channel, a customer who just sent a receipt image, and reviewer
    conversations whose window is open only for the phones in ``open_for``."""
    await _scope(session, tenant_id)
    ch = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=str(uuid.uuid4()),
    )
    buyer = Customer(tenant_id=tenant_id, identifier="56912345678")
    session.add_all([ch, buyer])
    await session.flush()
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=ch.id,
        customer_id=buyer.id,
        last_inbound_at=datetime.now(UTC),
    )
    session.add(conv)
    await session.flush()
    session.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            content="[media:image]",
            media_kind="image",
            media_s3_key="t/receipt.jpg",
            media_mime="image/jpeg",
        )
    )
    for reviewer in (DANIELA, PEDRO):
        digits = reviewer.phone.lstrip("+")
        cu = Customer(tenant_id=tenant_id, identifier=digits)
        session.add(cu)
        await session.flush()
        last = datetime.now(UTC) - (
            timedelta(hours=1) if reviewer.phone in open_for else timedelta(days=3)
        )
        session.add(
            Conversation(
                tenant_id=tenant_id, channel_id=ch.id, customer_id=cu.id, last_inbound_at=last
            )
        )
    await session.flush()
    return conv


async def _outbound_to(session, phone: str) -> list[Message]:
    digits = phone.lstrip("+")
    rows = await session.execute(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(Customer.identifier == digits, Message.direction == MessageDirection.OUTBOUND)
        .order_by(Message.created_at)
    )
    return list(rows.scalars().all())


async def _customer_outbound(session, conv: Conversation) -> list[str]:
    rows = await session.execute(
        select(Message.content).where(
            Message.conversation_id == conv.id, Message.direction == MessageDirection.OUTBOUND
        )
    )
    return [r for (r,) in rows.all()]


async def test_the_button_id_round_trips_and_nothing_else_parses() -> None:
    assert parse_tap(button_id("abc123", "ok")) == ("abc123", "ok")
    assert parse_tap(button_id("abc123", "no")) == ("abc123", "no")
    for other in (None, "", "confirmar", "prv:", "prv:abc", "prv:abc:maybe", "prv::ok"):
        assert parse_tap(other) is None


async def test_a_receipt_reaches_every_reviewer_with_buttons(console_world, db_session) -> None:
    tid = console_world["a"]["tenant_id"]
    conv = await _world(db_session, tid, open_for=(DANIELA.phone, PEDRO.phone))
    with tenant_context(tid):
        opened = await open_review(
            db_session,
            conversation=conv,
            reviewers=[DANIELA, PEDRO],
            business="Flor y Encanto",
            method="transfer",
            summary=SUMMARY,
        )
    assert opened.notified == 2 and opened.unreachable == 0
    assert opened.message_to_customer == MSG_CUSTOMER_PENDING
    for reviewer in (DANIELA, PEDRO):
        sent = await _outbound_to(db_session, reviewer.phone)
        assert [m.media_kind for m in sent] == ["image", None]  # receipt, then the buttons
        assert sent[0].media_s3_key == "t/receipt.jpg"
        buttons = sent[1].interactive_payload["buttons"]
        assert [b["title"] for b in buttons] == ["Confirmar pago", "Rechazar pago"]
        assert buttons[0]["id"] == button_id(opened.review.token, "ok")
        assert "Ramo de 12 rosas rojas" in sent[1].content
        assert "Envío a Ñuñoa · viernes 3 de octubre · 13:00 a 17:00" in sent[1].content
        assert "Total: $34.990 · Transferencia" in sent[1].content
    # The customer is never told who reviews.
    assert "Daniela" not in opened.message_to_customer
    assert "9128" not in opened.message_to_customer
    audit = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "payment_review.opened"))
    ).scalar_one()
    assert audit.after_json["notified"] == 2


async def test_a_reviewer_with_a_closed_window_is_counted_not_faked(
    console_world, db_session
) -> None:
    tid = console_world["a"]["tenant_id"]
    conv = await _world(db_session, tid, open_for=(DANIELA.phone,))
    with tenant_context(tid):
        opened = await open_review(
            db_session,
            conversation=conv,
            reviewers=[DANIELA, PEDRO],
            business="Flor y Encanto",
            method="transfer",
            summary=SUMMARY,
        )
    assert (opened.notified, opened.unreachable) == (1, 1)
    assert await _outbound_to(db_session, PEDRO.phone) == []
    notice = (
        await db_session.execute(
            select(PaymentReviewNotice).where(PaymentReviewNotice.reviewer_phone == PEDRO.phone)
        )
    ).scalar_one()
    assert (notice.delivery, notice.reason) == ("undelivered", "window_closed")


async def test_a_second_receipt_joins_the_pending_review(console_world, db_session) -> None:
    tid = console_world["a"]["tenant_id"]
    conv = await _world(db_session, tid, open_for=(DANIELA.phone,))
    with tenant_context(tid):
        first = await open_review(
            db_session,
            conversation=conv,
            reviewers=[DANIELA],
            business="Flor y Encanto",
            method="transfer",
            summary=SUMMARY,
        )
        db_session.add(
            Message(
                tenant_id=tid,
                conversation_id=conv.id,
                direction=MessageDirection.INBOUND,
                content="[media:document]",
                media_kind="document",
                media_s3_key="t/receipt-2.pdf",
            )
        )
        await db_session.flush()
        second = await open_review(
            db_session,
            conversation=conv,
            reviewers=[DANIELA],
            business="Flor y Encanto",
            method="transfer",
            summary=SUMMARY,
        )
    assert second.already_pending and second.review.id == first.review.id
    assert second.notified == 0
    assert len(second.review.receipt_message_ids) == 2
    assert len(await _outbound_to(db_session, DANIELA.phone)) == 2  # only the first notice


async def test_a_link_payment_the_store_shows_paid_is_informed_without_buttons(
    console_world, db_session
) -> None:
    tid = console_world["a"]["tenant_id"]
    conv = await _world(db_session, tid, open_for=(DANIELA.phone,))
    with tenant_context(tid):
        opened = await open_review(
            db_session,
            conversation=conv,
            reviewers=[DANIELA],
            business="Flor y Encanto",
            method="link",
            summary=SUMMARY,
            order_id="10452",
            order_status="processing",
        )
    assert opened.review.status == "informed"
    assert opened.message_to_customer == MSG_CUSTOMER_LINK_PAID
    sent = await _outbound_to(db_session, DANIELA.phone)
    last = sent[-1]
    assert last.interactive_payload is None
    assert "Pago en línea · pedido 10452 · processing" in last.content


async def _opened(console_world, db_session, *, customer_window: bool = True) -> tuple:
    tid = console_world["a"]["tenant_id"]
    conv = await _world(db_session, tid, open_for=(DANIELA.phone, PEDRO.phone))
    if not customer_window:
        conv.last_inbound_at = datetime.now(UTC) - timedelta(days=2)
    with tenant_context(tid):
        opened = await open_review(
            db_session,
            conversation=conv,
            reviewers=[DANIELA, PEDRO],
            business="Flor y Encanto",
            method="transfer",
            summary=SUMMARY,
        )
    return tid, conv, opened.review


async def test_the_first_confirm_resolves_and_everyone_hears(console_world, db_session) -> None:
    tid, conv, review = await _opened(console_world, db_session)
    with tenant_context(tid):
        out = await resolve_tap(
            db_session, payload_id=button_id(review.token, "ok"), sender="56991280655"
        )
    assert out.resolved and out.status == "confirmed"
    await db_session.refresh(review)
    assert review.resolved_by_name == "Daniela" and review.customer_notified is True
    assert (await _outbound_to(db_session, DANIELA.phone))[-1].content.startswith("Confirmado.")
    assert (await _outbound_to(db_session, PEDRO.phone))[-1].content == (
        "Daniela confirmó el pago de Camila."
    )
    assert (
        "Tu pago está verificado. Tu pedido queda en preparación para el "
        "viernes 3 de octubre, 13:00 a 17:00."
    ) in await _customer_outbound(db_session, conv)
    assert conv.agent_active is True


async def test_a_late_tap_changes_nothing_and_says_who(console_world, db_session) -> None:
    tid, _conv, review = await _opened(console_world, db_session)
    with tenant_context(tid):
        await resolve_tap(
            db_session, payload_id=button_id(review.token, "ok"), sender="56991280655"
        )
        late = await resolve_tap(
            db_session, payload_id=button_id(review.token, "no"), sender="+56 9 8982 9063"
        )
    assert late.handled and not late.resolved
    await db_session.refresh(review)
    assert review.status == "confirmed"
    assert (await _outbound_to(db_session, PEDRO.phone))[-1].content == (
        "Este pago ya lo confirmó Daniela."
    )
    resolutions = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "payment_review.resolved")
            )
        )
        .scalars()
        .all()
    )
    assert len(resolutions) == 1


async def test_a_reject_hands_the_conversation_to_a_person(console_world, db_session) -> None:
    tid, conv, review = await _opened(console_world, db_session)
    with tenant_context(tid):
        out = await resolve_tap(
            db_session, payload_id=button_id(review.token, "no"), sender="56989829063"
        )
    assert out.status == "rejected"
    await db_session.refresh(conv)
    assert conv.agent_active is False
    assert conv.takeover_context["reason"] == "payment_rejected"
    assert MSG_CUSTOMER_REJECTED in await _customer_outbound(db_session, conv)


async def test_a_closed_customer_window_is_recorded_not_faked(console_world, db_session) -> None:
    tid, conv, review = await _opened(console_world, db_session, customer_window=False)
    with tenant_context(tid):
        await resolve_tap(
            db_session, payload_id=button_id(review.token, "ok"), sender="56991280655"
        )
    await db_session.refresh(review)
    assert review.customer_notified is False
    assert not any(c.startswith("Tu pago") for c in await _customer_outbound(db_session, conv))


async def test_a_stranger_cannot_resolve(console_world, db_session) -> None:
    tid, _conv, review = await _opened(console_world, db_session)
    with tenant_context(tid):
        out = await resolve_tap(
            db_session, payload_id=button_id(review.token, "ok"), sender="56900000001"
        )
    assert out.handled and not out.resolved
    await db_session.refresh(review)
    assert review.status == "pending"


async def test_resolving_never_calls_the_model(console_world, db_session, monkeypatch) -> None:
    """T-MET: the tap is decided by the button, not by a model call."""
    import nexus_api.services.payment_reviews as svc

    assert not any("llm" in name.lower() for name in vars(svc))
    tid, _conv, review = await _opened(console_world, db_session)
    with tenant_context(tid):
        out = await resolve_tap(
            db_session, payload_id=button_id(review.token, "ok"), sender="56991280655"
        )
    assert out.resolved
    assert (await db_session.execute(select(PaymentReview))).scalars().first() is not None


async def test_an_earlier_product_photo_is_not_forwarded_as_the_receipt(
    console_world, db_session
) -> None:
    tid = console_world["a"]["tenant_id"]
    conv = await _world(db_session, tid, open_for=(DANIELA.phone,))
    # The agent answered after the first photo: that photo was a product, not a receipt.
    db_session.add(
        Message(
            tenant_id=tid,
            conversation_id=conv.id,
            direction=MessageDirection.OUTBOUND,
            content="Ese ramo lo tenemos.",
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
    )
    db_session.add(
        Message(
            tenant_id=tid,
            conversation_id=conv.id,
            direction=MessageDirection.INBOUND,
            content="[media:image]",
            media_kind="image",
            media_s3_key="t/the-real-receipt.jpg",
            created_at=datetime.now(UTC) + timedelta(seconds=2),
        )
    )
    await db_session.flush()
    with tenant_context(tid):
        opened = await open_review(
            db_session,
            conversation=conv,
            reviewers=[DANIELA],
            business="Flor y Encanto",
            method="transfer",
            summary=SUMMARY,
        )
    sent = await _outbound_to(db_session, DANIELA.phone)
    assert [m.media_s3_key for m in sent if m.media_s3_key] == ["t/the-real-receipt.jpg"]
    assert len(opened.review.receipt_message_ids) == 1
