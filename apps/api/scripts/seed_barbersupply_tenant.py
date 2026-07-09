"""Apply the woocommerce_sales_v1 sales agent to the Barber Supply Chile tenant.

Barber Supply Chile is the first client of the ``woocommerce_sales_v1``
vertical (WooCommerce store sales agent). Ficha:
Auphere/nexus/clients/barbersupply.md.

The tenant ``barbersupply`` already exists in prod with the WooCommerce
connector wired to https://barbersupply.cl. This script does NOT create the
tenant or the connector — it only:

  1. Renders ``woocommerce_sales_v1`` with the store's name / timezone.
  2. Re-renders the tenant's ACTIVE ``agent_config`` in place (system prompt +
     tools + policies + seed_template_ref) — moving it from the generic
     assistant to the WooCommerce sales agent.
  3. Enables the destructive ``woocommerce.*`` write tools (create_order,
     update_order_status, update_order, add_order_note) via
     connector-tool-overrides (mode=always), so the agent can take orders.
     The order-taking confirmation protocol lives in the system prompt.

Idempotent: re-running re-renders the active config and re-asserts the
overrides. Fails fast if the tenant or an ACTIVE config is missing.

Usage:

    NEXUS_DATABASE_URL=postgresql+asyncpg://... \\
      uv run python apps/api/scripts/seed_barbersupply_tenant.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Make ``nexus_api`` importable when run via plain ``python``.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_engine
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.connector import ConnectorToolMode
from nexus_api.db.models.tenant import Tenant
from nexus_api.services.connectors.service import upsert_override
from nexus_api.services.templating.seed_templates import (
    load_seed_template,
    render_seed_template,
)

TENANT_SLUG = os.environ.get("NEXUS_BARBERSUPPLY_SLUG", "barbersupply")
SEED = "woocommerce_sales_v1"
ACTOR = "seed_barbersupply_tenant.py"

# Destructive WooCommerce tools the sales agent needs to take orders. They
# start ``default_mode='blocked'`` in the catalog; enabling them per-tenant
# lets the agent call them. Confirmation-before-write is enforced by prompt.
WRITE_TOOLS = (
    "woocommerce.create_order",
    "woocommerce.update_order_status",
    "woocommerce.update_order",
    "woocommerce.add_order_note",
)


async def _amain() -> int:
    engine = get_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Tenant lookup — the tenants table is global (RLS on tenants is a no-op),
    # so this runs outside a tenant-scoped session.
    async with session_factory() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"barbersupply: tenant slug={TENANT_SLUG!r} NOT FOUND — aborting")
            return 1
        tenant_id = tenant.id
        tenant_name = tenant.name
        tenant_tz = tenant.timezone

    template = load_seed_template(SEED)
    rendered = render_seed_template(
        template,
        placeholders={"tenant.name": tenant_name, "tenant.timezone": tenant_tz},
    )

    async with session_factory() as session, tenant_scoped_session(session, tenant_id):
        config = (
            await session.execute(
                select(AgentConfig)
                .where(AgentConfig.tenant_id == tenant_id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                .order_by(AgentConfig.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if config is None:
            print(f"barbersupply: no ACTIVE agent_config for {TENANT_SLUG!r} — aborting")
            return 1

        prev_seed = config.seed_template_ref
        config.system_prompt_rendered = rendered.system_prompt
        config.tools = rendered.tools
        config.policies = rendered.policies
        config.seed_template_ref = rendered.seed_template_ref
        print(
            f"barbersupply: re-rendered active agent_config v{config.version} "
            f"({prev_seed} -> {SEED}, {len(rendered.tools)} tools)"
        )

        tenant_row = await session.get(Tenant, tenant_id)
        assert tenant_row is not None  # already fetched above
        for tool in WRITE_TOOLS:
            await upsert_override(
                session,
                tenant=tenant_row,
                tool_name=tool,
                mode=ConnectorToolMode.ALWAYS,
                reason="Sales agent takes orders (confirmation enforced by prompt).",
                actor=ACTOR,
            )
            print(f"barbersupply: enabled write tool {tool} (mode=always)")
        # tenant_scoped_session commits on clean exit — no explicit commit.

    print(f"barbersupply: ok slug={TENANT_SLUG} id={tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
