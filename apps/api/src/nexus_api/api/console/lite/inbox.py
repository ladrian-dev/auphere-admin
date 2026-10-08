"""``/console/lite/inbox/*`` — la Bandeja de entrada (spec 030, Requisitos 6 a 13).

**Las únicas rutas de la consola que pueden devolver cuerpos de mensaje.** C8
protege al negocio del partner; el negocio leyendo sus propias conversaciones
no cruza esa frontera (ADR-041). Solo las alcanza la persona de un cliente con
el módulo ``inbox`` (``require_client_principal``): ninguna persona del partner
llega aquí, y lo fija el barrido ``test_lite_bodies_only_in_inbox.py``.

Todo corre en la transacción del cliente de la sesión (``lite_scope``): un id
de otro cliente no existe para la RLS y responde 404, igual que uno inventado.

Cada acción se audita con la persona (``client:<correo>``) y sin contenido —
solo longitudes y nombres de etiqueta— y se publica en el canal de tiempo real
del cliente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ContactNote,
    Conversation,
    ConversationEventKind,
    ConversationStatus,
    ConversationTag,
    InboxRead,
    Message,
    MessageDirection,
    MessageStatus,
    SavedReply,
)
from nexus_api.services import conversation_control, inbox_lifecycle, inbox_view
from nexus_api.services.conversation_control import VersionMismatch
from nexus_api.services.inbox_stream import publish_inbox_event

from .deps import LiteScope, lite_scope

router = APIRouter(prefix="/inbox")

ConversationId = Path(..., description="Conversation id (of the session's client)")


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown conversation")


def _conflict(code: str, **info: Any) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": code, **info})


# ── schemas ────────────────────────────────────────────────────────────


class AuthorOut(BaseModel):
    kind: Literal["contact", "agent", "member", "operator", "system"]
    name: str | None = None
    is_me: bool = False


class ContactOut(BaseModel):
    name: str
    handle: str
    initials: str


class LastMessageOut(BaseModel):
    at: datetime
    author: AuthorOut
    preview: str
    has_media: bool


class ConversationItemOut(BaseModel):
    id: uuid.UUID
    contact: ContactOut
    channel: dict[str, str]
    agent: dict[str, str] | None = None
    state: Literal["agent", "waiting", "person", "resolved"]
    assignee: AuthorOut | None
    last_message: LastMessageOut | None
    unread: bool
    tags: list[str]


class CountsOut(BaseModel):
    unread: int
    waiting: int


class ConversationPageOut(BaseModel):
    items: list[ConversationItemOut]
    next_cursor: str | None
    counts: CountsOut
    has_any: bool
    channel_kinds: list[str]


class WindowOut(BaseModel):
    open: bool
    closes_at: datetime | None


class ContactDetailOut(BaseModel):
    name: str
    handle: str
    first_message_at: datetime | None
    conversations: int


class NoteOut(BaseModel):
    body: str
    updated_at: datetime | None


class ActivityOut(BaseModel):
    kind: str
    at: datetime
    actor: AuthorOut
    detail: str | None


class ConversationDetailOut(BaseModel):
    id: uuid.UUID
    state: Literal["agent", "waiting", "person", "resolved"]
    assignee: AuthorOut | None
    agent: dict[str, str] | None = None
    control_version: int
    window: WindowOut
    channel: dict[str, Any]
    contact: ContactDetailOut
    summary: str | None
    waiting_reason: str | None
    tags: list[str]
    note: NoteOut
    activity: list[ActivityOut]


class ThreadItemOut(BaseModel):
    type: Literal["message", "event"]
    id: uuid.UUID
    at: datetime
    direction: str | None = None
    author: AuthorOut | None = None
    text: str | None = None
    media: dict[str, str | None] | None = None
    delivery: str | None = None
    failure_reason: str | None = None
    kind: str | None = None
    detail: str | None = None


class ThreadOut(BaseModel):
    items: list[ThreadItemOut]
    next_before: str | None


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4096)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("blank message")
        return v


class SentOut(BaseModel):
    id: uuid.UUID
    at: datetime
    delivery: str


class TagsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[str] = Field(max_length=20)


class TagsOut(BaseModel):
    tags: list[str]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(max_length=4000)


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=1000)


class ReplyPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=80)
    body: str | None = Field(default=None, min_length=1, max_length=1000)


class ReplyOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str


# ── helpers ────────────────────────────────────────────────────────────


def _initials(name: str) -> str:
    parts = [p for p in name.replace("+", " ").split() if p and p[0].isalpha()]
    if not parts:
        return "·"
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()


def _author(a: inbox_view.Author | None) -> AuthorOut | None:
    if a is None:
        return None
    kind = a.kind if a.kind in {"contact", "agent", "member", "operator", "system"} else "system"
    return AuthorOut(kind=kind, name=a.name, is_me=a.is_me)  # type: ignore[arg-type]


def _audit(scope: LiteScope, action: str, target: uuid.UUID, after: dict[str, Any]) -> None:
    scope.session.add(
        AuditLog(
            tenant_id=scope.principal.tenant_id,
            actor=scope.principal.actor,
            action=action,
            target=f"conversation:{target}",
            after_json=after,
        )
    )


def _me(scope: LiteScope) -> str:
    return scope.principal.user_id


async def _conversation(scope: LiteScope, conversation_id: uuid.UUID) -> Conversation:
    conv = await inbox_view.get_conversation(scope.session, conversation_id)
    if conv is None:
        raise _not_found()
    return conv


async def _detail_out(scope: LiteScope, conv: Conversation) -> ConversationDetailOut:
    d = await inbox_view.detail(
        scope.session, conv, tenant_id=scope.principal.tenant_id, me=_me(scope)
    )
    return ConversationDetailOut(
        id=conv.id,
        state=d.state,  # type: ignore[arg-type]
        assignee=_author(d.assignee),
        agent=({"id": str(d.agent[0]), "name": d.agent[1]} if d.agent else None),
        control_version=conv.agent_active_version,
        window=WindowOut(open=d.window_open, closes_at=d.window_closes_at),
        channel={"kind": d.channel_kind, "connected": d.channel_connected},
        contact=ContactDetailOut(
            name=d.contact_name,
            handle=d.contact_handle,
            first_message_at=d.first_message_at,
            conversations=d.conversations,
        ),
        summary=d.summary,
        waiting_reason=d.waiting_reason,
        tags=d.tags,
        note=NoteOut(body=d.note_body, updated_at=d.note_updated_at),
        activity=[
            ActivityOut(
                kind=a.kind,
                at=a.at,
                actor=_author(a.actor) or AuthorOut(kind="system"),
                detail=a.detail,
            )
            for a in d.activity
        ],
    )


async def _publish(
    redis: Redis,
    scope: LiteScope,
    conv_id: uuid.UUID,
    event: str = "conversation.updated",
    **fields: Any,
) -> None:
    await publish_inbox_event(
        redis, tenant_id=scope.principal.tenant_id, event=event, conversation_id=conv_id, **fields
    )


# ── reads ──────────────────────────────────────────────────────────────


@router.get("/conversations", response_model=ConversationPageOut)
async def list_conversations(
    scope: LiteScope = Depends(lite_scope("inbox")),
    filter: Literal["all", "unread", "waiting", "resolved"] = Query(default="all"),
    q: str | None = Query(default=None, max_length=120),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=50),
    agent: uuid.UUID | None = Query(
        default=None, description="Only this agent's numbers (spec 030)"
    ),
) -> ConversationPageOut:
    try:
        page = await inbox_view.list_conversations(
            scope.session,
            tenant_id=scope.principal.tenant_id,
            me=_me(scope),
            flt=filter,
            q=q or None,
            cursor=cursor,
            limit=limit,
            agent=agent,
        )
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bad cursor"
        ) from None
    return ConversationPageOut(
        items=[
            ConversationItemOut(
                id=i.id,
                contact=ContactOut(
                    name=i.contact_name, handle=i.contact_handle, initials=_initials(i.contact_name)
                ),
                channel={"kind": i.channel_kind},
                agent=({"id": str(i.agent[0]), "name": i.agent[1]} if i.agent else None),
                state=i.state,  # type: ignore[arg-type]
                assignee=_author(i.assignee),
                last_message=(
                    LastMessageOut(
                        at=i.last_message.at,
                        author=_author(i.last_message.author) or AuthorOut(kind="system"),
                        preview=i.last_message.preview,
                        has_media=i.last_message.has_media,
                    )
                    if i.last_message
                    else None
                ),
                unread=i.unread,
                tags=i.tags,
            )
            for i in page.items
        ],
        next_cursor=page.next_cursor,
        counts=CountsOut(unread=page.unread, waiting=page.waiting),
        has_any=page.has_any,
        channel_kinds=page.channel_kinds,
    )


@router.get("/counts", response_model=CountsOut)
async def read_counts(scope: LiteScope = Depends(lite_scope("inbox"))) -> CountsOut:
    unread, waiting = await inbox_view.counts(scope.session, me=_me(scope))
    return CountsOut(unread=unread, waiting=waiting)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def read_conversation(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
) -> ConversationDetailOut:
    return await _detail_out(scope, await _conversation(scope, conversation_id))


@router.get("/conversations/{conversation_id}/messages", response_model=ThreadOut)
async def read_thread(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
    before: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=100),
) -> ThreadOut:
    conv = await _conversation(scope, conversation_id)
    try:
        items, next_before = await inbox_view.thread(
            scope.session,
            conv,
            tenant_id=scope.principal.tenant_id,
            me=_me(scope),
            before=before,
            limit=limit,
        )
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="bad cursor"
        ) from None
    return ThreadOut(
        items=[
            ThreadItemOut(
                type=i.type,  # type: ignore[arg-type]
                id=i.id,
                at=i.at,
                direction=i.direction,
                author=_author(i.author),
                text=i.text,
                media=(
                    {
                        "kind": i.media_kind,
                        "filename": i.media_filename,
                        "transcript": i.media_transcript,
                    }
                    if i.media_kind
                    else None
                ),
                delivery=i.delivery,
                failure_reason=i.failure_reason,
                kind=i.event_kind,
                detail=i.detail,
            )
            for i in items
        ],
        next_before=next_before,
    )


# ── read state ─────────────────────────────────────────────────────────


async def _set_read(scope: LiteScope, conv: Conversation, *, unread: bool) -> None:
    row = await scope.session.get(InboxRead, (conv.id, _me(scope)))
    if row is None:
        row = InboxRead(tenant_id=conv.tenant_id, conversation_id=conv.id, user_id=_me(scope))
        scope.session.add(row)
    if unread:
        row.marked_unread = True
    else:
        row.read_at = datetime.now(UTC)
        row.marked_unread = False
    await scope.session.flush()


@router.post("/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
) -> Response:
    await _set_read(scope, await _conversation(scope, conversation_id), unread=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/unread", status_code=status.HTTP_204_NO_CONTENT)
async def mark_unread(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
) -> Response:
    await _set_read(scope, await _conversation(scope, conversation_id), unread=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── control ────────────────────────────────────────────────────────────


def _if_match(raw: str | None) -> int | None:
    try:
        return conversation_control.parse_if_match(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="If-Match must be an integer version"
        ) from None


async def _version_conflict(
    scope: LiteScope, conv: Conversation, exc: VersionMismatch
) -> HTTPException:
    current = await _detail_out(scope, conv)
    return HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail={**exc.detail(), "conversation": current.model_dump(mode="json")},
    )


@router.post("/conversations/{conversation_id}/takeover", response_model=ConversationDetailOut)
async def take_over(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
    redis: Redis = Depends(get_redis),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> ConversationDetailOut:
    """La persona entra: el agente se calla en esta conversación (R9.2). Si ya
    la tenía otra persona, pasa a quien la toma ahora."""
    conv = await _conversation(scope, conversation_id)
    me = _me(scope)
    if not conv.agent_active and conv.assigned_user_id == me:
        return await _detail_out(scope, conv)
    try:
        conversation_control.check_version(conv, _if_match(if_match))
    except VersionMismatch as exc:
        raise await _version_conflict(scope, conv, exc) from None
    if conv.agent_active:
        conversation_control.pause(
            conv,
            reason="inbox",
            notes=None,
            operator_label=scope.principal.membership.display_name
            or scope.principal.membership.email,
        )
    else:
        conversation_control.bump(conv)
    if conv.status == ConversationStatus.CLOSED:
        conv.closed_at = None
    conv.status = ConversationStatus.OPEN
    conv.assigned_user_id = me
    await inbox_lifecycle.record_event(
        scope.session, conv, ConversationEventKind.TAKEOVER, f"client:{me}"
    )
    _audit(scope, "inbox.takeover", conv.id, {"control_version": conv.agent_active_version})
    await scope.session.flush()
    await _publish(redis, scope, conv.id)
    return await _detail_out(scope, conv)


@router.post("/conversations/{conversation_id}/release", response_model=ConversationDetailOut)
async def give_back(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
    redis: Redis = Depends(get_redis),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> ConversationDetailOut:
    """Devuelve la conversación al agente (R9.3): responde al siguiente mensaje
    del contacto, sabiendo lo que hizo la persona (``takeover_context`` se
    queda para el despachador)."""
    conv = await _conversation(scope, conversation_id)
    me = _me(scope)
    waiting_unattended = (
        conv.status == ConversationStatus.ESCALATED and conv.assigned_user_id is None
    )
    if conv.agent_active and not waiting_unattended:
        return await _detail_out(scope, conv)
    if conv.assigned_user_id not in (None, me):
        raise _conflict("not_assigned_to_you")
    try:
        conversation_control.check_version(conv, _if_match(if_match))
    except VersionMismatch as exc:
        raise await _version_conflict(scope, conv, exc) from None
    conversation_control.resume(conv)
    conv.assigned_user_id = None
    if conv.status == ConversationStatus.ESCALATED:
        conv.status = ConversationStatus.OPEN
    await inbox_lifecycle.record_event(
        scope.session, conv, ConversationEventKind.RELEASED, f"client:{me}"
    )
    _audit(scope, "inbox.released", conv.id, {"control_version": conv.agent_active_version})
    await scope.session.flush()
    await _publish(redis, scope, conv.id)
    return await _detail_out(scope, conv)


async def _can_send(scope: LiteScope, conv: Conversation) -> Channel:
    """Precondiciones de un envío (R10): la atiende quien envía, la ventana de
    24 h está abierta y el número está conectado."""
    if conv.agent_active or conv.assigned_user_id != _me(scope):
        raise _conflict("not_assigned_to_you")
    now = datetime.now(UTC)
    if conv.last_inbound_at is None or conv.last_inbound_at + inbox_view.WINDOW <= now:
        raise _conflict("window_closed")
    channel = await scope.session.get(Channel, conv.channel_id)
    if channel is None or channel.status != ChannelStatus.ACTIVE:
        raise _conflict("channel_disconnected")
    return channel


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SentOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    body: SendIn,
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
    redis: Redis = Depends(get_redis),
) -> SentOut:
    conv = await _conversation(scope, conversation_id)
    await _can_send(scope, conv)
    now = datetime.now(UTC)
    msg = Message(
        tenant_id=conv.tenant_id,
        conversation_id=conv.id,
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=body.text,
        tool_calls=[],
        actor_kind="member",
        # La membresía, no el ``user_id``: ``actor_id`` es UUID y el id de
        # la consola es texto de Better Auth.
        actor_id=scope.principal.membership.id,
    )
    scope.session.add(msg)
    conv.last_message_at = now
    _audit(scope, "inbox.message_sent", conv.id, {"length": len(body.text)})
    await scope.session.flush()
    await scope.session.refresh(msg)
    await _publish(
        redis, scope, conv.id, "message.new", message_id=str(msg.id), direction="outbound"
    )
    return SentOut(id=msg.id, at=msg.created_at, delivery="pending")


# ── lifecycle ──────────────────────────────────────────────────────────


@router.post("/conversations/{conversation_id}/resolve", response_model=ConversationDetailOut)
async def resolve(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
    redis: Redis = Depends(get_redis),
) -> ConversationDetailOut:
    conv = await _conversation(scope, conversation_id)
    if await inbox_lifecycle.resolve(scope.session, conv, actor=f"client:{_me(scope)}"):
        _audit(scope, "inbox.resolved", conv.id, {})
        await scope.session.flush()
        await _publish(redis, scope, conv.id)
    return await _detail_out(scope, conv)


@router.post("/conversations/{conversation_id}/reopen", response_model=ConversationDetailOut)
async def reopen(
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
    redis: Redis = Depends(get_redis),
) -> ConversationDetailOut:
    conv = await _conversation(scope, conversation_id)
    if await inbox_lifecycle.reopen(scope.session, conv, actor=f"client:{_me(scope)}"):
        _audit(scope, "inbox.reopened", conv.id, {})
        await scope.session.flush()
        await _publish(redis, scope, conv.id)
    return await _detail_out(scope, conv)


# ── tags and notes ─────────────────────────────────────────────────────


def _clean_tags(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in raw:
        clean = " ".join(tag.split())[:40]
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            out.append(clean)
    return out


@router.put("/conversations/{conversation_id}/tags", response_model=TagsOut)
async def set_tags(
    body: TagsIn,
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
    redis: Redis = Depends(get_redis),
) -> TagsOut:
    conv = await _conversation(scope, conversation_id)
    tags = _clean_tags(body.tags)
    before = [
        str(t)
        for t in (
            await scope.session.execute(
                sa.select(ConversationTag.tag).where(ConversationTag.conversation_id == conv.id)
            )
        ).scalars()
    ]
    await scope.session.execute(
        sa.delete(ConversationTag).where(ConversationTag.conversation_id == conv.id)
    )
    for tag in tags:
        scope.session.add(
            ConversationTag(
                tenant_id=conv.tenant_id,
                conversation_id=conv.id,
                tag=tag,
                created_by=scope.principal.actor,
            )
        )
    added = sorted({t for t in tags} - set(before))
    removed = sorted(set(before) - set(tags))
    if added:
        _audit(scope, "inbox.tagged", conv.id, {"tags": added})
    if removed:
        _audit(scope, "inbox.untagged", conv.id, {"tags": removed})
    await scope.session.flush()
    await _publish(redis, scope, conv.id)
    return TagsOut(tags=tags)


@router.get("/tags", response_model=TagsOut)
async def suggested_tags(scope: LiteScope = Depends(lite_scope("inbox"))) -> TagsOut:
    rows = await scope.session.execute(
        sa.select(ConversationTag.tag, sa.func.count())
        .group_by(ConversationTag.tag)
        .order_by(sa.func.count().desc(), ConversationTag.tag)
        .limit(50)
    )
    return TagsOut(tags=[str(t) for t, _n in rows.all()])


@router.put("/conversations/{conversation_id}/note", response_model=NoteOut)
async def set_note(
    body: NoteIn,
    conversation_id: uuid.UUID = ConversationId,
    scope: LiteScope = Depends(lite_scope("inbox")),
) -> NoteOut:
    """La nota interna del contacto: solo la ve el equipo, nunca la recibe el
    contacto ni la lee el agente (R13.5)."""
    conv = await _conversation(scope, conversation_id)
    note = await scope.session.get(ContactNote, conv.customer_id)
    now = datetime.now(UTC)
    if note is None:
        note = ContactNote(tenant_id=conv.tenant_id, customer_id=conv.customer_id)
        scope.session.add(note)
    note.body = body.body
    note.updated_by = scope.principal.actor
    note.updated_at = now
    _audit(scope, "inbox.note_saved", conv.id, {"length": len(body.body)})
    await scope.session.flush()
    return NoteOut(body=note.body, updated_at=note.updated_at)


# ── saved replies ──────────────────────────────────────────────────────


def _reply_out(r: SavedReply) -> ReplyOut:
    return ReplyOut(id=r.id, title=r.title, body=r.body)


@router.get("/replies", response_model=list[ReplyOut])
async def list_replies(scope: LiteScope = Depends(lite_scope("inbox"))) -> list[ReplyOut]:
    rows = await scope.session.execute(
        sa.select(SavedReply).where(SavedReply.archived_at.is_(None)).order_by(SavedReply.title)
    )
    return [_reply_out(r) for r in rows.scalars()]


@router.post("/replies", response_model=ReplyOut, status_code=status.HTTP_201_CREATED)
async def create_reply(body: ReplyIn, scope: LiteScope = Depends(lite_scope("inbox"))) -> ReplyOut:
    reply = SavedReply(
        tenant_id=scope.principal.tenant_id,
        title=body.title.strip(),
        body=body.body,
        created_by=scope.principal.actor,
    )
    scope.session.add(reply)
    await scope.session.flush()
    await scope.session.refresh(reply)
    scope.session.add(
        AuditLog(
            tenant_id=scope.principal.tenant_id,
            actor=scope.principal.actor,
            action="inbox.reply_saved",
            target=f"saved_reply:{reply.id}",
            after_json={"title_length": len(reply.title), "length": len(reply.body)},
        )
    )
    return _reply_out(reply)


async def _reply(scope: LiteScope, reply_id: uuid.UUID) -> SavedReply:
    reply = await scope.session.get(SavedReply, reply_id)
    if reply is None or reply.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown reply")
    return reply


@router.patch("/replies/{reply_id}", response_model=ReplyOut)
async def edit_reply(
    body: ReplyPatchIn,
    reply_id: uuid.UUID = Path(...),
    scope: LiteScope = Depends(lite_scope("inbox")),
) -> ReplyOut:
    reply = await _reply(scope, reply_id)
    if body.title is not None:
        reply.title = body.title.strip()
    if body.body is not None:
        reply.body = body.body
    reply.updated_at = datetime.now(UTC)
    await scope.session.flush()
    return _reply_out(reply)


@router.delete("/replies/{reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_reply(
    reply_id: uuid.UUID = Path(...),
    scope: LiteScope = Depends(lite_scope("inbox")),
) -> Response:
    """Borrar no existe (constitución §IV): la respuesta se archiva."""
    reply = await _reply(scope, reply_id)
    reply.archived_at = datetime.now(UTC)
    await scope.session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
