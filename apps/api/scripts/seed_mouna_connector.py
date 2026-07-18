"""Connect Mouna's Amigable Cobro connector (api_key) in the local DB.

Creates the ``tenant_credentials`` (entity_id + token, encrypted payload)
and the ``tenant_connectors`` row (status=connected, endpoint_meta with the
business_uuid) so the ``billing.*`` tools resolve credentials for Mouna.

Reads the API credentials from the environment (inject via Doppler):
    NEXUS_AMIGABLE_ENTITY_ID, NEXUS_AMIGABLE_TOKEN
    NEXUS_AMIGABLE_BUSINESS_UUID  (default: Mouna's "muna" business)

Usage:
    doppler run -- env NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus \\
      apps/api/.venv/bin/python apps/api/scripts/seed_mouna_connector.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_engine
from nexus_api.db.models.tenant import Tenant
from nexus_api.services.connectors.service import bootstrap_api_key

MOUNA_SLUG = os.environ.get("NEXUS_MOUNA_SLUG", "mouna")
BUSINESS_UUID = os.environ.get(
    "NEXUS_AMIGABLE_BUSINESS_UUID", "9621a21b-7434-46cf-b934-dccedc456e60"
)


async def _amain() -> int:
    entity_id = os.environ.get("NEXUS_AMIGABLE_ENTITY_ID")
    token = os.environ.get("NEXUS_AMIGABLE_TOKEN")
    if not (entity_id and token):
        print("ERROR: set NEXUS_AMIGABLE_ENTITY_ID and NEXUS_AMIGABLE_TOKEN (via Doppler)")
        return 1

    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # Tenant lookup in its own session (tenants is a global table); the write
    # then runs in a fresh, tenant-scoped transaction.
    async with Session() as lookup:
        tenant = (
            await lookup.execute(select(Tenant).where(Tenant.slug == MOUNA_SLUG))
        ).scalar_one_or_none()
    if tenant is None:
        print(f"ERROR: tenant {MOUNA_SLUG!r} not found — run seed_cobranza_tenant.py first")
        return 1

    async with Session() as session:
        # tenant_scoped_session opens the transaction and commits on clean exit.
        async with tenant_scoped_session(session, tenant.id):
            tc = await bootstrap_api_key(
                session,
                tenant=tenant,
                connector_slug="amigable_cobro",
                secret_payload={"entity_id": entity_id, "token": token},
                endpoint_meta={"business_uuid": BUSINESS_UUID},
                actor="seed_mouna_connector.py",
            )
            tc_id, tc_status = tc.id, tc.status
    print(
        f"mouna: amigable_cobro connected — tenant_connector={tc_id} "
        f"status={tc_status} business_uuid={BUSINESS_UUID}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
