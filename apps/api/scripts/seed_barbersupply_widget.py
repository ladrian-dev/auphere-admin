"""Enable the public web chat widget for the Barber Supply Chile tenant.

Creates (or updates) the ``tenant_widget_config`` row for the
``barbersupply`` tenant so the native chat bubble can be embedded on
barbersupply.cl. The agent behind it is the already-active
``woocommerce_sales_v1`` sales agent — this script only opens the WEB
channel front-door; it does NOT touch the agent config or the connector.

``tenant_widget_configs`` is a PLATFORM table (no RLS), so this runs
outside any tenant scope.

Idempotent: re-running preserves the existing ``public_key`` (so a widget
already deployed on the site keeps working) and refreshes the origins /
greeting / appearance / enabled flag.

Usage:

    NEXUS_DATABASE_URL=postgresql+asyncpg://... \\
      uv run python apps/api/scripts/seed_barbersupply_widget.py
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path

# Make ``nexus_api`` importable when run via plain ``python``.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.base import get_engine
from nexus_api.db.models.tenant import Tenant
from nexus_api.db.models.widget import TenantWidgetConfig

TENANT_SLUG = os.environ.get("NEXUS_BARBERSUPPLY_SLUG", "barbersupply")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "NEXUS_BARBERSUPPLY_WIDGET_ORIGINS", "https://barbersupply.cl,https://www.barbersupply.cl"
    ).split(",")
    if o.strip()
]
GREETING = "¡Hola! 👋 Soy tu asesor de Barber Supply. ¿Qué estás buscando?"
APPEARANCE = {"title": "Barber Supply", "accent_color": "#111827"}


async def _amain() -> int:
    engine = get_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"widget: tenant slug={TENANT_SLUG!r} NOT FOUND — aborting")
            return 1

        config = (
            await session.execute(
                select(TenantWidgetConfig).where(TenantWidgetConfig.tenant_id == tenant.id)
            )
        ).scalar_one_or_none()

        if config is None:
            public_key = "wgt_pub_" + secrets.token_hex(16)
            config = TenantWidgetConfig(
                tenant_id=tenant.id,
                public_key=public_key,
                allowed_origins=ALLOWED_ORIGINS,
                greeting=GREETING,
                appearance=APPEARANCE,
                enabled=True,
            )
            session.add(config)
            action = "created"
        else:
            # Preserve the existing public_key (already embedded on the site).
            config.allowed_origins = ALLOWED_ORIGINS
            config.greeting = GREETING
            config.appearance = APPEARANCE
            config.enabled = True
            action = "updated"

        await session.commit()
        public_key = config.public_key

    print(f"widget: {action} config for {TENANT_SLUG} (tenant_id={tenant.id})")
    print(f"widget: public_key = {public_key}")
    print(f"widget: allowed_origins = {ALLOWED_ORIGINS}")
    print("\nSnippet para el footer del tema WordPress:\n")
    print(
        '  <script src="https://api.auphere.com/widget.js"\n'
        f'          data-public-key="{public_key}" async></script>\n'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
