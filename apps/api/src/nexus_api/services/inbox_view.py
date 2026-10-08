"""Las lecturas de la Bandeja — spec 030 (Requisitos 7, 8 y 13).

Todo corre en la transacción del cliente de la sesión (``lite_scope``): la RLS
decide qué filas existen, así que un id de otro cliente no se encuentra y la
respuesta es la misma que para un id que no existe.

Las conversaciones del Playground (el canal ``qa_playground``) son pruebas del
partner, no conversaciones del negocio: no aparecen nunca.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from nexus_api.db.models import (
    Agent,
    AgentStatus,
    Channel,
    ChannelStatus,
    ClientMembership,
    ContactNote,
    Conversation,
    ConversationEvent,
    ConversationEventKind,
    ConversationStatus,
    ConversationTag,
    Customer,
    InboxRead,
    Message,
    MessageDirection,
)

#: El canal del Playground: pruebas del partner, nunca conversaciones del negocio.
PLAYGROUND_PROVIDER = "qa_playground"
#: La ventana de WhatsApp para escribir sin plantilla (R10.2).
WINDOW = timedelta(hours=24)
PREVIEW_CHARS = 140

Filter = str  # all | unread | waiting | resolved


def state_of(conversation: Conversation) -> str:
    """D12: ``resolved`` · ``waiting`` · ``person`` · ``agent``."""
    if conversation.status == ConversationStatus.CLOSED:
        return "resolved"
    if conversation.status == ConversationStatus.ESCALATED:
        return "waiting"
    if not conversation.agent_active:
        return "person"
    return "agent"


def unread_expr(user_id: str) -> sa.ColumnElement[bool]:
    """Sin leer para ``user_id``: lo marcó, o hay un entrante posterior a su lectura."""
    read = (
        sa.select(InboxRead.read_at)
        .where(InboxRead.conversation_id == Conversation.id, InboxRead.user_id == user_id)
        .scalar_subquery()
    )
    marked = (
        sa.select(InboxRead.marked_unread)
        .where(InboxRead.conversation_id == Conversation.id, InboxRead.user_id == user_id)
        .scalar_subquery()
    )
    return sa.or_(
        sa.func.coalesce(marked, sa.false()),
        sa.and_(
            Conversation.last_inbound_at.is_not(None),
            Conversation.last_inbound_at
            > sa.func.coalesce(read, sa.text("'-infinity'::timestamptz")),
        ),
    )


def _not_playground() -> sa.ColumnElement[bool]:
    return Channel.provider != PLAYGROUND_PROVIDER


def encode_cursor(at: datetime | None, id_: uuid.UUID) -> str:
    raw = f"{at.isoformat() if at else ''}|{id_}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime | None, uuid.UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    at_raw, id_raw = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
    return (datetime.fromisoformat(at_raw) if at_raw else None), uuid.UUID(id_raw)


@dataclass(frozen=True)
class Author:
    kind: str  # contact | agent | member | operator
    name: str | None = None
    is_me: bool = False


@dataclass(frozen=True)
class LastMessage:
    at: datetime
    author: Author
    preview: str
    has_media: bool


@dataclass(frozen=True)
class ListItem:
    id: uuid.UUID
    contact_name: str
    contact_handle: str
    channel_kind: str
    state: str
    assignee: Author | None
    last_message: LastMessage | None
    unread: bool
    tags: list[str]
    # Spec 030: the agent of the conversation's number — only with 2+ agents.
    agent: tuple[uuid.UUID, str] | None = None


@dataclass
class ListPage:
    items: list[ListItem] = field(default_factory=list)
    next_cursor: str | None = None
    unread: int = 0
    waiting: int = 0
    has_any: bool = False
    channel_kinds: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Members:
    """Las personas del cliente, para decir quién escribió o quién atiende.

    Se buscan por dos llaves que nunca chocan: el ``user_id`` de la consola
    (texto de Better Auth; lo guardan ``assigned_user_id``, ``inbox_reads`` y
    los eventos) y el id de la membresía (UUID; lo guarda
    ``messages.actor_id``, que es una columna UUID)."""

    by_key: dict[str, tuple[str, str]] = field(default_factory=dict)

    def author(self, key: str | None, *, me: str) -> Author:
        name, user_id = self.by_key.get(key or "", (None, None))
        return Author(kind="member", name=name, is_me=user_id is not None and user_id == me)


async def client_agents(session: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    """The client's active agents, principal first (RLS: the session's client)."""
    rows = await session.execute(
        sa.select(Agent.id, Agent.name)
        .where(Agent.status == AgentStatus.ACTIVE.value)
        .order_by(Agent.created_at, Agent.id)
    )
    return [(aid, str(name)) for aid, name in rows.all()]


def agent_of_channel(agents: list[tuple[uuid.UUID, str]]) -> sa.ColumnElement[uuid.UUID | None]:
    """Who answers on a conversation's number: its agent, else the principal."""
    if not agents:
        return Channel.agent_id.expression
    return sa.func.coalesce(
        Channel.agent_id, sa.cast(sa.literal(str(agents[0][0])), PG_UUID(as_uuid=True))
    )


