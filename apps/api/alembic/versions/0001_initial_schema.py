"""initial schema — 13 tables of the factory

Revision ID: 0001
Revises:
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions (idempotent — they may already exist from infra/postgres/init.sql)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── enums ───────────────────────────────────────────────────────────────
    # Created up front; columns below reference them with create_type=False so
    # create_table doesn't try to re-create them.
    tenant_plan = postgresql.ENUM(
        "essential", "pro", "business", "internal", name="tenant_plan", create_type=False
    )
    tenant_status = postgresql.ENUM(
        "active", "paused", "archived", name="tenant_status", create_type=False
    )
    agent_config_status = postgresql.ENUM(
        "staged", "active", "archived", name="agent_config_status", create_type=False
    )
    tool_status = postgresql.ENUM(
        "active", "deprecated", "experimental", name="tool_status", create_type=False
    )
    channel_type = postgresql.ENUM(
        "whatsapp",
        "instagram",
        "telegram",
        "email",
        "web",
        name="channel_type",
        create_type=False,
    )
    channel_status = postgresql.ENUM(
        "active",
        "paused",
        "degraded",
        "disconnected",
        name="channel_status",
        create_type=False,
    )
    conversation_status = postgresql.ENUM(
        "open", "closed", "escalated", name="conversation_status", create_type=False
    )
    message_direction = postgresql.ENUM(
        "inbound", "outbound", name="message_direction", create_type=False
    )

    op.execute("CREATE TYPE tenant_plan AS ENUM ('essential', 'pro', 'business', 'internal')")
    op.execute("CREATE TYPE tenant_status AS ENUM ('active', 'paused', 'archived')")
    op.execute("CREATE TYPE agent_config_status AS ENUM ('staged', 'active', 'archived')")
    op.execute("CREATE TYPE tool_status AS ENUM ('active', 'deprecated', 'experimental')")
    op.execute(
        "CREATE TYPE channel_type AS ENUM ('whatsapp', 'instagram', 'telegram', 'email', 'web')"
    )
    op.execute(
        "CREATE TYPE channel_status AS ENUM ('active', 'paused', 'degraded', 'disconnected')"
    )
    op.execute("CREATE TYPE conversation_status AS ENUM ('open', 'closed', 'escalated')")
    op.execute("CREATE TYPE message_direction AS ENUM ('inbound', 'outbound')")

    # ── tenants ─────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("plan", tenant_plan, nullable=False, server_default="pro"),
        sa.Column("status", tenant_status, nullable=False, server_default="active"),
        sa.Column("market", sa.String(8), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("business_hours", postgresql.JSONB, nullable=True),
        sa.Column("owner_phone", sa.String(32), nullable=True),
        sa.Column("owner_email", sa.String(255), nullable=True),
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
    )

    # ── tool_catalog (global) ───────────────────────────────────────────────
    op.create_table(
        "tool_catalog",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("mcp_server", sa.String(80), nullable=False),
        sa.Column("input_schema", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("output_schema", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "side_effects", postgresql.ARRAY(sa.String(40)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "capability_tags", postgresql.ARRAY(sa.String(40)), nullable=False, server_default="{}"
        ),
        sa.Column("cost_estimate", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", tool_status, nullable=False, server_default="active"),
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
    )

    # ── kg_schemas (global) ─────────────────────────────────────────────────
    op.create_table(
        "kg_schemas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("schema_definition", postgresql.JSONB, nullable=False, server_default="{}"),
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
        sa.UniqueConstraint("name", "version", name="uq_kg_schemas_name_version"),
    )

    # ── agent_configs ───────────────────────────────────────────────────────
    op.create_table(
        "agent_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", agent_config_status, nullable=False, server_default="staged"),
        sa.Column("system_prompt_rendered", sa.Text, nullable=False),
        sa.Column("channels", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("tools", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("policies", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("seed_template_ref", sa.String(80), nullable=True),
        sa.Column(
            "kg_schema_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kg_schemas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.String(255), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "version", name="uq_agent_configs_tenant_version"),
    )
    op.create_index("ix_agent_configs_tenant_id", "agent_configs", ["tenant_id"])
    op.create_index("ix_agent_configs_status", "agent_configs", ["status"])

    # ── channels ────────────────────────────────────────────────────────────
    op.create_table(
        "channels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", channel_type, nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_identifier", sa.String(255), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("config_encrypted", sa.LargeBinary, nullable=True),
        sa.Column("status", channel_status, nullable=False, server_default="active"),
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
        sa.UniqueConstraint("type", "provider_identifier", name="uq_channels_type_provider_id"),
    )
    op.create_index("ix_channels_tenant_id", "channels", ["tenant_id"])

    # ── tenant_credentials ──────────────────────────────────────────────────
    op.create_table(
        "tenant_credentials",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration", sa.String(64), nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary, nullable=False),
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
        sa.UniqueConstraint(
            "tenant_id", "integration", name="uq_tenant_credentials_tenant_integration"
        ),
    )
    op.create_index("ix_tenant_credentials_tenant_id", "tenant_credentials", ["tenant_id"])

    # ── kg_nodes ────────────────────────────────────────────────────────────
    op.create_table(
        "kg_nodes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("properties", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("external_ref", sa.String(255), nullable=True),
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
    )
    op.create_index("ix_kg_nodes_tenant_id", "kg_nodes", ["tenant_id"])
    op.create_index("ix_kg_nodes_label", "kg_nodes", ["label"])

    # ── kg_edges ────────────────────────────────────────────────────────────
    op.create_table(
        "kg_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kg_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kg_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("properties", postgresql.JSONB, nullable=False, server_default="{}"),
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
    )
    op.create_index("ix_kg_edges_tenant_id", "kg_edges", ["tenant_id"])
    op.create_index("ix_kg_edges_label", "kg_edges", ["label"])
    op.create_index("ix_kg_edges_source_id", "kg_edges", ["source_id"])
    op.create_index("ix_kg_edges_target_id", "kg_edges", ["target_id"])

    # ── customers ───────────────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identifier", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("preferences", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "kg_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kg_nodes.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.UniqueConstraint("tenant_id", "identifier", name="uq_customers_tenant_identifier"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])

    # ── conversations ───────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", conversation_status, nullable=False, server_default="open"),
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
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_channel_id", "conversations", ["channel_id"])
    op.create_index("ix_conversations_customer_id", "conversations", ["customer_id"])
    op.create_index("ix_conversations_status", "conversations", ["status"])

    # ── messages ────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", message_direction, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("intent", sa.String(80), nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("trace_id", sa.String(120), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB, nullable=False, server_default="[]"),
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
    )
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_trace_id", "messages", ["trace_id"])

    # ── usage_events ────────────────────────────────────────────────────────
    op.create_table(
        "usage_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("day", sa.Date, nullable=False),
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
        sa.UniqueConstraint(
            "tenant_id", "event_type", "day", name="uq_usage_events_tenant_event_day"
        ),
    )
    op.create_index("ix_usage_events_tenant_id", "usage_events", ["tenant_id"])

    # ── audit_log ───────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("before_json", postgresql.JSONB, nullable=True),
        sa.Column("after_json", postgresql.JSONB, nullable=True),
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
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    for tbl in (
        "audit_log",
        "usage_events",
        "messages",
        "conversations",
        "customers",
        "kg_edges",
        "kg_nodes",
        "tenant_credentials",
        "channels",
        "agent_configs",
        "kg_schemas",
        "tool_catalog",
        "tenants",
    ):
        op.drop_table(tbl)
    for enum_name in (
        "message_direction",
        "conversation_status",
        "channel_status",
        "channel_type",
        "tool_status",
        "agent_config_status",
        "tenant_status",
        "tenant_plan",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
