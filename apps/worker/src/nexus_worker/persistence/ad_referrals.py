"""Guardar el clic de un anuncio — spec 076, requisitos 1.1 y 1.2.

Una fila por clic en ``customer_ad_referrals``, en la transacción del mensaje
entrante. El contacto lo fija el servidor (el del mensaje), nunca una petición:
garantía 8. ``ON CONFLICT`` sobre ``(tenant_id, provider_message_id)``: una
redistribución del webhook no duplica.

El log lleva el tipo de origen, nunca el ``ctwa_clid`` (requisito 6.7).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime

import structlog
from nexus_api.db.models import CustomerAdReferral
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


async def store_referral(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    customer_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    provider_message_id: str,
    referral: Mapping[str, str],
    clicked_at: datetime,
) -> None:
    stmt = (
        insert(CustomerAdReferral)
        .values(
            tenant_id=tenant_id,
            channel_id=channel_id,
            customer_id=customer_id,
            conversation_id=conversation_id,
            provider_message_id=provider_message_id,
            source_type=referral["source_type"],
            source_id=referral.get("source_id"),
            source_url=referral.get("source_url"),
            headline=referral.get("headline"),
            ad_text=referral.get("body"),
            media_type=referral.get("media_type"),
            ctwa_clid=referral.get("ctwa_clid"),
            ref=referral.get("ref"),
            clicked_at=clicked_at,
        )
        .on_conflict_do_nothing(constraint="uq_customer_ad_referrals_message")
    )
    await session.execute(stmt)
    log.info(
        "ad_referral.stored",
        tenant_id=str(tenant_id),
        channel_id=str(channel_id),
        source_type=referral["source_type"],
    )
