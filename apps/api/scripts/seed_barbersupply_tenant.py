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
import re
import sys
from pathlib import Path
from typing import Any

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

# Destructive WooCommerce tools. The sales agent is READ-ONLY on orders
# (audit F-2/F-3): it consults orders but never mutates them, and any change
# escalates to a human. We actively BLOCK these per-tenant so any
# previously-granted ``always`` override is revoked.
BLOCKED_TOOLS = (
    "woocommerce.create_order",
    "woocommerce.update_order_status",
    "woocommerce.update_order",
    "woocommerce.add_order_note",
)

# Policy fields that MUST carry real store data before the agent goes live
# (audit F-1). Each is provided via its env var; if absent, we fall back to
# the value already in the tenant's active config (audit F-5 — never clobber
# an operator-set real value with a template placeholder). Rendering fails
# fast if any of these remains an unfilled ``<<...>>`` sentinel.
_POLICY_ENV: dict[str, str] = {
    "policies.wholesale.contact_name": "NEXUS_BARBERSUPPLY_WHOLESALE_NAME",
    "policies.wholesale.contact_phone": "NEXUS_BARBERSUPPLY_WHOLESALE_PHONE",
    "policies.store.shipping_info": "NEXUS_BARBERSUPPLY_SHIPPING_INFO",
    "policies.store.returns_info": "NEXUS_BARBERSUPPLY_RETURNS_INFO",
}

# ``<<...>>`` is the seed template's "fill me in" sentinel. A live agent must
# never hand a customer one of these literally (e.g. ``<<+56900000000>>``).
_SENTINEL_RE = re.compile(r"<<[^>]*>>")


def _existing_policy_value(policies: dict[str, Any], dotted: str) -> str | None:
    """Walk ``policies`` by the ``policies.a.b`` dotted key; return the
    string value if present, else None."""
    node: Any = policies
    for part in dotted.removeprefix("policies.").split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def _find_sentinels(system_prompt: str, policies: dict[str, Any]) -> set[str]:
    """Collect every unfilled ``<<...>>`` sentinel in the rendered prompt
    and policy values."""
    found: set[str] = set(_SENTINEL_RE.findall(system_prompt))

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            found.update(_SENTINEL_RE.findall(node))
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(policies)
    return found


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``override`` onto ``base``. ``override`` wins for keys it
    defines; keys present only in ``base`` (operator-set extras) survive."""
    out: dict[str, Any] = {k: v for k, v in base.items()}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


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

        # Build render overrides: tenant identity + real policy values. Each
        # policy field comes from its env var, else from the value already in
        # the active config (F-5: never clobber an operator-set value with a
        # placeholder). Anything still missing stays as the template sentinel
        # and is caught by the validation below.
        existing_policies = dict(config.policies or {})
        overrides: dict[str, Any] = {
            "tenant.name": tenant_name,
            "tenant.timezone": tenant_tz,
        }
        for dotted, env_var in _POLICY_ENV.items():
            value = os.environ.get(env_var)
            if not value:
                prior = _existing_policy_value(existing_policies, dotted)
                if prior and not _SENTINEL_RE.search(prior):
                    value = prior
            if value:
                overrides[dotted] = value

        rendered = render_seed_template(template, placeholders=overrides)

        # F-1: refuse to publish with unfilled placeholders. A live agent
        # must never hand a customer a literal ``<<+56900000000>>``.
        unfilled = _find_sentinels(rendered.system_prompt, rendered.policies)
        if unfilled:
            print(
                "barbersupply: ABORT — unfilled placeholders still present: "
                + ", ".join(sorted(unfilled))
            )
            print("  fill them via env vars: " + ", ".join(sorted(_POLICY_ENV.values())))
            return 1

        prev_seed = config.seed_template_ref
        config.system_prompt_rendered = rendered.system_prompt
        config.tools = rendered.tools
        # F-5: merge policies (rendered wins for the keys it defines; any
        # operator-set keys not in the template survive) instead of a blind
        # replace that reverts operator edits on every re-run.
        config.policies = _deep_merge(existing_policies, rendered.policies)
        config.seed_template_ref = rendered.seed_template_ref
        print(
            f"barbersupply: re-rendered active agent_config v{config.version} "
            f"({prev_seed} -> {SEED}, {len(rendered.tools)} tools)"
        )

        # F-2 / F-3: the sales agent is read-only on orders. Actively BLOCK
        # every destructive woocommerce tool so any previously-granted
        # ``always`` override is revoked. Changes escalate to a human.
        tenant_row = await session.get(Tenant, tenant_id)
        assert tenant_row is not None  # already fetched above
        for tool in BLOCKED_TOOLS:
            await upsert_override(
                session,
                tenant=tenant_row,
                tool_name=tool,
                mode=ConnectorToolMode.BLOCKED,
                reason="Sales agent is read-only on orders; changes escalate to a human.",
                actor=ACTOR,
            )
            print(f"barbersupply: blocked destructive tool {tool} (mode=blocked)")
        # tenant_scoped_session commits on clean exit — no explicit commit.

    print(f"barbersupply: ok slug={TENANT_SLUG} id={tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
