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
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import (
    EmbedContext,
    get_db_session,
    get_redis,
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
    EmbedSignupIn,
    EmbedSignupOut,
    EmbedStatusOut,
    EmbedTemplatesOut,
    PartnerConfigOut,
)
from nexus_api.services.broadcasts import create_broadcast
from nexus_api.services.partner_provisioning import activate_tenant_if_ready
from nexus_api.services.whatsapp_templates import fetch_templates

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/embed", tags=["embed"])


@router.get("/partner-config", response_model=PartnerConfigOut)
async def partner_config(
    response: Response,
    p: str = Query(min_length=2, max_length=80, description="partner slug"),
    session: AsyncSession = Depends(get_db_session),
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


@router.post("/whatsapp/signup", response_model=EmbedSignupOut, status_code=201)
async def embed_whatsapp_signup(
    body: EmbedSignupIn,
    ctx: EmbedContext = Depends(scoped_session_from_embed_jwt),
    redis: Redis = Depends(get_redis),
) -> EmbedSignupOut:
    """Complete Meta Embedded Signup from the ``/signup`` iframe (ADR-028
    Fase 2). Public variant of ``/admin/tenants/{id}/integrations/meta/
    signup`` — same orchestrator, but the tenant comes exclusively from
    the widget JWT claims and the audit lands in ``embed_audit_log``.

    On success, hands off to ``activate_tenant_if_ready``: partners with
    ``auto_activate`` get the tenant flipped PROVISIONING → ACTIVE when a
    promoted agent_config exists, so the number starts answering without
    an operator in the loop.
    """
    if "widget:connect" not in ctx.claims.scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session token lacks widget:connect scope",
        )

    from nexus_channels.whatsapp_meta import (
        EmbeddedSignupOrchestrator,
        MetaAPIError,
        MetaClient,
        SignupIngressPayload,
    )
    from nexus_channels.whatsapp_meta.exceptions import (
        RegisterPhoneError,
        SubscribeWebhookError,
        TokenExchangeError,
    )

    from nexus_api.config import get_settings

    settings = get_settings()
    client = MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )
    orchestrator = EmbeddedSignupOrchestrator(
        session=ctx.session,
        redis=redis,
        client=client,
        app_id=settings.meta_app_id,
        webhook_callback_url=settings.meta_webhook_callback_url,
        webhook_verify_token=settings.meta_webhook_verify_token,
    )
    payload = SignupIngressPayload(
        code=body.code,
        waba_id=body.waba_id,
        phone_number_id=body.phone_number_id,
        business_id=body.business_id,
        mode=body.mode,
    )
    try:
        result = await orchestrator.complete(payload)
    except TokenExchangeError as exc:
        log.warning("embed.signup.code_exchange_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Meta rejected the OAuth code — it expired or was already "
                "consumed. Close the dialog and retry the connection."
            ),
        ) from exc
    except RegisterPhoneError as exc:
        log.warning("embed.signup.register_phone_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Meta did not accept the phone registration. Usual cause: the "
                "number is registered under another app with a different PIN."
            ),
        ) from exc
    except SubscribeWebhookError as exc:
        log.warning("embed.signup.subscribe_webhook_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta did not accept the webhook subscription. Retry the connection.",
        ) from exc
    except MetaAPIError as exc:
        log.warning(
            "embed.signup.api_error",
            status=exc.status_code,
            code=exc.code,
            reason=exc.message,
        )
        http_status = (
            status.HTTP_502_BAD_GATEWAY
            if exc.status_code and exc.status_code >= 500
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=http_status, detail=f"Meta API error: {exc.message}"
        ) from exc
    finally:
        await client.close()

    from nexus_api.repositories.partner import EmbedAuditRepository

    await EmbedAuditRepository(ctx.session).record(
        event="whatsapp.signup.completed",
        partner_id=ctx.claims.partner_id,
        api_key_id=ctx.claims.key_id,
        tenant_id=ctx.claims.tenant_id,
        payload={
            "waba_id": result.waba_id,
            "phone_number_id": result.phone_number_id,
            "display_phone_number": result.display_phone_number,
            "mode": result.mode,
            "channel_id": str(result.channel_id),
        },
        jti=ctx.claims.jti,
    )

    activated = await activate_tenant_if_ready(
        ctx.session,
        partner=ctx.partner,
        tenant_id=ctx.claims.tenant_id,
        api_key_id=ctx.claims.key_id,
        jti=ctx.claims.jti,
    )

    log.info(
        "embed.signup.success",
        tenant_id=str(ctx.claims.tenant_id),
        partner_id=str(ctx.claims.partner_id),
        channel_id=str(result.channel_id),
        waba_id=result.waba_id,
        tenant_activated=activated,
    )
    return EmbedSignupOut(
        status="connected",
        display_phone_number=result.display_phone_number,
        tenant_activated=activated,
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
