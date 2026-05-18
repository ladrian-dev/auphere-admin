"""seed tool_catalog with the 12 woocommerce.* tools and link them to the connector

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-18

WooCommerce is the first ``api_key`` connector to land in the tool
catalog. The connector row itself is created by the seed runner from
``services/connectors/seeds/woocommerce.yaml`` — this migration adds
the 12 ``tool_catalog`` rows that depend on it and wires their
``connector_id`` FK.

Tool surface (8 read-only + 4 destructive):

- read-only (default_mode='always'):
    woocommerce.list_products / get_product / list_product_variations
    woocommerce.list_categories
    woocommerce.list_orders / get_order
    woocommerce.list_customers / get_customer

- destructive (default_mode='blocked' — operator opts in per tenant):
    woocommerce.create_order
    woocommerce.update_order
    woocommerce.update_order_status
    woocommerce.add_order_note

Schemas come from ``alembic/data/0024_woocommerce_tools.json``, generated
from the Pydantic ``input_model`` / ``output_model`` of each tool class.
When a schema changes, write a follow-up migration with a new snapshot —
never edit this one.

Idempotent: ON CONFLICT (name) DO UPDATE so re-running keeps schemas
fresh without duplicating rows.

The runtime registers the tool classes via
``nexus_mcp.registry.build_default_registry``; this migration only adds
the catalog rows so the operator panel and the agent_config whitelist
can reference them.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0024_woocommerce_tools.json",
)


# Capability tags surface in the operator-panel filter. Keep these
# loose; the gating contract is enforced by ``destructive`` + ``default_mode``.
_CAPABILITY_TAGS_BY_TOOL: dict[str, list[str]] = {
    "woocommerce.list_products": ["ecommerce", "products", "read"],
    "woocommerce.get_product": ["ecommerce", "products", "read"],
    "woocommerce.list_product_variations": ["ecommerce", "products", "read"],
    "woocommerce.list_categories": ["ecommerce", "catalog", "read"],
    "woocommerce.list_orders": ["ecommerce", "orders", "read"],
    "woocommerce.get_order": ["ecommerce", "orders", "read"],
    "woocommerce.list_customers": ["ecommerce", "customers", "read"],
    "woocommerce.get_customer": ["ecommerce", "customers", "read"],
    "woocommerce.create_order": ["ecommerce", "orders", "write"],
    "woocommerce.update_order": ["ecommerce", "orders", "write"],
    "woocommerce.update_order_status": ["ecommerce", "orders", "write"],
    "woocommerce.add_order_note": ["ecommerce", "orders", "communication"],
}


def upgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)

    bind = op.get_bind()

    # Self-contained: upsert the connector row with the canonical
    # values from the seed YAML at the time this migration was
    # authored. The runtime seed_runner re-applies the YAML on every
    # deploy, so YAML edits propagate without a follow-up migration.
    # Using ON CONFLICT DO NOTHING for the connector row (don't
    # clobber operator edits that may have been made through admin
    # endpoints).
    bind.execute(
        text(
            """
            INSERT INTO connectors (
                slug, display_name, vendor, category, capabilities,
                auth_kind, mcp_server_ref, provider_meta,
                auto_enable_on_connect, auto_enable_destructive,
                consent_link_template_name, status
            ) VALUES (
                'woocommerce', 'WooCommerce', 'Automattic', 'ecommerce',
                CAST(:capabilities AS varchar[]),
                'api_key', 'internal:woocommerce', CAST('{}' AS jsonb),
                true, false, NULL, 'beta'
            )
            ON CONFLICT (slug) DO NOTHING
            """
        ),
        {"capabilities": ["read", "write"]},
    )

    connector_row = bind.execute(
        text("SELECT id FROM connectors WHERE slug = 'woocommerce'")
    ).first()
    # The upsert above guarantees the row exists; this is a defensive
    # check so the failure mode is loud if a future migration drops
    # the row out from under us.
    if connector_row is None:
        raise RuntimeError("woocommerce connector row missing after upsert")
    connector_id = connector_row[0]

    bind = op.get_bind()
    for tool_name, spec in catalog.items():
        side_effects = spec["side_effects"]
        read_only = bool(spec["read_only"])
        destructive = bool(spec["destructive"])
        capability_tags = _CAPABILITY_TAGS_BY_TOOL.get(tool_name, ["ecommerce"])
        # Destructive tools start blocked; the operator promotes them
        # per tenant via tenant_connector_tool_overrides once they
        # trust the agent to mutate the store.
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
                "mcp_server": "woocommerce-server",
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
                "side_effects": list(side_effects),
                "capability_tags": list(capability_tags),
                "connector_id": connector_id,
                "read_only": read_only,
                "destructive": destructive,
                # api_key connectors require the credentials to be set
                # up by the operator before any tool can be invoked.
                "requires_consent": True,
                "default_mode": default_mode,
            },
        )


def downgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog = json.load(fh)
    names = list(catalog.keys())
    op.execute(
        "DELETE FROM tool_catalog WHERE name IN ("
        + ", ".join(f"'{n}'" for n in names)
        + ")"
    )
