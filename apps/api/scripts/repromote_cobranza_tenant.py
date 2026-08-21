"""Re-render + promote a cobranza tenant's agent_config to the current
``cobranza_v1`` template — the PROD-safe way (new version, audited, roll
back-able), NOT the in-place re-render the dev seed does.

Why this exists: tenants seeded before ``billing.find_client`` /
``billing.add_charge`` (and ``billing.send_reminders``) were added to the
vertical stayed on an older config that lacks those tools. This stages a
fresh version from the current template and promotes it.

Data safety: the tenant's REAL ``admin_access.admin_phones`` are read from
the CURRENT active config and fed back in as placeholders, so the whitelist
is preserved verbatim. The script ASSERTS it survived before promoting — it
would rather abort than silently drop the admins the gate depends on.

It deliberately does NOT carry ``policies.payment.*`` forward. ADR-035
removed payment data from the vertical: it was rendered into the shared
seed's prompt, so the placeholder examples reached production as if they
were the client's real bank details, and every future Amigable Cobro client
would have inherited the same ones. Re-promoting is how a tenant sheds them.

``policies.reminders`` from the current config IS carried forward when
present, so re-promoting never silently re-enables (or disables) a tenant's
daily sweep.

Usage (dry-run by default — prints the diff, writes NOTHING):

    NEXUS_DATABASE_URL=postgresql+asyncpg://... \\
      uv run python apps/api/scripts/repromote_cobranza_tenant.py mouna

Add ``--apply`` to actually stage + promote:

    NEXUS_DATABASE_URL=... uv run python \\
      apps/api/scripts/repromote_cobranza_tenant.py mouna --apply
"""

from __future__ import annotations

import asyncio
import os
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
from nexus_api.db.models.tenant import Tenant
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.templating.seed_templates import (
    load_seed_template,
    render_seed_template,
)

SEED = "cobranza_v1"


def _placeholders_from_current(tenant: Tenant, policies: dict[str, Any]) -> dict[str, Any]:
    """Only the data the tenant genuinely owns. ``policies.payment.*`` is NOT
    among it any more — see the module docstring."""
    access = (policies or {}).get("admin_access") or {}
    ph: dict[str, Any] = {
        "tenant.name": tenant.name,
        "tenant.timezone": tenant.timezone,
        "policies.admin_access.admin_phones": list(access.get("admin_phones") or []),
    }
    reminders = (policies or {}).get("reminders")
    if isinstance(reminders, dict):
        for field, val in reminders.items():
            ph[f"policies.reminders.{field}"] = val
    return ph


async def _amain(slug: str, apply: bool) -> int:
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # 1) Read tenant + current active config (superuser session bypasses RLS).
    async with Session() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"ERROR: no tenant with slug={slug!r}")
            return 1
        current = (
            await session.execute(
                select(AgentConfig)
                .where(AgentConfig.tenant_id == tenant.id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            )
        ).scalar_one_or_none()
        if current is None:
            print(f"ERROR: tenant {slug!r} has no ACTIVE agent_config")
            return 1
        cur_tools = list(current.tools or [])
        cur_policies = dict(current.policies or {})
        cur_channels = list(current.channels or [])
        cur_kg = current.kg_schema_id
        cur_version = current.version

    cur_admins = list((cur_policies.get("admin_access") or {}).get("admin_phones") or [])

    # 2) Re-render the current template with the tenant's real data preserved.
    template = load_seed_template(SEED)
    rendered = render_seed_template(
        template, placeholders=_placeholders_from_current(tenant, cur_policies)
    )
    new_admins = list((rendered.policies.get("admin_access") or {}).get("admin_phones") or [])

    # 3) SAFETY: never drop the admin whitelist the gate depends on.
    if sorted(new_admins) != sorted(cur_admins):
        print("ABORT: admin_phones would change — refusing to promote.")
        print(f"  actual : {cur_admins}")
        print(f"  render : {new_admins}")
        return 2

    added = [t for t in rendered.tools if t not in cur_tools]
    removed = [t for t in cur_tools if t not in rendered.tools]

    print(f"tenant   : {slug} (id={tenant.id})")
    print(f"config   : active v{cur_version} → would stage v{cur_version + 1}")
    print(f"admins   : {len(cur_admins)} preserved {cur_admins}")
    print(f"tools +  : {added or '—'}")
    print(f"tools -  : {removed or '—'}")

    if not apply:
        print("\nDRY-RUN (nada escrito). Re-ejecuta con --apply para promover.")
        return 0

    # 4) Stage a new version from the rendered template + promote.
    async with Session() as session, tenant_scoped_session(session, tenant.id):
        svc = AgentConfigService(session)
        staged = await svc.stage_new_version(
            actor="repromote_cobranza_tenant.py",
            system_prompt_rendered=rendered.system_prompt,
            channels=cur_channels,
            tools=rendered.tools,
            policies=rendered.policies,
            seed_template_ref=rendered.seed_template_ref,
            kg_schema_id=cur_kg,
        )
        promoted = await svc.promote(staged.version, actor="repromote_cobranza_tenant.py")

    print(f"\nOK: {slug} promovido a agent_config v{promoted.version} "
          f"({len(rendered.tools)} tools). Publica el refresh de cache si aplica.")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    slug = (args[0] if args else None) or os.environ.get("NEXUS_COBRANZA_SLUG") or "mouna"
    apply_flag = "--apply" in sys.argv[1:]
    raise SystemExit(asyncio.run(_amain(slug, apply_flag)))
