"""Spec 064, requisito 4 — una conversación resuelta empieza de cero.

Resolver deja dicho que la próxima reapertura corta. La reapertura por el
contacto o por un aviso del sistema fija ``context_from`` —desde cuándo lee el
agente—; la de una persona, a mano, no: el contexto sigue. La Bandeja no lo
nota: lee desde ``attended_at``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.services import inbox_lifecycle
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

PERSON = "client:ana@salon.es"


@pytest.fixture
async def conv(db_session, console_world) -> Conversation:
    """Una conversación cuyo último intercambio fue hace 20 días: lo que se
    escriba después en cada prueba es lo único posterior al último entrante."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    cid = inbox["conversations"][0]
    age = timedelta(days=20)
    await db_session.execute(
        sa.update(Message)
        .where(Message.conversation_id == cid)
        .values(created_at=Message.created_at - age)
    )
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == cid)
        .values(
            attended_at=Conversation.attended_at - age,
            last_attended_inbound_at=Conversation.last_attended_inbound_at - age,
            last_inbound_at=Conversation.last_inbound_at - age,
            last_message_at=Conversation.last_message_at - age,
        )
    )
    await db_session.commit()
    return await _load(db_session, cid)


async def _load(db_session: Any, conversation_id: uuid.UUID) -> Conversation:
    db_session.expire_all()
    row = await db_session.get(Conversation, conversation_id)
    assert row is not None
    return row


async def _say(
    db_session: Any,
    conv: Conversation,
    *,
    at: datetime,
    inbound: bool = False,
    actor: str | None = "system",
    template: bool = True,
) -> Message:
    """Un saliente. Del sistema y por plantilla (la cobranza) salvo que se diga."""
    msg = Message(
        id=uuid.uuid4(),
        tenant_id=conv.tenant_id,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND if inbound else MessageDirection.OUTBOUND,
        status=MessageStatus.DELIVERED if inbound else MessageStatus.SENT,
        content="hola" if inbound else "Te recordamos tu cita.",
        actor_kind=None if inbound else actor,
        template_payload=(
            {"name": "cobranza_recordatorio", "language": "es", "params": {"body": {}}}
            if template and not inbound and actor == "system"
            else None
        ),
        created_at=at,
    )
    db_session.add(msg)
    await db_session.flush()
    return msg


async def _resolve(db_session: Any, conv: Conversation) -> datetime:
    assert await inbox_lifecycle.resolve(db_session, conv, actor=PERSON)
    await db_session.flush()
    assert conv.closed_at is not None
    return conv.closed_at


async def test_resolving_says_the_next_reopening_cuts(db_session, conv) -> None:
    assert conv.cut_on_reopen is False and conv.context_from is None
    await _resolve(db_session, conv)
    assert conv.status == ConversationStatus.CLOSED
    assert conv.cut_on_reopen is True
    assert conv.context_from is None  # resolver no corta: corta volver


@pytest.mark.parametrize("actor", ["contact", "system", "business_app", "history"])
async def test_coming_back_cuts_at_the_resolution(db_session, conv, actor: str) -> None:
    closed = await _resolve(db_session, conv)
    assert await inbox_lifecycle.reopen(db_session, conv, actor=actor)
    assert conv.status == ConversationStatus.OPEN
    assert conv.context_from == closed
    assert conv.cut_on_reopen is False


async def test_a_person_reopening_by_hand_keeps_the_context(db_session, conv) -> None:
    await _resolve(db_session, conv)
    assert await inbox_lifecycle.reopen(db_session, conv, actor=PERSON)
    assert conv.context_from is None
    assert conv.cut_on_reopen is False
    # Y lo que venga después tampoco corta, hasta que se vuelva a resolver.
    conv.status = ConversationStatus.CLOSED
    conv.closed_at = datetime.now(UTC)
    assert await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from is None


async def test_resolved_before_this_spec_does_not_cut(db_session, conv) -> None:
    """Requisito 4.8: una fila ``CLOSED`` de antes no trae ``cut_on_reopen``."""
    conv.status = ConversationStatus.CLOSED
    conv.closed_at = datetime.now(UTC) - timedelta(days=3)
    await db_session.flush()
    assert await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from is None