async def member_names(session: AsyncSession, tenant_id: uuid.UUID) -> Members:
    rows = await session.execute(
        sa.select(
            ClientMembership.id,
            ClientMembership.user_id,
            ClientMembership.display_name,
            ClientMembership.email,
        ).where(ClientMembership.tenant_id == tenant_id)
    )
    by_key: dict[str, tuple[str, str]] = {}
    for membership_id, user_id, name, email in rows.all():
        entry = (str(name or email), str(user_id))
        by_key[str(user_id)] = entry
        by_key[str(membership_id)] = entry
    return Members(by_key)


def author_of(
    direction: MessageDirection,
    actor_kind: str | None,
    actor_id: uuid.UUID | None,
    *,
    me: str,
    names: Members,
) -> Author:
    if direction == MessageDirection.INBOUND:
        return Author(kind="contact")
    if actor_kind == "member":
        return names.author(str(actor_id) if actor_id else None, me=me)
    if actor_kind in {"operator", "owner"}:
        return Author(kind="operator")
    return Author(kind="agent")


def _preview(content: str | None) -> str:
    text = " ".join((content or "").split())
    return text if len(text) <= PREVIEW_CHARS else text[: PREVIEW_CHARS - 1].rstrip() + "…"


async def list_conversations(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    me: str,
    flt: Filter,
    q: str | None,
    cursor: str | None,
    limit: int,
    agent: uuid.UUID | None = None,
) -> ListPage:
    page = ListPage()
    unread = unread_expr(me)
    agents = await client_agents(session)
    agent_col = agent_of_channel(agents)
    names_by_agent = dict(agents)
    base = (
        sa.select(
            Conversation,
            Customer.name,
            Customer.identifier,
            Channel.type,
            unread.label("unread"),
            agent_col.label("agent_id"),
        )
        .join(Customer, Customer.id == Conversation.customer_id)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(_not_playground())
    )
    if flt == "resolved":
        base = base.where(Conversation.status == ConversationStatus.CLOSED)
    elif flt == "waiting":
        base = base.where(Conversation.status == ConversationStatus.ESCALATED)
    else:
        base = base.where(Conversation.status != ConversationStatus.CLOSED)
        if flt == "unread":
            base = base.where(unread)
    if agent is not None:
        base = base.where(agent_col == agent)
    if q:
        like = f"%{q.strip()}%"
        in_messages = (
            sa.select(sa.literal(1))
            .select_from(Message)
            .where(Message.conversation_id == Conversation.id, Message.content.ilike(like))
            .exists()
        )
        base = base.where(
            sa.or_(Customer.name.ilike(like), Customer.identifier.ilike(like), in_messages)
        )
    if cursor:
        c_at, c_id = decode_cursor(cursor)
        if c_at is not None:
            base = base.where(
                sa.or_(
                    Conversation.last_message_at < c_at,
                    sa.and_(Conversation.last_message_at == c_at, Conversation.id < c_id),
                    Conversation.last_message_at.is_(None),
                )
            )
        else:
            base = base.where(Conversation.last_message_at.is_(None), Conversation.id < c_id)
    stmt = base.order_by(
        Conversation.last_message_at.desc().nulls_last(), Conversation.id.desc()
    ).limit(limit + 1)
    rows = (await session.execute(stmt)).all()
    shown = rows[:limit]
    if len(rows) > limit and shown:
        last = shown[-1][0]
        page.next_cursor = encode_cursor(last.last_message_at, last.id)

    ids = [r[0].id for r in shown]
    names = await member_names(session, tenant_id)
    last_by_conv: dict[uuid.UUID, Message] = {}
    tags_by_conv: dict[uuid.UUID, list[str]] = {}
    if ids:
        ranked = (
            sa.select(
                Message,
                sa.func.row_number()
                .over(partition_by=Message.conversation_id, order_by=Message.created_at.desc())
                .label("rn"),
            )
            .where(Message.conversation_id.in_(ids))
            .subquery()
        )
        latest = aliased(Message, ranked)
        for row_msg in (await session.execute(sa.select(latest).where(ranked.c.rn == 1))).scalars():
            last_by_conv[row_msg.conversation_id] = row_msg
        for cid, tag in (
            await session.execute(
                sa.select(ConversationTag.conversation_id, ConversationTag.tag)
                .where(ConversationTag.conversation_id.in_(ids))
                .order_by(ConversationTag.created_at)
            )
        ).all():
            tags_by_conv.setdefault(cid, []).append(str(tag))

    show_agents = len(agents) > 1
    for conv, name, identifier, channel_type, is_unread, agent_id in shown:
        msg = last_by_conv.get(conv.id)
        last = (
            LastMessage(
                at=msg.created_at,
                author=author_of(msg.direction, msg.actor_kind, msg.actor_id, me=me, names=names),
                preview=_preview(msg.content),
                has_media=bool(msg.media_s3_key or msg.media_kind),
            )
            if msg is not None
            else None
        )
        assignee = names.author(conv.assigned_user_id, me=me) if conv.assigned_user_id else None
        page.items.append(
            ListItem(
                id=conv.id,
                contact_name=str(name or identifier),
                contact_handle=str(identifier),
                channel_kind=str(getattr(channel_type, "value", channel_type)),
                state=state_of(conv),
                assignee=assignee,
                last_message=last,
                unread=bool(is_unread),
                tags=tags_by_conv.get(conv.id, []),
                agent=(
                    (agent_id, names_by_agent.get(agent_id, "—"))
                    if show_agents and agent_id is not None
                    else None
                ),
            )
        )

    counts_base = (
        sa.select(sa.func.count())
        .select_from(Conversation)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(_not_playground())
    )
    page.unread = int(
        await session.scalar(
            counts_base.where(Conversation.status != ConversationStatus.CLOSED, unread)
        )
        or 0
    )
    page.waiting = int(
        await session.scalar(counts_base.where(Conversation.status == ConversationStatus.ESCALATED))
        or 0
    )
    page.has_any = bool(await session.scalar(counts_base))
    kinds = await session.execute(
        sa.select(sa.distinct(Channel.type)).where(
            _not_playground(), Channel.config["role"].astext.is_distinct_from("notifications")
        )
    )
    page.channel_kinds = sorted(str(getattr(k, "value", k)) for (k,) in kinds.all())
    return page


