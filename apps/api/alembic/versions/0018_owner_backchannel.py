"""owner backchannel — Phase 1: ADR-018 + architecture/owner-backchannel.md

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-13

Adds:

- ``owner_consultations`` — durable log of every question the agent (or a
  cron/admin actor in later phases) asks the tenant's owner via the
  Auphere ↔ Owner backchannel. RLS + FORCE. Lifecycle is enforced by a
  CHECK constraint (pending → sent → answered, or timed_out / cancelled).
- ``owner_phone_index`` — global lookup ``phone_e164 → tenant_id`` used by
  the inbound webhook BEFORE we know which tenant to scope to. NOT
  RLS-scoped by design (mirrors ``tenants``). UNIQUE on phone — a single
  E.164 belongs to exactly one tenant; collisions surface at admin time.
- ``conversations.awaiting_owner_response`` + ``awaiting_owner_correlation_id``
  — durable flag so the pipeline knows a turn is paused on an owner
  reply even after a worker restart.
- ``tenants.backchannel_*`` — per-tenant config (enabled, rate caps, SLA
  windows). Defaults are sane and apply to every existing tenant
  (server_default).

Phase 2 will add slash-command-only columns, the offline-mode pause
counter, and any extra indexes operator-panel UIs need.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RLS_POLICY_SQL = """
CREATE POLICY {table}_tenant_isolation ON {table}
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
"""


def upgrade() -> None:
    # ── owner_consultations ────────────────────────────────────────────────
    op.create_table(
        "owner_consultations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("urgency", sa.String(10), nullable=False),
        sa.Column("expected_reply_kind", sa.String(20), nullable=False),
        sa.Column("template_name", sa.String(120), nullable=False),
        sa.Column(
            "template_params_json",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("ycloud_message_id", sa.String(120), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reminded_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("owner_response_text", sa.Text(), nullable=True),
        sa.Column("owner_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_command_kind", sa.String(20), nullable=True),
        sa.Column("timed_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(60), nullable=False),
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
        sa.CheckConstraint(
            "char_length(question_text) <= 1000",
            name="ck_owner_consultations_question_length",
        ),
        sa.CheckConstraint(
            "context_summary IS NULL OR char_length(context_summary) <= 500",
            name="ck_owner_consultations_context_length",
        ),
        sa.CheckConstraint(
            "urgency IN ('low','normal','high')",
            name="ck_owner_consultations_urgency",
        ),
        sa.CheckConstraint(
            "expected_reply_kind IN ('free_text','yes_no','action_done')",
            name="ck_owner_consultations_expected_reply_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','answered','timed_out','cancelled')",
            name="ck_owner_consultations_status",
        ),
        sa.CheckConstraint(
            "owner_command_kind IS NULL OR owner_command_kind IN "
            "('free_text','yes','no','handoff','pause','done','help')",
            name="ck_owner_consultations_command_kind",
        ),
        sa.CheckConstraint(
            "(status = 'pending'  AND sent_at IS NULL AND owner_response_at IS NULL) OR "
            "(status = 'sent'     AND sent_at IS NOT NULL AND owner_response_at IS NULL) OR "
            "(status = 'answered' AND sent_at IS NOT NULL AND owner_response_at IS NOT NULL) OR "
            "(status = 'timed_out' AND timed_out_at IS NOT NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="ck_owner_consultations_lifecycle",
        ),
    )
    op.create_index(
        "idx_oc_tenant_status_urgency",
        "owner_consultations",
        ["tenant_id", "status", "urgency", "asked_at"],
    )
    op.create_index(
        "idx_oc_conversation",
        "owner_consultations",
        ["conversation_id", "status"],
    )
    op.execute("ALTER TABLE owner_consultations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE owner_consultations FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="owner_consultations"))

    # ── owner_phone_index ─────────────────────────────────────────────────
    # Global lookup — NOT RLS-scoped. The inbound webhook resolves which
    # tenant a given phone belongs to before applying ``app.tenant_id``.
    # Same pattern as ``tenants`` and ``tool_catalog``.
    op.create_table(
        "owner_phone_index",
        sa.Column("phone_e164", sa.String(20), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_label", sa.String(120), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index(
        "idx_owner_phone_tenant", "owner_phone_index", ["tenant_id"]
    )

    # ── conversations: pending-owner-response flag ────────────────────────
    op.add_column(
        "conversations",
        sa.Column(
            "awaiting_owner_response",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "awaiting_owner_correlation_id",
            sa.String(40),
            nullable=True,
        ),
    )

    # ── tenants: backchannel config ───────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "backchannel_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "backchannel_max_consultations_per_hour",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "backchannel_offline_pause_after_timeouts",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "backchannel_sla_high_min",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "backchannel_sla_normal_min",
            sa.Integer(),
            nullable=False,
            server_default="240",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "backchannel_sla_low_min",
            sa.Integer(),
            nullable=False,
            server_default="1440",
        ),
    )

    # ── tool_catalog seed: operator.consult_owner ─────────────────────────
    # Idempotent INSERT. Mirrors the pattern in migration 0003.
    op.execute(
        """
        INSERT INTO tool_catalog
            (name, description, mcp_server, side_effects, capability_tags, status)
        VALUES (
            'operator.consult_owner',
            'Ask the tenant owner a question over the Auphere backchannel. '
            'Returns an ack message for the customer; the owner replies '
            'asynchronously and the pipeline re-enters when the response '
            'arrives. Use whenever the agent does not know the answer with '
            'certainty AND a human owner can resolve it.',
            'operator-server',
            ARRAY['sends_message','mutates_db','async_reply'],
            ARRAY['operator','hitl','backchannel'],
            'active'
        )
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM tool_catalog WHERE name = 'operator.consult_owner'")

    op.drop_column("tenants", "backchannel_sla_low_min")
    op.drop_column("tenants", "backchannel_sla_normal_min")
    op.drop_column("tenants", "backchannel_sla_high_min")
    op.drop_column("tenants", "backchannel_offline_pause_after_timeouts")
    op.drop_column("tenants", "backchannel_max_consultations_per_hour")
    op.drop_column("tenants", "backchannel_enabled")

    op.drop_column("conversations", "awaiting_owner_correlation_id")
    op.drop_column("conversations", "awaiting_owner_response")

    op.drop_index("idx_owner_phone_tenant", table_name="owner_phone_index")
    op.drop_table("owner_phone_index")

    op.execute("ALTER TABLE owner_consultations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE owner_consultations DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS owner_consultations_tenant_isolation "
        "ON owner_consultations"
    )
    op.drop_index("idx_oc_conversation", table_name="owner_consultations")
    op.drop_index(
        "idx_oc_tenant_status_urgency", table_name="owner_consultations"
    )
    op.drop_table("owner_consultations")