async def test_each_resolution_moves_the_cut_forward(db_session, conv) -> None:
    first = await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == first
    second = await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == second and second >= first


async def test_an_unanswered_notice_stays_in_the_context(db_session, conv) -> None:
    """Requisito 4.6: un aviso del sistema que el contacto aún no contestó, y que
    no viene de Reservas, sigue vigente 7 días."""
    notice = await _say(db_session, conv, at=datetime.now(UTC) - timedelta(days=6))
    closed = await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == notice.created_at
    assert conv.context_from < closed


async def test_an_old_notice_is_left_behind(db_session, conv) -> None:
    await _say(db_session, conv, at=datetime.now(UTC) - timedelta(days=8))
    closed = await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == closed


async def test_an_answered_notice_is_left_behind(db_session, conv) -> None:
    now = datetime.now(UTC)
    await _say(db_session, conv, at=now - timedelta(days=2))
    await _say(db_session, conv, at=now - timedelta(days=1), inbound=True)
    closed = await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == closed


async def test_only_a_notice_of_the_system_is_kept(db_session, conv) -> None:
    """Lo último que dijo el agente o una persona no es un aviso pendiente."""
    now = datetime.now(UTC)
    await _say(db_session, conv, at=now - timedelta(hours=3), actor="agent")
    await _say(db_session, conv, at=now - timedelta(hours=2), actor="member")
    closed = await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == closed


async def test_a_holding_reply_is_not_a_pending_notice(db_session, conv) -> None:
    """El texto de espera de una puerta cerrada lo firma el sistema, pero es
    una respuesta. No adelanta el corte, y lo que una persona contestó después
    tampoco entra por él."""
    now = datetime.now(UTC)
    await _say(db_session, conv, at=now - timedelta(hours=5), inbound=True)
    await _say(db_session, conv, at=now - timedelta(hours=5) + timedelta(seconds=2), template=False)
    await _say(db_session, conv, at=now - timedelta(hours=4), actor="member")
    closed = await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == closed


async def test_the_earliest_pending_notice_marks_the_cut(db_session, conv) -> None:
    now = datetime.now(UTC)
    first = await _say(db_session, conv, at=now - timedelta(days=2))
    await _say(db_session, conv, at=now - timedelta(days=1))
    await _resolve(db_session, conv)
    await inbox_lifecycle.reopen(db_session, conv, actor="contact")
    assert conv.context_from == first.created_at


async def test_clear_and_archive_keep_working(db_session, conv) -> None:
    await inbox_lifecycle.clear(db_session, conv)
    assert conv.attended_at is not None and conv.context_from is None
    await inbox_lifecycle.archive(db_session, conv, actor=PERSON)
    assert conv.attended_at is None and conv.cut_on_reopen is True


async def test_the_inbox_still_reads_the_whole_thread(client, db_session, console_world) -> None:
    """Requisito 4.3: el corte es del agente. La Bandeja enseña lo de antes."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    cid = inbox["conversations"][0]
    base = f"/console/lite/inbox/conversations/{cid}"
    before = (await client.get(f"{base}/messages", headers=inbox["headers"]())).json()
    assert (await client.post(f"{base}/resolve", headers=inbox["headers"]())).status_code == 200
    row = await _load(db_session, cid)
    await inbox_lifecycle.reopen(db_session, row, actor="contact")
    await db_session.commit()
    assert (await _load(db_session, cid)).context_from is not None
    after = (await client.get(f"{base}/messages", headers=inbox["headers"]())).json()

    def messages(thread: dict[str, Any]) -> list[str]:
        return [i["id"] for i in thread["items"] if i["type"] == "message"]

    assert messages(after) == messages(before) and len(messages(after)) == 2
    kinds = [i["kind"] for i in after["items"] if i["type"] == "event"]
    assert kinds[-2:] == ["resolved", "reopened"]
