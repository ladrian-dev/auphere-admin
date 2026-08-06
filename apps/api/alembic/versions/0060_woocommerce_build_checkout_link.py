"""seed tool_catalog with woocommerce.build_checkout_link (read-only)

Revision ID: 0060_woo_checkout_link
Revises: 0059_tiktok_channel
Create Date: 2026-08-06

``woocommerce.build_checkout_link`` is registered in the MCP runtime
(``WOOCOMMERCE_TOOLS``) and is in the ``woocommerce_sales_v1`` agent
whitelist, so it already runs in production. But it was never added to
``tool_catalog`` — migration 0024 seeded the original 12 woocommerce
tools and this one landed later. The gap means:

- the operator panel / agent editor cannot see or gate it, and
- any code path that rebuilds a whitelist from the catalog
  (``auto_enable_connector_tools``) would silently drop it, leaving the
  sales agent unable to close a single sale.

This migration closes the gap: it adds the catalog row as a READ-ONLY
tool (it only builds a URL from the tenant's store — no mutation, no API
call), ``default_mode='always'`` so it is available wherever the
connector is connected, matching how the tool actually behaves.

Idempotent: ON CONFLICT (name) DO UPDATE.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0060_woo_checkout_link"
down_revision: str | Sequence[str] | None = "0059_tiktok_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TOOL_NAME = "woocommerce.build_checkout_link"

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "minimum": 1},
                    "quantity": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10000,
                        "default": 1,
                    },
                },
                "required": ["product_id"],
            },
        }
    },
    "required": ["items"],
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"url": {"type": "string"}},
    "required": ["url"],
}


def upgrade() -> None:
    bind = op.get_bind()

    connector_row = bind.execute(
        text("SELECT id FROM connectors WHERE slug = 'woocommerce'")
    ).first()
    # The woocommerce connector is seeded by migration 0024; if it is
    # missing something is very wrong upstream — fail loud.
    if connector_row is None:
        raise RuntimeError("woocommerce connector row missing — run 0024 first")
    connector_id = connector_row[0]

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
            "name": TOOL_NAME,
            "description": (
                "Build the checkout link: a URL that pre-fills the cart with the "
                "given products and opens the store's checkout page, where the "
                "customer picks delivery + payment and completes the order. "
                "Read-only: builds a URL, no mutation."
            ),
            "mcp_server": "woocommerce-server",
            "input_schema": json.dumps(INPUT_SCHEMA),
            "output_schema": json.dumps(OUTPUT_SCHEMA),
            "side_effects": [],
            "capability_tags": ["ecommerce", "checkout", "read"],
            "connector_id": connector_id,
            "read_only": True,
            "destructive": False,
            "requires_consent": True,
            "default_mode": "always",
        },
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM tool_catalog WHERE name = '{TOOL_NAME}'")
