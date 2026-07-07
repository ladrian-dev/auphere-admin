"""Public partner surface: ``/v1/partners/*`` + ``/v1/widget-sessions`` (ADR-028).

Server-to-server only — authenticated with the partner's secret API key
(``core/partner_auth.py``). This is the ONLY place in the platform where
a ``tenant_id`` is chosen for a widget session, and the choice is gated
by the ``partner_tenants`` allow-list under the authenticated partner's
id. The browser-facing surface (``/v1/embed/*``) then reads the tenant
exclusively from the signed JWT claims.

Responses never contain internal tenant ids: the partner speaks
``external_client_ref``, we translate.
"""

from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core import rate_limit
from nexus_api.core.embed_jwt import mint_widget_token
from nexus_api.core.partner_auth import PartnerContext, require_partner_key
from nexus_api.core.tenant_context import apply_tenant_to_session
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.repositories.partner import EmbedAuditRepository, PartnerTenantRepository
from nexus_api.schemas.partner import (
    ClientProvisionIn,
    ClientProvisionOut,
    WhatsAppStatusOut,
    WidgetSessionIn,
    WidgetSessionOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["partners"])

# Session scopes a widget token carries. ``widget:connect`` is reserved
# for the Phase 2 self-serve signup; shipping it in the claims now keeps
# the token shape stable.
_WIDGET_SCOPES = ["widget:send", "widget:connect"]

_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")


def _client_slug(partner_slug: str, external_client_ref: str) -> str:
    """Deterministic, unique tenant slug for a partner's client.

    The ref is the partner's arbitrary string — slugify what we can and
    append a short digest of the exact ref so two refs that normalise to
    the same text (e.g. ``client_42`` vs ``client 42``) can't collide.
    """
    normalised = _SLUG_SAFE.sub("-", external_client_ref.lower()).strip("-") or "client"
    digest = uuid.uuid5(uuid.NAMESPACE_URL, external_client_ref).hex[:8]
    return f"p-{partner_slug}-{normalised}"[:70] + f"-{digest}"


async def _whatsapp_status(session: AsyncSession, tenant_id: uuid.UUID) -> WhatsAppStatusOut:
    """Read the tenant's WhatsApp channel under RLS scope.

    Runs in its own short transaction: ``set_config(app.tenant_id)`` is
    transaction-local, so nothing leaks into the caller's work.
    """
    async with session.begin():
        await apply_tenant_to_session(session, tenant_id)
        result = await session.execute(
            sa.select(Channel.provider_identifier)
            .where(
                Channel.type == ChannelType.WHATSAPP,
                Channel.status == ChannelStatus.ACTIVE,
            )
            .limit(1)
        )
        phone = result.scalar_one_or_none()
    if phone is None:
        return WhatsAppStatusOut(status="not_connected", display_phone_number=None)
    return WhatsAppStatusOut(status="connected", display_phone_number=phone)


@router.post(
    "/partners/clients",
    response_model=ClientProvisionOut,
    status_code=status.HTTP_200_OK,
)
async def provision_client(
    body: ClientProvisionIn,
    request: Request,
    ctx: PartnerContext = Depends(require_partner_key("provision")),
    session: AsyncSession = Depends(get_db_session),
) -> ClientProvisionOut:
    """Idempotent: registering the same ``external_client_ref`` twice
    returns the existing mapping. First registration creates the tenant
    just-in-time with status ``provisioning`` (no channel until the
    WhatsApp signup completes)."""
    mappings = PartnerTenantRepository(session)

    # Reads and writes each run in their own transaction block — SQLAlchemy
    # autobegin would otherwise collide with the explicit ``begin()`` below.
    async with session.begin():
        mapping = await mappings.get_mapping(ctx.partner.id, body.external_client_ref)
    if mapping is None:
        try:
            async with session.begin():
                tenant = Tenant(
                    id=uuid.uuid4(),
                    name=body.name,
                    slug=_client_slug(ctx.partner.slug, body.external_client_ref),
                    status=TenantStatus.PROVISIONING,
                    timezone=body.timezone,
                )
                session.add(tenant)
                await session.flush()
                mapping = await mappings.create(
                    PartnerTenant(
                        partner_id=ctx.partner.id,
                        external_client_ref=body.external_client_ref,
                        tenant_id=tenant.id,
                        client_name=body.name,
                    )
                )
                await EmbedAuditRepository(session).record(
                    event="client.provisioned",
                    partner_id=ctx.partner.id,
                    api_key_id=ctx.api_key.id,
                    tenant_id=tenant.id,
                    payload={"external_client_ref": body.external_client_ref},
                    ip=request.client.host if request.client else None,
                )
        except IntegrityError:
            # Lost a race against a concurrent provision of the same ref —
            # the winner's row is the truth.
            async with session.begin():
                mapping = await mappings.get_mapping(ctx.partner.id, body.external_client_ref)
            if mapping is None:  # pragma: no cover - defensive
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="provisioning conflict",
                ) from None

    whatsapp = await _whatsapp_status(session, mapping.tenant_id)
    return ClientProvisionOut(
        external_client_ref=body.external_client_ref,
        status="provisioned",
        whatsapp=whatsapp,
    )


@router.post(
    "/widget-sessions",
    response_model=WidgetSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_widget_session(
    body: WidgetSessionIn,
    request: Request,
    ctx: PartnerContext = Depends(require_partner_key("widget_sessions")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> WidgetSessionOut:
    """Mint a short-lived session JWT scoped to exactly one tenant.

    The tenant is resolved through ``partner_tenants`` under the
    authenticated partner — an unknown ref is an opaque 404 (we don't
    reveal whether the ref exists for someone else)."""
    if not await rate_limit.allow(
        redis,
        key=rate_limit.mint_bucket_key(str(ctx.partner.id)),
        per_minute=ctx.partner.rate_limit_mint_per_min,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    async with session.begin():
        mapping = await PartnerTenantRepository(session).get_mapping(
            ctx.partner.id, body.external_client_ref
        )
        tenant = await session.get(Tenant, mapping.tenant_id) if mapping is not None else None
    if (
        mapping is None
        or tenant is None
        or tenant.status not in (TenantStatus.ACTIVE, TenantStatus.PROVISIONING)
    ):
        # Opaque 404 — don't reveal whether the ref exists in another state.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown client reference",
        )

    token, jti, expires_in = mint_widget_token(
        tenant_id=mapping.tenant_id,
        partner_id=ctx.partner.id,
        key_id=ctx.api_key.id,
        scope=_WIDGET_SCOPES,
        allowed_origins=list(ctx.api_key.allowed_origins or []),
    )

    async with session.begin():
        await EmbedAuditRepository(session).record(
            event="session.minted",
            partner_id=ctx.partner.id,
            api_key_id=ctx.api_key.id,
            tenant_id=mapping.tenant_id,
            payload={"external_client_ref": body.external_client_ref},
            ip=request.client.host if request.client else None,
            jti=jti,
        )

    whatsapp = await _whatsapp_status(session, mapping.tenant_id)
    return WidgetSessionOut(session_token=token, expires_in=expires_in, whatsapp=whatsapp)
