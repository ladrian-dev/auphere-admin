"""Public web chat widget surface: ``/v1/widget/*``.

Browser-facing. A visitor on a tenant's own website (e.g. barbersupply.cl)
chats with that tenant's agent through three endpoints:

- ``POST /session`` — resolve the public site key → tenant, check the
  origin allow-list, mint a short-lived session JWT bound to
  ``(tenant_id, session_id, origin)``.
- ``POST /messages`` — enqueue the visitor's turn onto ``nexus:inbound``
  (``provider="web_widget"``), exactly like the Meta webhook does for
  WhatsApp. The existing worker consumer + agent pipeline process it
  unchanged.
- ``GET /messages?since=`` — poll for the agent's replies. Web outbound
  rows are persisted ``status=SENT`` by the checkpoint node (they skip the
  WhatsApp outbound dispatcher), so they are readable the moment the turn
  finishes.

The tenant is read EXCLUSIVELY from the signed JWT claims — never from
browser input — and every message read/write runs under ``SET LOCAL
app.tenant_id`` + RLS. The public key is public (a site key); the real
gate is the origin allow-list + the short-lived token + RLS.

CORS for this surface is handled by ``WidgetCORSMiddleware`` (main.py),
which reflects the request origin — the browser can call cross-origin, but
authorization is the token + the server-side origin check, not CORS.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core import rate_limit
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.widget_jwt import (
    WidgetSessionClaims,
    WidgetSessionTokenError,
    mint_widget_session_token,
    verify_widget_session_token,
)
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
)
from nexus_api.repositories.widget import WidgetConfigRepository
from nexus_api.schemas.widget import (
    WidgetConfigOut,
    WidgetMessageIn,
    WidgetMessageOut,
    WidgetPollOut,
    WidgetSendAck,
    WidgetSessionCreate,
    WidgetSessionOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/widget", tags=["widget"])

# The embeddable loader is served from the API itself (the only deployed
# browser-facing surface — embed.auphere.com is not stood up). The site
# embeds ``<script src="https://api.auphere.com/widget.js" ...>``. Packaged
# as static data under the ``nexus_api`` package (hatchling ships it).
loader_router = APIRouter(tags=["widget"])
_WIDGET_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "widget.js"


@loader_router.get("/widget.js", include_in_schema=False)
async def widget_loader() -> FileResponse:
    return FileResponse(
        _WIDGET_JS_PATH,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


# Same Redis inbound stream the Meta webhook publishes to. Defined locally
# to mirror ``webhooks/meta.py`` (the API side doesn't import the worker).
_INBOUND_STREAM = "nexus:inbound"

# ``type=web`` channel for the public widget. Distinct provider from
# ``qa_playground`` so the customer-facing web traffic keeps its own
# channel / conversation history, separate from the internal QA chat.
_WEB_WIDGET_PROVIDER = "web_widget"

_POLL_HISTORY_LIMIT = 100


def _web_channel_provider_identifier(tenant_id: uuid.UUID) -> str:
    """Globally-unique ``provider_identifier`` for a tenant's web widget
    channel. ``channels`` enforces ``UNIQUE(type, provider_identifier)``."""
    return f"web_widget:{tenant_id}"


async def _get_web_channel(session: AsyncSession, tenant_id: uuid.UUID) -> Channel | None:
    stmt = (
        sa.select(Channel)
        .where(Channel.tenant_id == tenant_id)
        .where(Channel.type == ChannelType.WEB)
        .where(Channel.provider == _WEB_WIDGET_PROVIDER)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _ensure_web_channel(session: AsyncSession, tenant_id: uuid.UUID) -> Channel:
    """Get-or-create the tenant's public web widget ``web`` channel.

    Created lazily on the first widget message. The caller's tx must
    already have ``app.tenant_id`` set so RLS accepts the INSERT.
    """
    channel = await _get_web_channel(session, tenant_id)
    if channel is not None:
        return channel
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WEB,
        provider=_WEB_WIDGET_PROVIDER,
        provider_identifier=_web_channel_provider_identifier(tenant_id),
        config={"web_widget": True},
        status=ChannelStatus.ACTIVE,
    )
    session.add(channel)
    await session.flush()
    return channel


# ── session mint (no token yet — public site key + origin) ──────────────────


@router.post(
    "/session",
    response_model=WidgetSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_widget_session(
    body: WidgetSessionCreate,
    request: Request,
    origin: str | None = Header(default=None, alias="Origin"),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> WidgetSessionOut:
    """Mint a short-lived session JWT for an anonymous visitor.

    The public key resolves the tenant; the request ``Origin`` must be in
    the tenant's allow-list. Both an unknown key and a disabled/forbidden
    origin return an opaque 403 so the key space can't be probed.
    """
    if not origin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing Origin")

    async with session.begin():
        config = await WidgetConfigRepository(session).get_by_public_key(body.public_key)

    # Opaque failure — never reveal whether the key exists, is disabled, or
    # the origin is simply not allowed.
    if config is None or not config.enabled or origin not in (config.allowed_origins or []):
        log.info(
            "widget.session.rejected",
            has_config=config is not None,
            origin=origin,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Widget not available for this site"
        )

    # Per-site mint throttle keyed on the public key (pre-session, no
    # session id yet). Reuses the visitor's poll ceiling as a sane bound.
    if not await rate_limit.allow(
        redis,
        key=rate_limit.widget_message_bucket_key(body.public_key),
        per_minute=get_settings().widget_poll_rate_limit_per_min,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    # Reuse the returning visitor's stored id (cart/history continuity) or
    # mint a fresh anonymous identity.
    session_id = body.session_id or uuid.uuid4().hex
    token, _jti, expires_in = mint_widget_session_token(
        tenant_id=config.tenant_id, session_id=session_id, origin=origin
    )
    return WidgetSessionOut(
        session_token=token,
        session_id=session_id,
        expires_in=expires_in,
        config=WidgetConfigOut(greeting=config.greeting, appearance=config.appearance or {}),
    )


# ── authenticated widget context (message send + poll) ──────────────────────


@dataclass(frozen=True)
class WidgetContext:
    """Tenant-scoped session + verified claims for a ``/v1/widget/messages``
    request. ``session`` is scoped from the JWT — never from browser input."""

    session: AsyncSession
    claims: WidgetSessionClaims


async def scoped_session_from_widget_jwt(
    authorization: str | None = Header(default=None, alias="Authorization"),
    origin: str | None = Header(default=None, alias="Origin"),
    session: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[WidgetContext]:
    """Verify the session JWT, bind the request to the token's origin, and
    scope the session to the token's tenant (RLS). Fail-closed re-check:
    the widget config must still exist + be enabled, mirroring key
    revocation — disabling the widget kills live tokens on the next call.
    """
    from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = verify_widget_session_token(authorization.removeprefix("Bearer ").strip())
    except WidgetSessionTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        ) from None

    # The token is bound to the origin it was minted for. A request from a
    # different origin (token lifted onto another site) is rejected.
    if not origin or origin != claims.origin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin mismatch")

    token = _current_tenant.set(claims.tenant_id)
    try:
        async with session.begin():
            await apply_tenant_to_session(session, claims.tenant_id)
            config = await WidgetConfigRepository(session).get_for_tenant(claims.tenant_id)
            if config is None or not config.enabled or origin not in (config.allowed_origins or []):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Widget disabled")
            bind_tenant(claims.tenant_id)
            yield WidgetContext(session=session, claims=claims)
    finally:
        _current_tenant.reset(token)


@router.post(
    "/messages",
    response_model=WidgetSendAck,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_widget_message(
    body: WidgetMessageIn,
    ctx: WidgetContext = Depends(scoped_session_from_widget_jwt),
    redis: Redis = Depends(get_redis),
) -> WidgetSendAck:
    """Enqueue the visitor's turn onto ``nexus:inbound``. The worker's
    existing consumer + pipeline upsert the customer/conversation and run
    the agent — identical to the WhatsApp path, just a different provider."""
    if not await rate_limit.allow(
        redis,
        key=rate_limit.widget_message_bucket_key(ctx.claims.session_id),
        per_minute=get_settings().widget_message_rate_limit_per_min,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    channel = await _ensure_web_channel(ctx.session, ctx.claims.tenant_id)

    fields: dict[str, str] = {
        "tenant_id": str(ctx.claims.tenant_id),
        "channel_id": str(channel.id),
        "user_id": ctx.claims.session_id,
        "content": body.content,
        "provider": _WEB_WIDGET_PROVIDER,
        "kind": "text",
    }
    await redis.xadd(_INBOUND_STREAM, fields)  # type: ignore[arg-type]  # redis stub: invariant dict
    log.info(
        "widget.message.enqueued",
        tenant_id=str(ctx.claims.tenant_id),
        channel_id=str(channel.id),
        session_id=ctx.claims.session_id,
    )
    return WidgetSendAck(status="enqueued")


@router.get("/messages", response_model=WidgetPollOut)
async def poll_widget_messages(
    ctx: WidgetContext = Depends(scoped_session_from_widget_jwt),
    since: str | None = Query(default=None, description="ISO-8601 timestamp; return newer rows"),
    redis: Redis = Depends(get_redis),
) -> WidgetPollOut:
    """Return this session's messages after ``since`` (or recent history on
    first load). Web outbound rows are persisted ``SENT``, so an agent reply
    shows up here as soon as the turn finishes."""
    if not await rate_limit.allow(
        redis,
        key=rate_limit.widget_poll_bucket_key(ctx.claims.session_id),
        per_minute=get_settings().widget_poll_rate_limit_per_min,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    server_time = datetime.now(UTC)
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            since_dt = None

    channel = await _get_web_channel(ctx.session, ctx.claims.tenant_id)
    if channel is None:
        return WidgetPollOut(messages=[], server_time=server_time)

    # Resolve this visitor's conversation on the web channel. Missing until
    # the worker processes the first inbound — return empty, keep polling.
    conv_stmt = (
        sa.select(Conversation.id)
        .join(Customer, Customer.id == Conversation.customer_id)
        .where(Conversation.channel_id == channel.id)
        .where(Customer.identifier == ctx.claims.session_id)
        .limit(1)
    )
    conversation_id = (await ctx.session.execute(conv_stmt)).scalar_one_or_none()
    if conversation_id is None:
        return WidgetPollOut(messages=[], server_time=server_time)

    msg_stmt = (
        sa.select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(_POLL_HISTORY_LIMIT)
    )
    if since_dt is not None:
        msg_stmt = msg_stmt.where(Message.created_at > since_dt)
    rows = (await ctx.session.execute(msg_stmt)).scalars().all()

    messages = [
        WidgetMessageOut(
            id=m.id,
            direction=m.direction.value
            if isinstance(m.direction, MessageDirection)
            else str(m.direction),
            content=m.content,
            interactive_payload=m.interactive_payload,
            created_at=m.created_at,
        )
        for m in rows
    ]
    return WidgetPollOut(messages=messages, server_time=server_time)
