"""connectors + tenant_connectors + tool_catalog annotations — block L

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-12

Block L unifies "integrations" into a first-class Connectors module.
Decision: ADR-011. Spec: architecture/connectors.md. Tests:
architecture/connectors-testing.md.

Three new tables:

1. ``connectors`` (global catalog, no RLS) — one row per integration
   the platform supports (whatsapp_ycloud, agendapro, google_calendar,
   calendly, notion). Seeded from
   apps/api/.../services/connectors/seeds/*.yaml.

2. ``tenant_connectors`` (RLS+FORCE) — one row per (tenant, connector)
   install. Holds status, credentials_ref (jsonb pointing to either a
   composio connection_id, a tenant_credentials row, or a channels
   row), scopes, timestamps.

3. ``tenant_connector_tool_overrides`` (RLS+FORCE) — optional per-tenant
   per-tool gating override. mode in {always, blocked, needs_approval}.
   Phase 1 only uses always/blocked at runtime; needs_approval is
   schema-ready for Phase 4+ operator-in-loop without future migration.

Plus ALTERs to tool_catalog:
- ``connector_id`` FK (nullable; internal tools like notification.* and
  escalate.* have no connector).
- ``read_only`` bool — MCP-standard readOnlyHint mapping.
- ``destructive`` bool — MCP-standard destructiveHint mapping.
- ``requires_consent`` bool — true if the tool only operates with a
  consent-backed credential (excludes internal/notification/escalate).
- ``default_mode`` text — "always" | "blocked" (Phase 1) | "needs_approval"
  (Phase 4+). Default "always" for read_only=true; "always" for
  destructive=false; "blocked" for destructive=true unless the connector
  flips auto_enable_destructive=true.

Backfill of existing data lives in
apps/api/scripts/migrate_to_connectors.py (idempotent, runs separately).

Downgrade drops the three new tables; the tool_catalog ALTERs remain
(additive, do not break the pre-L code path).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RLS_POLICY_SQL = """
CREATE POLICY {table}_tenant_isolation ON {table}
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
"""


def upgrade() -> None:
    # ── connectors (global catalog) ─────────────────────────────────────────
    op.create_table(
        "connectors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("vendor", sa.String(120), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column(
            "capabilities",
            postgresql.ARRAY(sa.String(40)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("auth_kind", sa.String(40), nullable=False),
        sa.Column("mcp_server_ref", sa.String(120), nullable=False),
        sa.Column(
            "provider_meta",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "auto_enable_on_connect",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "auto_enable_destructive",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("consent_link_template_name", sa.String(120), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="available",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_connectors_slug"),
        sa.CheckConstraint(
            "auth_kind IN ('oauth_composio', 'browser_credentials', "
            "'webhook_manual', 'api_key')",
            name="ck_connectors_auth_kind",
        ),
        sa.CheckConstraint(
            "status IN ('available', 'beta', 'deprecated')",
            name="ck_connectors_status",
        ),
    )
    op.create_index(
        "ix_connectors_category_available",
        "connectors",
        ["category"],
        postgresql_where=sa.text("status = 'available'"),
    )

    # ── tenant_connectors (per-tenant install) ──────────────────────────────
    op.create_table(
        "tenant_connectors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "credentials_ref",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "scopes_granted",
            postgresql.ARRAY(sa.String(120)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "config",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_token", sa.String(255), nullable=True),
        sa.Column("consent_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name="fk_tc_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["connectors.id"], ondelete="RESTRICT", name="fk_tc_connector"
        ),
        sa.UniqueConstraint("tenant_id", "connector_id", name="uq_tc_tenant_connector"),
        sa.CheckConstraint(
            "status IN ('pending', 'connected', 'partial', 'needs_reauth', "
            "'disconnected', 'error')",
            name="ck_tc_status",
        ),
    )
    op.create_index("ix_tc_tenant", "tenant_connectors", ["tenant_id"])
    op.create_index("ix_tc_tenant_status", "tenant_connectors", ["tenant_id", "status"])
    op.execute("ALTER TABLE tenant_connectors ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_connectors FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="tenant_connectors"))

    # ── tenant_connector_tool_overrides (per-tenant per-tool gating) ────────
    op.create_table(
        "tenant_connector_tool_overrides",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("set_by_actor", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name="fk_tcto_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["tool_name"],
            ["tool_catalog.name"],
            ondelete="RESTRICT",
            name="fk_tcto_tool",
        ),
        sa.UniqueConstraint(
            "tenant_id", "tool_name", name="uq_tcto_tenant_tool"
        ),
        sa.CheckConstraint(
            "mode IN ('always', 'blocked', 'needs_approval')",
            name="ck_tcto_mode",
        ),
    )
    op.create_index(
        "ix_tcto_tenant", "tenant_connector_tool_overrides", ["tenant_id"]
    )
    op.execute(
        "ALTER TABLE tenant_connector_tool_overrides ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE tenant_connector_tool_overrides FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        _RLS_POLICY_SQL.format(table="tenant_connector_tool_overrides")
    )

    # ── tool_catalog: connector_id FK + annotations + default_mode ──────────
    op.add_column(
        "tool_catalog",
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tool_catalog_connector",
        "tool_catalog",
        "connectors",
        ["connector_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tool_catalog_connector", "tool_catalog", ["connector_id"]
    )
    op.add_column(
        "tool_catalog",
        sa.Column(
            "read_only",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tool_catalog",
        sa.Column(
            "destructive",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tool_catalog",
        sa.Column(
            "requires_consent",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tool_catalog",
        sa.Column(
            "default_mode",
            sa.String(20),
            nullable=False,
            server_default="always",
        ),
    )
    op.create_check_constraint(
        "ck_tool_catalog_default_mode",
        "tool_catalog",
        "default_mode IN ('always', 'blocked', 'needs_approval')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tool_catalog_default_mode", "tool_catalog", type_="check")
    op.drop_column("tool_catalog", "default_mode")
    op.drop_column("tool_catalog", "requires_consent")
    op.drop_column("tool_catalog", "destructive")
    op.drop_column("tool_catalog", "read_only")
    op.drop_index("ix_tool_catalog_connector", table_name="tool_catalog")
    op.drop_constraint("fk_tool_catalog_connector", "tool_catalog", type_="foreignkey")
    op.drop_column("tool_catalog", "connector_id")

    op.execute(
        "DROP POLICY IF EXISTS tenant_connector_tool_overrides_tenant_isolation "
        "ON tenant_connector_tool_overrides"
    )
    op.execute(
        "ALTER TABLE tenant_connector_tool_overrides NO FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE tenant_connector_tool_overrides DISABLE ROW LEVEL SECURITY"
    )
    op.drop_index(
        "ix_tcto_tenant", table_name="tenant_connector_tool_overrides"
    )
    op.drop_table("tenant_connector_tool_overrides")

    op.execute(
        "DROP POLICY IF EXISTS tenant_connectors_tenant_isolation "
        "ON tenant_connectors"
    )
    op.execute("ALTER TABLE tenant_connectors NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_connectors DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_tc_tenant_status", table_name="tenant_connectors")
    op.drop_index("ix_tc_tenant", table_name="tenant_connectors")
    op.drop_table("tenant_connectors")

    op.drop_index("ix_connectors_category_available", table_name="connectors")
    op.drop_table("connectors")
