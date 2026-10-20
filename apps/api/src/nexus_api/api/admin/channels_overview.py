"""Admin — channels and connectors across every client (spec 035).

``channels`` and ``tenant_connectors`` are tenant tables with RLS. The global
views read them **client by client, each under its own GUC**
(``tenant_scoped_session``) and label every row with the client it came from.
RLS is never lifted. The Playground's internal channels are left out.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, Partner, Tenant, TenantConnector
from nexus_api.db.models.channel import QA_PLAYGROUND_PROVIDER
from nexus_api.services.channel_catalog import channel_catalog

log = structlog.get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_admin_token)])


class ChannelCatalogOut(BaseModel):
    key: str
    name: str
    description: str
    availability: str
    note: str | None


class GlobalChannelOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str
    partner_id: uuid.UUID | None
    partner_name: str | None
    type: str
    provider: str
    provider_identifier: str
    status: str
    role: str | None
    agent_enabled: bool
    name: str | None
    created_at: datetime


class ConnectorInstallOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    status: str


class GlobalChannelsOut(BaseModel):
    channels: list[GlobalChannelOut]
    #: Clients whose channels could not be read (named, never hidden).
    unreadable: list[uuid.UUID]


@router.get("/channel-catalog", response_model=list[ChannelCatalogOut])
async def get_channel_catalog() -> list[ChannelCatalogOut]:
    return [
        ChannelCatalogOut(
            key=c.key,
            name=c.name,
            description=c.description,
            availability=c.availability,
            note=c.note,
        )
        for c in channel_catalog()
    ]


async def _tenants(session: AsyncSession) -> list[tuple[Tenant, Partner | None]]:
    rows = (
        await session.execute(
            sa.select(Tenant, Partner)
            .outerjoin(Partner, Partner.id == Tenant.partner_id)
            .order_by(Tenant.name)
        )
    ).all()
    return [(t, p) for t, p in rows]


def _display(channel: Channel) -> str | None:
    config: dict[str, Any] = channel.config or {}
    for key in ("verified_name", "display_name", "display_phone_number"):
        value = config.get(key)
        if isinstance(value, str) and value:
            return value
    return None


@router.get("/channels", response_model=GlobalChannelsOut)
async def list_all_channels(session: AsyncSession = Depends(get_db_session)) -> GlobalChannelsOut:
    async with session.begin():
        tenants = await _tenants(session)
    sm = get_sessionmaker()
    out: list[GlobalChannelOut] = []
    unreadable: list[uuid.UUID] = []
    for tenant, partner in tenants:
        try:
            async with sm() as s, tenant_scoped_session(s, tenant.id):
                rows = (
                    (
                        await s.execute(
                            sa.select(Channel)
                            .where(Channel.provider != QA_PLAYGROUND_PROVIDER)
                            .order_by(Channel.created_at)
                        )
                    )
                    .scalars()
                    .all()
                )
        except Exception as exc:  # pragma: no cover - surfaced as a partial state
            log.warning("admin.channels.unreadable", tenant_id=str(tenant.id), error=str(exc))
            unreadable.append(tenant.id)
            continue
        for c in rows:
            config = c.config or {}
            out.append(
                GlobalChannelOut(
                    id=c.id,
                    tenant_id=tenant.id,
                    tenant_name=tenant.name,
                    partner_id=partner.id if partner else None,
                    partner_name=partner.name if partner else None,
                    type=str(getattr(c.type, "value", c.type)),
                    provider=c.provider,
                    provider_identifier=c.provider_identifier,
                    status=str(getattr(c.status, "value", c.status)),
                    role=config.get("role") if isinstance(config.get("role"), str) else None,
                    agent_enabled=config.get("agent_enabled", True) is not False,
                    name=_display(c),
                    created_at=c.created_at,
                )
            )
    return GlobalChannelsOut(channels=out, unreadable=unreadable)


@router.get("/connectors-installs", response_model=dict[str, list[ConnectorInstallOut]])
async def list_connector_installs(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, list[ConnectorInstallOut]]:
    """Which clients have each connector, by slug, read client by client."""
    async with session.begin():
        tenants = await _tenants(session)
    sm = get_sessionmaker()
    by_slug: dict[str, list[ConnectorInstallOut]] = {}
    for tenant, _partner in tenants:
        try:
            async with sm() as s, tenant_scoped_session(s, tenant.id):
                rows = (await s.execute(sa.select(TenantConnector))).scalars().all()
                slugs = {
                    cid: slug
                    for cid, slug in (
                        await s.execute(
                            sa.text("SELECT id, slug FROM connectors WHERE id = ANY(:ids)"),
                            {"ids": [r.connector_id for r in rows]},
                        )
                    ).all()
                }
        except Exception as exc:  # pragma: no cover - partial state
            log.warning(
                "admin.connectors.installs_unreadable", tenant_id=str(tenant.id), error=str(exc)
            )
            continue
        for r in rows:
            slug = slugs.get(r.connector_id)
            if slug is None:
                continue
            by_slug.setdefault(slug, []).append(
                ConnectorInstallOut(
                    tenant_id=tenant.id,
                    tenant_name=tenant.name,
                    status=str(getattr(r.status, "value", r.status)),
                )
            )
    return by_slug