async def counts(session: AsyncSession, *, me: str) -> tuple[int, int]:
    unread = unread_expr(me)
    base = (
        sa.select(sa.func.count())
        .select_from(Conversation)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(_not_playground())
    )
    n_unread = await session.scalar(
        base.where(Conversation.status != ConversationStatus.CLOSED, unread)
    )
    n_waiting = await session.scalar(
        base.where(Conversation.status == ConversationStatus.ESCALATED)
    )
    return int(n_unread or 0), int(n_waiting or 0)


async def get_conversation(
    session: AsyncSession, conversation_id: uuid.UUID
) -> Conversation | None:
    """La conversación, si es del cliente de la sesión y no del Playground."""
    row = await session.execute(
        sa.select(Conversation)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(Conversation.id == conversation_id, _not_playground())
    )
    return row.scalar_one_or_none()


@dataclass(frozen=True)
class Activity:
    kind: str
    at: datetime
    actor: Author
    detail: str | None


@dataclass
class Detail:
    conversation: Conversation
    state: str
    assignee: Author | None
    window_open: bool
    window_closes_at: datetime | None
    channel_kind: str
    channel_connected: bool
    contact_name: str
    contact_handle: str
    first_message_at: datetime | None
    conversations: int
    summary: str | None
    waiting_reason: str | None
    tags: list[str]
    note_body: str
    note_updated_at: datetime | None
    activity: list[Activity]
    agent: tuple[uuid.UUID, str] | None = None


