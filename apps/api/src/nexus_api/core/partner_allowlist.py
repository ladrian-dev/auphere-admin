"""Lectura/escritura de ``partner_model_allowlist`` bajo GUC ya fijado."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.partner_model_allowlist import PartnerModelAllowlist


async def read_allowlist(session: AsyncSession, partner_id: uuid.UUID) -> frozenset[str]:
    rows = await session.scalars(
        sa.select(PartnerModelAllowlist.model_id).where(
            PartnerModelAllowlist.partner_id == partner_id
        )
    )
    return frozenset(str(mid) for mid in rows.all())


async def replace_allowlist(
    session: AsyncSession, partner_id: uuid.UUID, model_ids: list[str]
) -> frozenset[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for mid in model_ids:
        if mid in seen:
            continue
        seen.add(mid)
        unique.append(mid)
    await session.execute(
        sa.delete(PartnerModelAllowlist).where(PartnerModelAllowlist.partner_id == partner_id)
    )
    for mid in unique:
        session.add(PartnerModelAllowlist(partner_id=partner_id, model_id=mid))
    await session.flush()
    return frozenset(unique)
