"""Payment reviews (spec 025): the business team confirms or rejects a payment.

Two tenant-scoped tables with forced RLS — ``payment_reviews`` (one per
payment waiting for the team) and ``payment_review_notices`` (one per
reviewer the review was sent to) — plus the ``payments.request_review`` row
in ``tool_catalog`` and the two audit actions the console counts.

Revision ID: 0137_payment_reviews
Revises: 0136_message_skipped_reason
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision: str = "0137_payment_reviews"
down_revision: str | Sequence[str] | None = "0136_message_skipped_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "0137_payment_tools.json"
_REVIEWS = "payment_reviews"
_NOTICES = "payment_review_notices"
_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

VOCABULARY = (
    (
        "payment_review.opened",
        "agents",
        "info",
        "El agente pidió al equipo de {client} revisar un pago.",
        "The agent asked {client}'s team to review a payment.",
    ),
    (
        "payment_review.resolved",
        "agents",
        "info",
        "{actor} resolvió un pago de {client}.",
        "{actor} resolved a payment of {client}.",
    ),
)


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} {_POLICY}")


def upgrade() -> None:
    op.create_table(
        _REVIEWS,
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(16), nullable=False, unique=True),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("summary", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("order_id", sa.String(40), nullable=True),
        sa.Column("order_status", sa.String(40), nullable=True),
        sa.Column(
            "receipt_message_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("resolved_by_phone", sa.String(32), nullable=True),
        sa.Column("resolved_by_name", sa.String(120), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_notified", sa.Boolean(), nullable=True),
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
            "status IN ('pending', 'confirmed', 'rejected', 'informed')",
            name="ck_payment_reviews_status",
        ),
        sa.CheckConstraint("method IN ('transfer', 'link')", name="ck_payment_reviews_method"),
        sa.CheckConstraint(
            "(status IN ('confirmed', 'rejected')) = (resolved_at IS NOT NULL)",
            name="ck_payment_reviews_resolved",
        ),
    )
    op.create_index(
        "ix_payment_reviews_conversation", _REVIEWS, ["tenant_id", "conversation_id", "status"]
    )
    _rls(_REVIEWS)

    op.create_table(
        _NOTICES,
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "review_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{_REVIEWS}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reviewer_phone", sa.String(32), nullable=False),
        sa.Column("reviewer_name", sa.String(120), nullable=True),
        sa.Column(
            "reviewer_conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delivery", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(40), nullable=True),
        # ``messages`` is partitioned (no single-column unique key): no FK.
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "delivery IN ('interactive', 'undelivered')", name="ck_payment_review_notices_delivery"
        ),
        sa.UniqueConstraint("review_id", "reviewer_phone", name="uq_payment_review_notice_phone"),
    )
    op.create_index("ix_payment_review_notices_tenant", _NOTICES, ["tenant_id"])
    _rls(_NOTICES)

    bind = op.get_bind()
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        catalog: dict[str, dict] = json.load(fh)
    for tool_name, spec in catalog.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO tool_catalog (
                    name, description, mcp_server,
                    input_schema, output_schema,
                    side_effects, capability_tags, cost_estimate,
                    connector_id, read_only, destructive, requires_consent,
                    default_mode
                ) VALUES (
                    :name, :description, 'payments-server',
                    CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb),
                    CAST('{mutates_db,sends_message}' AS varchar[]),
                    CAST('{payments,escalate}' AS varchar[]),
                    CAST('{}' AS jsonb),
                    NULL, false, false, false,
                    'always'
                )
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    input_schema = EXCLUDED.input_schema,
                    output_schema = EXCLUDED.output_schema
                """
            ),
            {
                "name": tool_name,
                "description": spec["description"],
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
            },
        )

    for action, category, severity, summary_es, summary_en in VOCABULARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT
                    CAST(:action AS VARCHAR(80)),
                    CAST(:category AS VARCHAR(40)),
                    CAST(:severity AS VARCHAR(10)),
                    CAST(:summary_es AS TEXT),
                    CAST(:summary_en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary
                    WHERE action = CAST(:action AS VARCHAR(80))
                )
                """
            ),
            {
                "action": action,
                "category": category,
                "severity": severity,
                "summary_es": summary_es,
                "summary_en": summary_en,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM console_audit_vocabulary WHERE action IN "
            "('payment_review.opened', 'payment_review.resolved')"
        )
    )
    bind.execute(sa.text("DELETE FROM tool_catalog WHERE name = 'payments.request_review'"))
    op.execute(f"DROP POLICY IF EXISTS {_NOTICES}_tenant_isolation ON {_NOTICES}")
    op.drop_index("ix_payment_review_notices_tenant", table_name=_NOTICES)
    op.drop_table(_NOTICES)
    op.execute(f"DROP POLICY IF EXISTS {_REVIEWS}_tenant_isolation ON {_REVIEWS}")
    op.drop_index("ix_payment_reviews_conversation", table_name=_REVIEWS)
    op.drop_table(_REVIEWS)
