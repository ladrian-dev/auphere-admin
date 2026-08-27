"""Seed the Demo Farmacia Amigable tenant (vertical ``inventario_v1``).

Creates, in one run and idempotently:
  - Tenant ``demo-farmacia-amigable`` (plan PRO, market VE, America/Caracas).
  - agent_config v1 ACTIVE rendered from the ``inventario_v1`` seed, with the
    four read-only ``inventory.*`` tools and the admin whitelist.
  - The ``amigable_venta`` connector (api_key), with the API key stored in
    ``tenant_credentials`` as an encrypted payload.

Re-running picks up the existing tenant by ``slug``, re-renders the active
config in place (so iterating on the template is one command) and re-bootstraps
the connector.

The agent is ``admin_only``: it only answers the phones in
``NEXUS_FARMACIA_ADMIN_PHONES``. The agent's OWN line (the WABA number) must
NOT be listed there — a number cannot message itself on WhatsApp.

Usage:

    NEXUS_DATABASE_URL=postgresql+asyncpg://... \\
    NEXUS_FERNET_KEY=... \\
    NEXUS_AMIGABLE_VENTA_TOKEN=amk_... \\
      python apps/api/scripts/seed_demo_farmacia_tenant.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Make ``nexus_api`` importable when run via plain ``python``.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_engine
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.tenant import Tenant, TenantPlan, TenantStatus
from nexus_api.services.connectors.service import bootstrap_api_key
from nexus_api.services.templating.seed_templates import (
    load_seed_template,
    render_seed_template,
)

SLUG = os.environ.get("NEXUS_FARMACIA_SLUG", "demo-farmacia-amigable")
NAME = os.environ.get("NEXUS_FARMACIA_NAME", "Demo Farmacia Amigable")
TIMEZONE = os.environ.get("NEXUS_FARMACIA_TIMEZONE", "America/Caracas")
MARKET = os.environ.get("NEXUS_FARMACIA_MARKET", "VE")


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return [p.strip() for p in raw.split(",") if p.strip()]


# Teléfonos del PERSONAL autorizado (E.164) — los únicos a los que el agente
# responde (gate en el dispatcher: policies.admin_access). Cualquier otro
# remitente queda persistido para auditoría pero SIN respuesta.
#
# NOTA: +34672138367 es la LÍNEA del agente (la WABA), por eso NO está aquí:
# un número no puede escribirse a sí mismo por WhatsApp. El personal le
# escribe a esa línea desde estos teléfonos.
ADMIN_PHONES: list[str] = _env_list(
    "NEXUS_FARMACIA_ADMIN_PHONES",
    ["+34610777570", "+34632719028"],
)

AGENT_LINE = "+34672138367"


async def _amain() -> int:
    token = os.environ.get("NEXUS_AMIGABLE_VENTA_TOKEN")
    if AGENT_LINE in ADMIN_PHONES:
        print(f"ERROR: {AGENT_LINE} es la LÍNEA del agente; no puede estar en admin_phones")
        return 1

    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    template = load_seed_template("inventario_v1")
    rendered = render_seed_template(
        template,
        placeholders={
            "tenant.name": NAME,
            "tenant.timezone": TIMEZONE,
            "policies.admin_access.admin_phones": ADMIN_PHONES,
        },
    )

    async with Session() as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == SLUG))
        ).scalar_one_or_none()

        if existing:
            tenant_id = existing.id
            print(f"farmacia: tenant exists slug={SLUG} id={tenant_id}")
        else:
            tenant = Tenant(
                id=uuid.uuid4(),
                name=NAME,
                slug=SLUG,
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
                market=MARKET,
                timezone=TIMEZONE,
            )
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
            print(f"farmacia: created tenant slug={SLUG} id={tenant_id}")

        config = (
            await session.execute(
                select(AgentConfig)
                .where(AgentConfig.tenant_id == tenant_id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            )
        ).scalar_one_or_none()

        if config:
            # Local dev: re-render the active config in place so iterating on
            # the inventario_v1 template is one command. PROD stages a new
            # version instead (AgentConfigService.stage_new_version + promote).
            config.system_prompt_rendered = rendered.system_prompt
            config.tools = rendered.tools
            config.policies = rendered.policies
            config.seed_template_ref = rendered.seed_template_ref
            print(f"farmacia: re-rendered agent_config v{config.version} from seed (local dev)")
        else:
            config = AgentConfig(
                tenant_id=tenant_id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=rendered.system_prompt,
                channels=[],  # WhatsApp se cablea cuando la WABA esté conectada
                tools=rendered.tools,
                policies=rendered.policies,
                seed_template_ref=rendered.seed_template_ref,
                created_by="seed_demo_farmacia_tenant.py",
            )
            session.add(config)
            print(
                f"farmacia: created agent_config v1 (active, seed={rendered.seed_template_ref}, "
                f"{len(rendered.tools)} tools)"
            )

        await session.commit()

    # Connector en transacción propia y con scope de tenant (RLS).
    if token:
        async with Session() as session, tenant_scoped_session(session, tenant_id):
            tenant = (
                await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            ).scalar_one()
            tc = await bootstrap_api_key(
                session,
                tenant=tenant,
                connector_slug="amigable_venta",
                secret_payload={"token": token},
                endpoint_meta={},
                actor="seed_demo_farmacia_tenant.py",
            )
            tc_id, tc_status = tc.id, tc.status
        print(f"farmacia: amigable_venta connected — tenant_connector={tc_id} status={tc_status}")
    else:
        print(
            "farmacia: sin NEXUS_AMIGABLE_VENTA_TOKEN — el agente servirá el "
            "catálogo importado (load_local_catalog.py). Conecta el connector "
            "cuando el API tenga datos y tomará la precedencia solo."
        )
    print(f"farmacia: admins={ADMIN_PHONES} · línea del agente={AGENT_LINE} (pendiente de cablear)")
    print(f"farmacia: ok slug={SLUG} id={tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
