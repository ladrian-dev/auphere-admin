"""Repositories for the partner platform tables (ADR-028).

These tables are NOT tenant-scoped (no RLS) — they are the layer that
decides which tenant a widget session may touch. Every method takes the
partner id explicitly; there is no query here that crosses partners.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    EmbedAuditLog,
    Partner,
    PartnerApiKey,
    PartnerTenant,
)


class PartnerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, partner_id: uuid.UUID) -> Partner | None:
        return await self._session.get(Partner, partner_id)

    async def get_by_slug(self, slug: str) -> Partner | None:
        result = await self._session.execute(
            sa.select(Partner).where(Partner.slug == slug).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Partner]:
        result = await self._session.execute(sa.select(Partner).order_by(Partner.created_at))
        return list(result.scalars())

    async def create(self, partner: Partner) -> Partner:
        self._session.add(partner)
        await self._session.flush()
        return partner


class PartnerApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key_id: uuid.UUID) -> PartnerApiKey | None:
        return await self._session.get(PartnerApiKey, key_id)

    async def list_for_partner(self, partner_id: uuid.UUID) -> list[PartnerApiKey]:
        result = await self._session.execute(
            sa.select(PartnerApiKey)
            .where(PartnerApiKey.partner_id == partner_id)
            .order_by(PartnerApiKey.created_at.desc())
        )
        return list(result.scalars())

    async def create(self, key: PartnerApiKey) -> PartnerApiKey:
        self._session.add(key)
        await self._session.flush()
        return key


class PartnerTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_mapping(
        self, partner_id: uuid.UUID, external_client_ref: str
    ) -> PartnerTenant | None:
        return await self._session.get(PartnerTenant, (partner_id, external_client_ref))

    async def mapping_exists(self, partner_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            sa.select(sa.literal(True))
            .select_from(PartnerTenant)
            .where(
                PartnerTenant.partner_id == partner_id,
                PartnerTenant.tenant_id == tenant_id,
            )
            .limit(1)
        )
        return result.scalar() is not None

    async def list_for_partner(self, partner_id: uuid.UUID) -> list[PartnerTenant]:
        result = await self._session.execute(
            sa.select(PartnerTenant)
            .where(PartnerTenant.partner_id == partner_id)
            .order_by(PartnerTenant.created_at)
        )
        return list(result.scalars())

    async def create(self, mapping: PartnerTenant) -> PartnerTenant:
        self._session.add(mapping)
        await self._session.flush()
        return mapping


class EmbedAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        event: str,
        partner_id: uuid.UUID | None = None,
        api_key_id: uuid.UUID | None = None,
        tenant_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        ip: str | None = None,
        origin: str | None = None,
        jti: str | None = None,
    ) -> None:
        self._session.add(
            EmbedAuditLog(
                event=event,
                partner_id=partner_id,
                api_key_id=api_key_id,
                tenant_id=tenant_id,
                payload=payload or {},
                ip=ip,
                origin=origin,
                jti=jti,
            )
        )
        await self._session.flush()

    async def list_for_partner(
        self,
        partner_id: uuid.UUID,
        *,
        limit: int = 100,
        before: datetime | None = None,
    ) -> list[EmbedAuditLog]:
        stmt = (
            sa.select(EmbedAuditLog)
            .where(EmbedAuditLog.partner_id == partner_id)
            .order_by(EmbedAuditLog.created_at.desc())
            .limit(limit)
        )
        if before is not None:
            stmt = stmt.where(EmbedAuditLog.created_at < before)
        result = await self._session.execute(stmt)
        return list(result.scalars())
