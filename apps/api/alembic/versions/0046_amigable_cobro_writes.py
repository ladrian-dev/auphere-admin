"""Amigable Cobro write tools (billing.*) + refresh read schemas

Revision ID: 0046_amigable_cobro_writes
Revises: 0045_amigable_cobro_tools
Create Date: 2026-06-30

cobranza_v1 v2.0.0 turns the collections agent into the ADMIN's assistant
(ADR pending; see Auphere/nexus/verticals/cobranza_v1.md). The admin can now
mutate Amigable Cobro from the chat: register payments, flip status, apply
discounts, create/update accounts. This migration upserts the full billing.*
tool surface (4 reads + 5 writes) from the 0046 snapshot.

Access control layers for the writes:
  1. Dispatcher admin gate — only ``policies.admin_access.admin_phones``
     senders ever reach the agent (pipeline.skipped.not_admin otherwise).
  2. System-prompt confirmation protocol — the agent must echo the exact
     change and receive an explicit "sí" before calling a write tool.
  3. ``side_effects=("mutates_db",)`` — the QA Playground (dry_run)
     intercepts writes so operators preview without touching real data.
Because layer 1 already restricts WHO can talk to the agent, the writes
ship ``default_mode='always'`` (a 'blocked' default would require per-tenant
overrides and break the feature for its only consumer).

Idempotent: ON CONFLICT (name) DO UPDATE keeps schemas fresh.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "0046_amigable_cobro_writes"
down_revision: str | Sequence[str] | None = "0045_amigable_cobro_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "0046_amigable_cobro_tools.json",
)

_CAPABILITY_TAGS_BY_TOOL: dict[str, list[str]] = {
    "billing.get_my_debt": ["billing", "collections", "read"],
    "billing.get_account": ["billing", "collections", "read"],
    "billing.get_debtor_by_phone": ["billing", "collections", "read"],
    "billing.list_overdue": ["billing", "collections", "read"],
    "billing.register_payment": ["billing", "collections", "write"],
    "billing.update_status": ["billing", "collections", "write"],
    "billing.apply_discount": ["billing", "collections", "write"],
    "billing.create_account": ["billing", "collections", "write"],
    "billing.update_account": ["billing", "collections", "write"],
}

# Names introduced by THIS migration (0045 owns the other three).
_NEW_IN_0046 = (
    "billing.get_account",
    "billing.register_payment",
    "billing.update_status",
    "billing.apply_discount",
    "billing.create_account",
    "billing.update_account",
)


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
        destructive = bool(spec["destructive"])
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
                "destructive": destructive,
                "requires_consent": True,
                # See docstring: admin gate at the dispatcher is the WHO
                # control; gating mode stays 'always' so the writes actually
                # run for the (admin-only) tenant that whitelists them.
                "default_mode": "always",
            },
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM tool_catalog WHERE name IN (" + ", ".join(f"'{n}'" for n in _NEW_IN_0046) + ")"
    )
