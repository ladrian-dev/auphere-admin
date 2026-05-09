"""Seed an internal canary tenant for the Block I production smoke.

Idempotent: re-running picks up the existing tenant by ``slug`` and only
fills in pieces that are missing. Block I uses this against the
freshly-deployed Railway Postgres to verify that:

- The Alembic + Drizzle release commands ran cleanly.
- ``GET /admin/tenants`` lists the canary.
- ``GET /admin/tenants/:id/isolation/metrics`` returns 0s on every
  metric.
- ``GET /admin/tenants/:id/agent-config`` returns the active version.

Block J replaces this script with the real onboarding wizard for
Cultor Barber. The canary tenant should not be deleted between
deployments — it is the smoke fixture that future releases verify
against.

Usage:

    NEXUS_DATABASE_URL=postgresql+asyncpg://... \\
      uv run python apps/api/scripts/seed_canary_tenant.py

The script honours ``NEXUS_CANARY_SLUG`` (default ``auphere-canary``)
so multiple isolated canaries can co-exist (e.g. for the isolation
suite second-tenant runs).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Make ``nexus_api`` importable when the script is executed via plain
# ``python`` rather than ``uv run`` from inside the apps/api package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.base import get_engine
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.tenant import Tenant, TenantPlan, TenantStatus

CANARY_SLUG = os.environ.get("NEXUS_CANARY_SLUG", "auphere-canary")
CANARY_NAME = os.environ.get("NEXUS_CANARY_NAME", "Auphere Canary")
CANARY_TIMEZONE = os.environ.get("NEXUS_CANARY_TIMEZONE", "America/Santiago")
CANARY_MARKET = os.environ.get("NEXUS_CANARY_MARKET", "CL")

CANARY_PROMPT = """You are a smoke-test agent for the Auphere Nexus canary
tenant. You will never see real customer messages. If you do receive a
turn, respond briefly that the canary is healthy and end the turn.
""".strip()


async def _amain() -> int:
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == CANARY_SLUG))
        ).scalar_one_or_none()

        if existing:
            tenant_id = existing.id
            print(f"canary: tenant exists slug={CANARY_SLUG} id={tenant_id}")
        else:
            tenant = Tenant(
                id=uuid.uuid4(),
                name=CANARY_NAME,
                slug=CANARY_SLUG,
                plan=TenantPlan.INTERNAL,
                status=TenantStatus.ACTIVE,
                market=CANARY_MARKET,
                timezone=CANARY_TIMEZONE,
            )
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
            print(f"canary: created tenant slug={CANARY_SLUG} id={tenant_id}")

        config = (
            await session.execute(
                select(AgentConfig)
                .where(AgentConfig.tenant_id == tenant_id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            )
        ).scalar_one_or_none()

        if config:
            print(f"canary: agent_config v{config.version} already active")
        else:
            config = AgentConfig(
                tenant_id=tenant_id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=CANARY_PROMPT,
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=None,
                created_by="seed_canary_tenant.py",
            )
            session.add(config)
            print("canary: created agent_config v1 (active, no tools, no channels)")

        await session.commit()

    print(f"canary: ok slug={CANARY_SLUG} id={tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
