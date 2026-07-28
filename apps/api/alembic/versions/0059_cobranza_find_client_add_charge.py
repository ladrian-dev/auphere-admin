"""Cobranza catalog gap: billing.find_client + billing.add_charge

Revision ID: 0059_cobranza_find_client
Revises: 0058_cobranza_send_reminders
Create Date: 2026-07-26

``cobranza_v1`` lists ``billing.find_client`` and ``billing.add_charge`` in
its required tools, but NO migration ever registered them in
``tool_catalog`` (0045/0046 shipped the other 9). Because
``AgentConfigService._validate_tools`` validates the agent_config whitelist
against ``tool_catalog``, provisioning/promoting a cobranza agent that
includes these two would 422, so tenants stayed on an older config WITHOUT
them — leaving the agent unable to look up an account by name (find_client)
or add a charge (add_charge). This backfills both.

Idempotent: ON CONFLICT (name) DO UPDATE keeps the schemas fresh.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0059_cobranza_find_client"
down_revision: str | Sequence[str] | None = "0058_cobranza_send_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0059_cobranza_find_client_add_charge.json",
)

_CAPABILITY_TAGS_BY_TOOL: dict[str, list[str]] = {
    "billing.find_client": ["billing", "collections", "read"],
    "billing.add_charge": ["billing", "collections", "write"],
}
_NEW_TOOLS = ("billing.find_client", "billing.add_charge")


def upgrade() -> None:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)

    bind = op.get_bind()
    connector_row = bind.execute(
        text("SELECT id FROM connectors WHERE slug = 'amigable_cobro'")
    ).first()
    if connector_row is None:
        raise RuntimeError("amigable_cobro connector row missing (0045 should have created it)")
    connector_id = connector_row[0]

    for tool_name, spec in catalog.items():
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
                "mcp_server": "amigable-cobro-server",
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
                "side_effects": list(spec["side_effects"]),
                "capability_tags": _CAPABILITY_TAGS_BY_TOOL.get(tool_name, ["billing"]),
                "connector_id": connector_id,
                "read_only": bool(spec["read_only"]),
                "destructive": bool(spec["destructive"]),
                "requires_consent": True,
                "default_mode": "always",
            },
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM tool_catalog WHERE name IN ("
        + ", ".join(f"'{n}'" for n in _NEW_TOOLS)
        + ")"
    )
