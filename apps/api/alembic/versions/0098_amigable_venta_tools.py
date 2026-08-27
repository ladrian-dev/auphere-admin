"""seed tool_catalog with the inventory.* (Amigable Venta) tools + connector

Revision ID: 0098_amigable_venta_tools
Revises: 0097_workflow_packs
Create Date: 2026-08-24

Amigable Venta is an ``api_key`` connector (a single ``amk_…`` Bearer key,
no entity-id and no business_uuid — the key alone scopes the catalogue to
one business) that exposes a tenant's product catalogue and stock. The
connector row is also created by the seed runner from
``services/connectors/seeds/amigable_venta.yaml``; this migration adds the
``tool_catalog`` rows that depend on it and wires their ``connector_id``.

Tool surface (4 read-only, default_mode='always'):
    inventory.search_products
    inventory.get_product
    inventory.check_stock
    inventory.low_stock

Schemas come from ``alembic/data/0098_amigable_venta_tools.json``, generated
from the Pydantic input/output models of each tool class. When a schema
changes, write a follow-up migration with a new snapshot — never edit this.

Idempotent: ON CONFLICT (name) DO UPDATE so re-running keeps schemas fresh.
The runtime registers the tool classes via
``nexus_mcp.registry.build_default_registry``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0098_amigable_venta_tools"
down_revision: str | Sequence[str] | None = "0097_workflow_packs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0098_amigable_venta_tools.json",
)

_CAPABILITY_TAGS_BY_TOOL: dict[str, list[str]] = {
    "inventory.search_products": ["inventory", "catalog", "read"],
    "inventory.get_product": ["inventory", "catalog", "read"],
    "inventory.check_stock": ["inventory", "stock", "read"],
    "inventory.low_stock": ["inventory", "stock", "read"],
}


def upgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)

    bind = op.get_bind()

    # Upsert the connector row with the canonical seed values. The runtime
    # seed_runner re-applies the YAML on every deploy, so YAML edits
    # propagate without a follow-up migration. DO NOTHING to avoid
    # clobbering operator edits made through admin endpoints.
    bind.execute(
        text(
            """
            INSERT INTO connectors (
                slug, display_name, vendor, category, capabilities,
                auth_kind, mcp_server_ref, provider_meta,
                auto_enable_on_connect, auto_enable_destructive,
                consent_link_template_name, status
            ) VALUES (
                'amigable_venta', 'Amigable Venta', 'Amacrux Lab', 'catalog',
                CAST(:capabilities AS varchar[]),
                'api_key', 'internal:amigable_venta', CAST('{}' AS jsonb),
                true, false, NULL, 'available'
            )
            ON CONFLICT (slug) DO NOTHING
            """
        ),
        {"capabilities": ["read"]},
    )

    connector_row = bind.execute(
        text("SELECT id FROM connectors WHERE slug = 'amigable_venta'")
    ).first()
    if connector_row is None:
        raise RuntimeError("amigable_venta connector row missing after upsert")
    connector_id = connector_row[0]

    for tool_name, spec in catalog.items():
        side_effects = spec["side_effects"]
        read_only = bool(spec["read_only"])
        destructive = bool(spec["destructive"])
        capability_tags = _CAPABILITY_TAGS_BY_TOOL.get(tool_name, ["inventory", "read"])
        # Read-only catalogue lookups: always available once the connector
        # is connected (the api_key requires_consent gate still applies).
        default_mode = "blocked" if destructive else "always"

        bind.execute(
            text(
                """
                INSERT INTO tool_catalog (
                    name, description, mcp_server,
                    input_schema, output_schema,
                    side_effects, capability_tags, cost_estimate,
                    connector_id, read_only, destructive, requires_consent,
                    default_mode
                ) VALUES (
                    :name, :description, :mcp_server,
                    CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                    CAST(:side_effects AS varchar[]),
                    CAST(:capability_tags AS varchar[]),
                    CAST('{}' AS jsonb),
                    :connector_id, :read_only, :destructive, :requires_consent,
                    :default_mode
                )
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    input_schema = EXCLUDED.input_schema,
                    output_schema = EXCLUDED.output_schema,
                    side_effects = EXCLUDED.side_effects,
                    capability_tags = EXCLUDED.capability_tags,
                    connector_id = EXCLUDED.connector_id,
                    read_only = EXCLUDED.read_only,
                    destructive = EXCLUDED.destructive,
                    requires_consent = EXCLUDED.requires_consent,
                    default_mode = EXCLUDED.default_mode
                """
            ),
            {
                "name": tool_name,
                "description": spec["description"],
                "mcp_server": "amigable-venta-server",
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
                "side_effects": list(side_effects),
                "capability_tags": list(capability_tags),
                "connector_id": connector_id,
                "read_only": read_only,
                "destructive": destructive,
                # api_key connectors require operator-configured credentials
                # before any tool can be invoked.
                "requires_consent": True,
                "default_mode": default_mode,
            },
        )


def downgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog = json.load(fh)
    names = list(catalog.keys())
    op.execute(
        "DELETE FROM tool_catalog WHERE name IN (" + ", ".join(f"'{n}'" for n in names) + ")"
    )
