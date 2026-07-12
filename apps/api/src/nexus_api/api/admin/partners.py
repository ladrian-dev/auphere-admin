"""Admin CRUD for the partner platform (ADR-028) — operator panel only.

Everything here runs under ``require_admin_token`` and as the table
owner (no tenant scope): these are platform tables. The one-time
plaintext key is returned exactly once from create/rotate; only the
SHA-256 lands in the DB.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import Partner, PartnerApiKey, PartnerTenant, Tenant
from nexus_api.repositories.partner import (
    EmbedAuditRepository,
    PartnerApiKeyRepository,
    PartnerRepository,
    PartnerTenantRepository,
)
from nexus_api.schemas.partner import (
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyOut,
    ApiKeyRotateIn,
    EmbedAuditEntryOut,
    OriginsUpdateIn,
    PartnerCreateIn,
    PartnerOut,
    PartnerTenantLinkIn,
    PartnerTenantOut,
    PartnerUpdateIn,
    PartnerUsageOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


async def _get_partner_or_404(session: AsyncSession, partner_id: uuid.UUID) -> Partner:
    partner = await PartnerRepository(session).get(partner_id)
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"partner {partner_id} not found",
        )
    return partner


@router.get("", response_model=list[PartnerOut])
async def list_partners(session: AsyncSession = Depends(get_db_session)) -> list[PartnerOut]:
    partners = await PartnerRepository(session).list_all()
    return [PartnerOut.model_validate(p) for p in partners]


@router.post("", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
async def create_partner(
    body: PartnerCreateIn,
    session: AsyncSession = Depends(get_db_session),
) -> PartnerOut:
    try:
        async with session.begin():
            partner = await PartnerRepository(session).create(
                Partner(
                    id=uuid.uuid4(),
                    name=body.name,
                    slug=body.slug,
                    contact_email=body.contact_email,
                )
            )
            await EmbedAuditRepository(session).record(
                event="partner.created",
                partner_id=partner.id,
                payload={"slug": body.slug},
            )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"slug {body.slug!r} is already taken",
        ) from exc
    return PartnerOut.model_validate(partner)


@router.get("/{partner_id}", response_model=PartnerOut)
async def get_partner(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> PartnerOut:
    return PartnerOut.model_validate(await _get_partner_or_404(session, partner_id))


@router.patch("/{partner_id}", response_model=PartnerOut)
async def update_partner(
    partner_id: uuid.UUID,
    body: PartnerUpdateIn,
    session: AsyncSession = Depends(get_db_session),
) -> PartnerOut:
    async with session.begin():
        partner = await _get_partner_or_404(session, partner_id)
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        # Blueprint refs (Fase 2b): empty string clears; a non-empty value
        # must exist so a typo doesn't surface later as a broken provision.
        if "default_seed_template" in changes:
            if changes["default_seed_template"] == "":
                changes["default_seed_template"] = None
            else:
                from nexus_api.services.templating.seed_templates import list_seed_templates

                if changes["default_seed_template"] not in list_seed_templates():
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"seed template {changes['default_seed_template']!r} not found",
                    )
        if "default_connector_slug" in changes:
            if changes["default_connector_slug"] == "":
                changes["default_connector_slug"] = None
            else:
                import sqlalchemy as sa

                from nexus_api.db.models import Connector

                connector = await session.scalar(
                    sa.select(Connector).where(Connector.slug == changes["default_connector_slug"])
                )
                if connector is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"connector {changes['default_connector_slug']!r} not found",
                    )
        for field, value in changes.items():
            setattr(partner, field, value)
        if changes:
            await EmbedAuditRepository(session).record(
                event="partner.updated",
                partner_id=partner.id,
                payload={"fields": sorted(changes)},
            )
    return PartnerOut.model_validate(partner)


# ── API keys ─────────────────────────────────────────────────────────────────


@router.get("/{partner_id}/keys", response_model=list[ApiKeyOut])
async def list_keys(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[ApiKeyOut]:
    await _get_partner_or_404(session, partner_id)
    keys = await PartnerApiKeyRepository(session).list_for_partner(partner_id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post(
    "/{partner_id}/keys",
    response_model=ApiKeyCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_key(
    partner_id: uuid.UUID,
    body: ApiKeyCreateIn,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyCreatedOut:
    generated = generate_api_key(body.type)
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        key = await PartnerApiKeyRepository(session).create(
            PartnerApiKey(
                id=uuid.uuid4(),
                partner_id=partner_id,
                type=body.type,
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=body.scopes,
                allowed_origins=body.allowed_origins,
                expires_at=body.expires_at,
            )
        )
        await EmbedAuditRepository(session).record(
            event="key.created",
            partner_id=partner_id,
            api_key_id=key.id,
            payload={"type": body.type, "scopes": body.scopes},
        )
    return ApiKeyCreatedOut(
        plaintext=generated.plaintext, **ApiKeyOut.model_validate(key).model_dump()
    )


@router.post(
    "/{partner_id}/keys/{key_id}/rotate",
    response_model=ApiKeyCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def rotate_key(
    partner_id: uuid.UUID,
    key_id: uuid.UUID,
    body: ApiKeyRotateIn,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyCreatedOut:
    """Create a replacement key and put the old one on a grace timer.
    The old key keeps authenticating until ``grace_expires_at`` so the
    partner can deploy the new secret without downtime."""
    async with session.begin():
        keys = PartnerApiKeyRepository(session)
        old = await keys.get(key_id)
        if old is None or old.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found")
        if old.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="key is already revoked",
            )
        now = datetime.now(UTC)
        old.revoked_at = now
        old.grace_expires_at = now + timedelta(hours=body.grace_hours)

        generated = generate_api_key(old.type)
        new = await keys.create(
            PartnerApiKey(
                id=uuid.uuid4(),
                partner_id=partner_id,
                type=old.type,
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=list(old.scopes or []),
                allowed_origins=list(old.allowed_origins or []),
                expires_at=old.expires_at,
            )
        )
        await EmbedAuditRepository(session).record(
            event="key.rotated",
            partner_id=partner_id,
            api_key_id=new.id,
            payload={"replaces": str(key_id), "grace_hours": body.grace_hours},
        )
    return ApiKeyCreatedOut(
        plaintext=generated.plaintext, **ApiKeyOut.model_validate(new).model_dump()
    )


@router.post("/{partner_id}/keys/{key_id}/revoke", response_model=ApiKeyOut)
async def revoke_key(
    partner_id: uuid.UUID,
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyOut:
    """Immediate, no grace: the key (and every live session token minted
    with it — the embed verifier re-checks per request) dies now."""
    async with session.begin():
        key = await PartnerApiKeyRepository(session).get(key_id)
        if key is None or key.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found")
        key.revoked_at = datetime.now(UTC)
        key.grace_expires_at = None
        await EmbedAuditRepository(session).record(
            event="key.revoked",
            partner_id=partner_id,
            api_key_id=key.id,
        )
    return ApiKeyOut.model_validate(key)


@router.put("/{partner_id}/keys/{key_id}/origins", response_model=ApiKeyOut)
async def update_origins(
    partner_id: uuid.UUID,
    key_id: uuid.UUID,
    body: OriginsUpdateIn,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyOut:
    for origin in body.allowed_origins:
        if not origin.startswith("https://") and not origin.startswith("http://localhost"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"origin must be https (or http://localhost for dev): {origin}",
            )
    async with session.begin():
        key = await PartnerApiKeyRepository(session).get(key_id)
        if key is None or key.partner_id != partner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found")
        key.allowed_origins = body.allowed_origins
        await EmbedAuditRepository(session).record(
            event="key.origins_updated",
            partner_id=partner_id,
            api_key_id=key.id,
            payload={"allowed_origins": body.allowed_origins},
        )
    return ApiKeyOut.model_validate(key)


# ── Tenant mappings ──────────────────────────────────────────────────────────


@router.get("/{partner_id}/tenants", response_model=list[PartnerTenantOut])
async def list_tenant_mappings(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[PartnerTenantOut]:
    await _get_partner_or_404(session, partner_id)
    mappings = await PartnerTenantRepository(session).list_for_partner(partner_id)
    return [PartnerTenantOut.model_validate(m) for m in mappings]


@router.post(
    "/{partner_id}/tenants",
    response_model=PartnerTenantOut,
    status_code=status.HTTP_201_CREATED,
)
async def link_tenant(
    partner_id: uuid.UUID,
    body: PartnerTenantLinkIn,
    session: AsyncSession = Depends(get_db_session),
) -> PartnerTenantOut:
    """Manually map an existing tenant to a partner client ref — the
    operator-assisted onboarding path while self-serve signup lands."""
    try:
        async with session.begin():
            await _get_partner_or_404(session, partner_id)
            if await session.get(Tenant, body.tenant_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"tenant {body.tenant_id} not found",
                )
            mapping = await PartnerTenantRepository(session).create(
                PartnerTenant(
                    partner_id=partner_id,
                    external_client_ref=body.external_client_ref,
                    tenant_id=body.tenant_id,
                    client_name=body.client_name,
                )
            )
            await EmbedAuditRepository(session).record(
                event="tenant.linked",
                partner_id=partner_id,
                tenant_id=body.tenant_id,
                payload={"external_client_ref": body.external_client_ref},
            )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="client ref or tenant already mapped for this partner",
        ) from exc
    return PartnerTenantOut.model_validate(mapping)


# ── Usage (metrics / billing) ───────────────────────────────────────────────


@router.get("/{partner_id}/usage", response_model=PartnerUsageOut)
async def partner_usage(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    window_days: int = Query(default=30, ge=1, le=365),
) -> PartnerUsageOut:
    """Aggregated usage across every tenant mapped to the partner —
    the billing/metrics view. Tenant-scoped tables (channels,
    agent_configs, broadcasts, messages) are RLS-protected, so each
    tenant is read in its own short scoped transaction (same pattern as
    ``_whatsapp_status`` on the provision surface); N is the partner's
    client count, small by construction.
    """
    import sqlalchemy as sa

    from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
    from nexus_api.db.models import (
        AgentConfig,
        AgentConfigStatus,
        Broadcast,
        BroadcastRecipient,
        Channel,
        ChannelStatus,
        ChannelType,
        Message,
        MessageDirection,
    )
    from nexus_api.schemas.partner import PartnerClientUsageOut, PartnerUsageOut

    # Reads run in their own transaction block — autobegin would collide
    # with the explicit per-tenant ``begin()`` below.
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        mappings = await PartnerTenantRepository(session).list_for_partner(partner_id)
    since = datetime.now(UTC) - timedelta(days=window_days)

    clients: list[PartnerClientUsageOut] = []
    for mapping in mappings:
        ctx_token = _current_tenant.set(mapping.tenant_id)
        try:
            async with session.begin():
                await apply_tenant_to_session(session, mapping.tenant_id)
                tenant = await session.get(Tenant, mapping.tenant_id)
                phone = await session.scalar(
                    sa.select(Channel.provider_identifier)
                    .where(
                        Channel.type == ChannelType.WHATSAPP,
                        Channel.status == ChannelStatus.ACTIVE,
                    )
                    .limit(1)
                )
                agent = await session.scalar(
                    sa.select(AgentConfig)
                    .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                    .limit(1)
                )
                broadcasts, recipients = (
                    await session.execute(
                        sa.select(
                            sa.func.count(sa.distinct(Broadcast.id)),
                            sa.func.count(BroadcastRecipient.id),
                        )
                        .select_from(Broadcast)
                        .outerjoin(
                            BroadcastRecipient,
                            BroadcastRecipient.broadcast_id == Broadcast.id,
                        )
                        .where(Broadcast.created_at >= since)
                    )
                ).one()
                inbound, outbound, cost = (
                    await session.execute(
                        sa.select(
                            sa.func.count(Message.id).filter(
                                Message.direction == MessageDirection.INBOUND
                            ),
                            sa.func.count(Message.id).filter(
                                Message.direction == MessageDirection.OUTBOUND
                            ),
                            sa.func.coalesce(sa.func.sum(Message.cost_usd), 0.0),
                        ).where(Message.created_at >= since)
                    )
                ).one()
        finally:
            _current_tenant.reset(ctx_token)

        clients.append(
            PartnerClientUsageOut(
                external_client_ref=mapping.external_client_ref,
                client_name=mapping.client_name,
                tenant_id=mapping.tenant_id,
                tenant_status=tenant.status.value if tenant else "unknown",
                whatsapp_connected=phone is not None,
                agent_version=agent.version if agent else None,
                agent_seed_template=agent.seed_template_ref if agent else None,
                broadcasts=broadcasts,
                broadcast_recipients=recipients,
                messages_inbound=inbound,
                messages_outbound=outbound,
                cost_usd=float(cost),
            )
        )

    return PartnerUsageOut(
        partner_id=partner_id,
        window_days=window_days,
        clients_total=len(clients),
        clients_active=sum(1 for c in clients if c.tenant_status == "active"),
        clients_whatsapp_connected=sum(1 for c in clients if c.whatsapp_connected),
        clients_with_agent=sum(1 for c in clients if c.agent_version is not None),
        broadcasts=sum(c.broadcasts for c in clients),
        broadcast_recipients=sum(c.broadcast_recipients for c in clients),
        messages_inbound=sum(c.messages_inbound for c in clients),
        messages_outbound=sum(c.messages_outbound for c in clients),
        cost_usd=round(sum(c.cost_usd for c in clients), 6),
        clients=clients,
    )


# ── Audit ────────────────────────────────────────────────────────────────────


@router.get("/{partner_id}/audit", response_model=list[EmbedAuditEntryOut])
async def list_audit(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    limit: int = 100,
) -> list[EmbedAuditEntryOut]:
    await _get_partner_or_404(session, partner_id)
    entries = await EmbedAuditRepository(session).list_for_partner(
        partner_id, limit=min(limit, 500)
    )
    return [EmbedAuditEntryOut.model_validate(e) for e in entries]
