"""Cobranza on-demand reminder tool (billing.send_reminders)

Revision ID: 0058_cobranza_send_reminders
Revises: 0057_billing_effective_from
Create Date: 2026-07-26

Due-date reminders are no longer sent by an autonomous cron. They now go out
only when a business admin asks the agent for them, via the new
``billing.send_reminders`` tool (confirm=true, after explicit confirmation).
This migration upserts that tool into ``tool_catalog`` so it can be
whitelisted on the cobranza_v1 agent config.

Access control layers (same as the other billing.* writes):
  1. Dispatcher admin gate — only ``policies.admin_access.admin_phones``
     senders reach the agent at all.
  2. System-prompt + the tool's own ``confirm`` flag — the agent must get an
     explicit admin confirmation before calling with confirm=true.
  3. ``side_effects=['mutates_db']`` — QA Playground (dry_run) intercepts it.

Idempotent: ON CONFLICT (name) DO UPDATE keeps the schema fresh.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0058_cobranza_send_reminders"
down_revision: str | Sequence[str] | None = "0057_billing_effective_from"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0058_cobranza_send_reminders.json",
)

_TOOL_NAME = "billing.send_reminders"
_CAPABILITY_TAGS = ["billing", "collections", "notify"]


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
                "capability_tags": _CAPABILITY_TAGS,
                "connector_id": connector_id,
                "read_only": bool(spec["read_only"]),
                "destructive": bool(spec["destructive"]),
                "requires_consent": True,
                # Admin gate at the dispatcher is the WHO control; gating mode
                # stays 'always' so the tool actually runs for the (admin-only)
                # tenant that whitelists it.
                "default_mode": "always",
            },
        )


def downgrade() -> None:
    op.execute(f"DELETE FROM tool_catalog WHERE name = '{_TOOL_NAME}'")
