"""Backfill existing channels + tenant_credentials rows into tenant_connectors.

One-time migration ladder rung for Bloque L. Idempotent: re-runs detect
existing tenant_connectors rows and skip.

What it does:

- For each ``channels`` row with ``type='whatsapp'`` AND ``provider='ycloud'``
  → insert/update a tenant_connectors row for connector slug ``whatsapp_ycloud``
  with ``credentials_ref = {"channel_id": "<uuid>"}``.

- For each ``tenant_credentials`` row with ``integration='agendapro'``
  → insert/update a tenant_connectors row for connector slug ``agendapro``
  with ``credentials_ref = {"tenant_credentials_id": "<uuid>"}`` (we don't
  copy context_id here — runtime reads it from the encrypted payload on
  demand).

Run once after migration 0013 + seed_connectors.py.

The script runs under RLS via ``apply_tenant_to_session`` per tenant so the
INSERT into ``tenant_connectors`` complies with the row-level policy.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.core.tenant_context import apply_tenant_to_session
from nexus_api.db.base import dispose_engine, get_engine
from nexus_api.db.models import (
    Channel,
    ChannelType,
    Connector,
    TenantConnector,
    TenantConnectorStatus,
    TenantCredentials,
)
from nexus_api.logging import configure_logging

configure_logging()
log = structlog.get_logger(__name__)


async def _backfill_one(
    session, tenant_id, connector, credentials_ref: dict
) -> str:
    """Idempotent UPSERT under the tenant's RLS scope."""
    await apply_tenant_to_session(session, tenant_id)
    existing = await session.scalar(
        select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id,
            TenantConnector.connector_id == connector.id,
        )
    )
    if existing:
        if existing.status != TenantConnectorStatus.CONNECTED.value:
            existing.status = TenantConnectorStatus.CONNECTED.value
            existing.credentials_ref = credentials_ref
            existing.connected_at = existing.connected_at or datetime.now(UTC)
            return "updated"
        return "unchanged"
    row = TenantConnector(
        tenant_id=tenant_id,
        connector_id=connector.id,
        status=TenantConnectorStatus.CONNECTED.value,
        credentials_ref=credentials_ref,
        scopes_granted=[],
        config={},
        connected_at=datetime.now(UTC),
    )
    session.add(row)
    return "inserted"


async def main() -> int:
    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    stats = {"inserted": 0, "updated": 0, "unchanged": 0}

    async with factory() as global_session:
        # Disable RLS for the discovery query — we need to see ALL tenants.
        await global_session.execute(text("SET LOCAL row_security = off"))
        wa_connector = await global_session.scalar(
            select(Connector).where(Connector.slug == "whatsapp_ycloud")
        )
        ap_connector = await global_session.scalar(
            select(Connector).where(Connector.slug == "agendapro")
        )
        if wa_connector is None or ap_connector is None:
            log.error(
                "migrate_to_connectors.catalog_missing",
                whatsapp=wa_connector is not None,
                agendapro=ap_connector is not None,
            )
            print(
                "ERROR: connectors catalog missing rows; "
                "run apps/api/scripts/seed_connectors.py first"
            )
            return 2

        await global_session.execute(text("SET LOCAL row_security = off"))
        channels = (
            await global_session.scalars(
                select(Channel).where(
                    Channel.type == ChannelType.WHATSAPP, Channel.provider == "ycloud"
                )
            )
        ).all()
        credentials = (
            await global_session.scalars(
                select(TenantCredentials).where(
                    TenantCredentials.integration == "agendapro"
                )
            )
        ).all()

    log.info(
        "migrate_to_connectors.discovered",
        whatsapp_channels=len(channels),
        agendapro_credentials=len(credentials),
    )

    for ch in channels:
        async with factory() as s, s.begin():
            outcome = await _backfill_one(
                s,
                ch.tenant_id,
                wa_connector,
                credentials_ref={"channel_id": str(ch.id)},
            )
            stats[outcome] += 1
            log.info(
                "migrate_to_connectors.whatsapp",
                tenant_id=str(ch.tenant_id),
                channel_id=str(ch.id),
                outcome=outcome,
            )

    for cr in credentials:
        async with factory() as s, s.begin():
            outcome = await _backfill_one(
                s,
                cr.tenant_id,
                ap_connector,
                credentials_ref={"tenant_credentials_id": str(cr.id)},
            )
            stats[outcome] += 1
            log.info(
                "migrate_to_connectors.agendapro",
                tenant_id=str(cr.tenant_id),
                credentials_id=str(cr.id),
                outcome=outcome,
            )

    print(
        f"backfill: inserted={stats['inserted']} "
        f"updated={stats['updated']} unchanged={stats['unchanged']}"
    )
    await dispose_engine()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
