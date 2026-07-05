"""Browser-facing embed surface: ``/v1/embed/*`` (ADR-028).

Called by the iframe app on ``embed.auphere.com`` with a widget session
JWT. Tenant scoping comes exclusively from the verified claims via
``scoped_session_from_embed_jwt`` — RLS makes cross-tenant reads
structurally impossible.

``GET /v1/embed/partner-config`` is the one unauthenticated route: it
resolves a partner slug to its ``allowed_origins`` so the embed app's
middleware can emit a per-partner ``frame-ancestors`` CSP. Origins are
public information (they appear in every embedding page).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from nexus_api.api.deps import (
    EmbedContext,
    get_db_session,
    scoped_session_from_embed_jwt,
)
from nexus_api.db.models import (
    Broadcast,
    BroadcastRecipient,
    BroadcastRecipientStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Message,
)
from nexus_api.repositories.partner import PartnerApiKeyRepository, PartnerRepository
from nexus_api.schemas.embed import (
    BroadcastAcceptedOut,
    BroadcastCreateIn,
    BroadcastRecipientStatusOut,
    BroadcastStatusOut,
    EmbedStatusOut,
    EmbedTemplatesOut,
    PartnerConfigOut,
)
from nexus_api.services.broadcasts import create_broadcast
from nexus_api.services.whatsapp_templates import fetch_templates

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/embed", tags=["embed"])


@router.get("/partner-config", response_model=PartnerConfigOut)
async def partner_config(
    response: Response,
    p: str = Query(min_length=2, max_length=80, description="partner slug"),
    session=Depends(get_db_session),
) -> PartnerConfigOut:
    """Union of ``allowed_origins`` across the partner's active keys.
    Cached at the CDN edge — the embed middleware calls this on every
    document request."""
    partner = await PartnerRepository(session).get_by_slug(p)
    response.headers["Cache-Control"] = "public, s-maxage=300, max-age=60"
    if partner is None or partner.status != "active":
        # Same shape as an empty partner — no slug enumeration signal
        # beyond what the (public) slug already is.
        return PartnerConfigOut(allowed_origins=[])
    origins: set[str] = set()
    from datetime import UTC, datetime

    from nexus_api.core.partner_auth import key_is_active

    now = datetime.now(UTC)
    for key in await PartnerApiKeyRepository(session).list_for_partner(partner.id):
        if key_is_active(key, now=now):
            origins.update(key.allowed_origins or [])
    return PartnerConfigOut(allowed_origins=sorted(origins))


@router.get("/status", response_model=EmbedStatusOut)
async def embed_status(
    ctx: EmbedContext = Depends(scoped_session_from_embed_jwt),
) -> EmbedStatusOut:
    result = await ctx.session.execute(
        sa.select(Channel.provider_identifier)
        .where(
            Channel.type == ChannelType.WHATSAPP,
            Channel.status == ChannelStatus.ACTIVE,
        )
        .limit(1)
    )
    phone = result.scalar_one_or_none()
    if phone is None:
        return EmbedStatusOut(status="not_connected", display_phone_number=None)
    return EmbedStatusOut(status="connected", display_phone_number=phone)


@router.get("/templates", response_model=EmbedTemplatesOut)
async def embed_templates(
    ctx: EmbedContext = Depends(scoped_session_from_embed_jwt),
) -> EmbedTemplatesOut:
    """Only APPROVED templates — the modal must not offer a template
    Meta would reject at send time."""
    if "widget:send" not in ctx.claims.scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session token lacks widget:send scope",
        )
    templates, _waba_id = await fetch_templates(ctx.session)
    approved = [t for t in templates if (t.status or "").upper() == "APPROVED"]
    return EmbedTemplatesOut(templates=approved)


def _require_send_scope(ctx: EmbedContext) -> None:
    if "widget:send" not in ctx.claims.scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session token lacks widget:send scope",
        )


@router.post("/broadcasts", response_model=BroadcastAcceptedOut, status_code=202)
async def create_embed_broadcast(
    body: BroadcastCreateIn,
    response: Response,
    ctx: EmbedContext = Depends(scoped_session_from_embed_jwt),
) -> BroadcastAcceptedOut:
    """Fan out a template to N recipients. 202: the rows are queued for
    the outbound dispatcher; per-recipient delivery is async (poll
    ``GET /broadcasts/{id}``). Idempotent replays return 200."""
    _require_send_scope(ctx)
    result, created = await create_broadcast(
        ctx.session,
        tenant_id=ctx.claims.tenant_id,
        partner_id=ctx.claims.partner_id,
        recipient_cap=ctx.partner.broadcast_recipient_cap,
        jti=ctx.claims.jti,
        payload=body,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastStatusOut)
async def get_embed_broadcast(
    broadcast_id: uuid.UUID,
    ctx: EmbedContext = Depends(scoped_session_from_embed_jwt),
) -> BroadcastStatusOut:
    """Counters + per-recipient state. Delivery state comes from the
    JOIN to ``messages`` — the status webhook advances it, nothing is
    duplicated here."""
    _require_send_scope(ctx)
    broadcast = await ctx.session.get(Broadcast, broadcast_id)
    if broadcast is None:  # RLS already hides other tenants' rows
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    rows = (
        await ctx.session.execute(
            sa.select(BroadcastRecipient, Message.status, Message.failure_code)
            .outerjoin(Message, Message.id == BroadcastRecipient.message_id)
            .where(BroadcastRecipient.broadcast_id == broadcast.id)
            .order_by(BroadcastRecipient.created_at)
        )
    ).all()

    counts: dict[str, int] = {}
    recipients: list[BroadcastRecipientStatusOut] = []
    for recipient, msg_status, failure_code in rows:
        if recipient.status == BroadcastRecipientStatus.REJECTED.value:
            state, reason = "rejected", recipient.reject_reason
        elif msg_status is None:
            state, reason = "queued", None
        else:
            state = msg_status.value if hasattr(msg_status, "value") else str(msg_status)
            reason = failure_code
        counts[state] = counts.get(state, 0) + 1
        recipients.append(
            BroadcastRecipientStatusOut(phone=recipient.phone_e164, status=state, reason=reason)
        )

    return BroadcastStatusOut(
        broadcast_id=broadcast.id,
        template_name=broadcast.template_name,
        status=broadcast.status,
        created_at=broadcast.created_at,
        counts=counts,
        recipients=recipients,
    )