def _event_actor(actor: str, *, me: str, names: Members) -> Author:
    if actor.startswith("client:"):
        return names.author(actor.removeprefix("client:"), me=me)
    if actor == "contact":
        return Author(kind="contact")
    if actor.startswith("operator:") or actor.startswith("admin:"):
        return Author(kind="operator")
    if actor == "agent":
        return Author(kind="agent")
    return Author(kind="system")


async def detail(
    session: AsyncSession, conversation: Conversation, *, tenant_id: uuid.UUID, me: str
) -> Detail:
    names = await member_names(session, tenant_id)
    customer = await session.get(Customer, conversation.customer_id)
    channel = await session.get(Channel, conversation.channel_id)
    first = await session.scalar(
        sa.select(sa.func.min(Message.created_at)).where(
            Message.conversation_id.in_(
                sa.select(Conversation.id).where(
                    Conversation.customer_id == conversation.customer_id
                )
            )
        )
    )
    rows_for_customer = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(Conversation)
            .where(Conversation.customer_id == conversation.customer_id)
        )
        or 0
    )
    reopened = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(ConversationEvent)
            .where(
                ConversationEvent.conversation_id.in_(
                    sa.select(Conversation.id).where(
                        Conversation.customer_id == conversation.customer_id
                    )
                ),
                ConversationEvent.kind == ConversationEventKind.REOPENED.value,
                ConversationEvent.actor == "contact",
            )
        )
        or 0
    )
    events = (
        (
            await session.execute(
                sa.select(ConversationEvent)
                .where(ConversationEvent.conversation_id == conversation.id)
                .order_by(ConversationEvent.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    last_escalation = next(
        (e for e in events if e.kind == ConversationEventKind.ESCALATED.value), None
    )
    tags = [
        str(t)
        for t in (
            await session.execute(
                sa.select(ConversationTag.tag)
                .where(ConversationTag.conversation_id == conversation.id)
                .order_by(ConversationTag.created_at)
            )
        ).scalars()
    ]
    note = await session.get(ContactNote, conversation.customer_id)
    agents = await client_agents(session)
    agent: tuple[uuid.UUID, str] | None = None
    if len(agents) > 1:
        agent_id = (channel.agent_id if channel else None) or agents[0][0]
        agent = (agent_id, dict(agents).get(agent_id, "—"))
    now = datetime.now(UTC)
    closes = conversation.last_inbound_at + WINDOW if conversation.last_inbound_at else None
    payload: dict[str, Any] = last_escalation.payload if last_escalation is not None else {}
    return Detail(
        conversation=conversation,
        state=state_of(conversation),
        assignee=(
            names.author(conversation.assigned_user_id, me=me)
            if conversation.assigned_user_id
            else None
        ),
        window_open=bool(closes and closes > now),
        window_closes_at=closes,
        channel_kind=str(getattr(channel.type, "value", channel.type)) if channel else "whatsapp",
        channel_connected=bool(channel and channel.status == ChannelStatus.ACTIVE),
        contact_name=str((customer.name or customer.identifier) if customer else "—"),
        contact_handle=str(customer.identifier if customer else ""),
        first_message_at=first,
        conversations=rows_for_customer + reopened,
        summary=(payload.get("customer_summary") or None) if last_escalation else None,
        waiting_reason=(payload.get("reason") or None)
        if (last_escalation and conversation.status == ConversationStatus.ESCALATED)
        else None,
        tags=tags,
        note_body=note.body if note else "",
        note_updated_at=note.updated_at if note else None,
        activity=[
            Activity(
                kind=e.kind,
                at=e.created_at,
                actor=_event_actor(e.actor, me=me, names=names),
                detail=(
                    str(e.payload.get("reason"))[:80]
                    if e.kind == "escalated" and e.payload.get("reason")
                    else None
                ),
            )
            for e in events
        ],
        agent=agent,
    )


@dataclass(frozen=True)
class ThreadItem:
    type: str  # message | event
    id: uuid.UUID
    at: datetime
    direction: str | None = None
    author: Author | None = None
    text: str | None = None
    media_kind: str | None = None
    media_filename: str | None = None
    media_transcript: str | None = None
    delivery: str | None = None
    failure_reason: str | None = None
    event_kind: str | None = None
    detail: str | None = None


async def thread(
    session: AsyncSession,
    conversation: Conversation,
    *,
    tenant_id: uuid.UUID,
    me: str,
    before: str | None,
    limit: int,
) -> tuple[list[ThreadItem], str | None]:
    """Mensajes y eventos en orden, paginando hacia atrás desde ``before``."""
    names = await member_names(session, tenant_id)
    msg_stmt = sa.select(Message).where(Message.conversation_id == conversation.id)
    ev_stmt = sa.select(ConversationEvent).where(
        ConversationEvent.conversation_id == conversation.id
    )
    if before:
        b_at, _ = decode_cursor(before)
        if b_at is not None:
            msg_stmt = msg_stmt.where(Message.created_at < b_at)
            ev_stmt = ev_stmt.where(ConversationEvent.created_at < b_at)
    msgs = (
        (await session.execute(msg_stmt.order_by(Message.created_at.desc()).limit(limit + 1)))
        .scalars()
        .all()
    )
    evs = (
        (
            await session.execute(
                ev_stmt.order_by(ConversationEvent.created_at.desc()).limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )
    items: list[ThreadItem] = []
    for m in msgs:
        status = str(getattr(m.status, "value", m.status)) if m.status is not None else None
        items.append(
            ThreadItem(
                type="message",
                id=m.id,
                at=m.created_at,
                direction=str(getattr(m.direction, "value", m.direction)),
                author=author_of(m.direction, m.actor_kind, m.actor_id, me=me, names=names),
                text=m.content or None,
                media_kind=m.media_kind,
                media_filename=m.media_filename,
                media_transcript=m.media_transcript,
                delivery=status if m.direction == MessageDirection.OUTBOUND else None,
                failure_reason=(m.last_error or m.failure_code) if status == "failed" else None,
            )
        )
    for e in evs:
        items.append(
            ThreadItem(
                type="event",
                id=e.id,
                at=e.created_at,
                author=_event_actor(e.actor, me=me, names=names),
                event_kind=e.kind,
                detail=(
                    str(e.payload.get("reason"))
                    if e.kind == "escalated" and e.payload.get("reason")
                    else None
                ),
            )
        )
    items.sort(key=lambda i: i.at, reverse=True)
    more = len(items) > limit
    page = items[:limit]
    page.reverse()
    next_before = encode_cursor(page[0].at, page[0].id) if (more and page) else None
    return page, next_before


__all__ = [
    "PLAYGROUND_PROVIDER",
    "WINDOW",
    "Author",
    "Detail",
    "ListPage",
    "Members",
    "ThreadItem",
    "counts",
    "detail",
    "get_conversation",
    "list_conversations",
    "state_of",
    "thread",
]
