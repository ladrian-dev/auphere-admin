"""billing plans + tenant→partner billing relation

Revision ID: 0054_billing_model
Revises: 0053_message_idempotency_key
Create Date: 2026-07-21

First half of the internal billing model (Stripe comes later, in its own
migration). Establishes WHO pays for WHAT and HOW MUCH:

- ``billing_plans`` — the price catalogue. A plan is a code + a monthly
  amount in **USD cents** (integer, never float — money). Platform-level,
  no RLS: prices are Auphere's, not a tenant's.
- ``partners.billing_email`` — where an agency's invoice is sent. Agencies
  (Amacrux, Facelad) are the payers for their tenants.
- ``tenants.partner_id`` — NULL means "direct Auphere client", billed
  individually; set means the tenant rolls up into that partner's monthly
  invoice. ON DELETE RESTRICT so a partner with live tenants can't be
  deleted out from under its billing.
- ``tenants.billing_plan_id`` + ``price_override_cents`` — the plan gives
  the base price; the override wins when a tenant has a negotiated rate.
  NULL override → use the plan.

Currency is USD everywhere (product decision), so there is no per-row
currency column — it would be dead weight that only invites drift.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0054_billing_model"
down_revision: str | Sequence[str] | None = "0053_message_idempotency_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_plans",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        # USD cents. CHECK >= 0 — a negative price is always a bug.
        sa.Column("monthly_amount_cents", sa.Integer, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
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
        sa.CheckConstraint("monthly_amount_cents >= 0", name="ck_billing_plans_amount_nonneg"),
    )

    op.add_column("partners", sa.Column("billing_email", sa.String(255), nullable=True))

    op.add_column(
        "tenants",
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "billing_plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("billing_plans.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("price_override_cents", sa.Integer, nullable=True),
    )
    op.create_check_constraint(
        "ck_tenants_price_override_nonneg",
        "tenants",
        "price_override_cents IS NULL OR price_override_cents >= 0",
    )
    op.create_index("ix_tenants_partner_id", "tenants", ["partner_id"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON billing_plans TO nexus_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON billing_plans FROM nexus_app")
    op.drop_index("ix_tenants_partner_id", table_name="tenants")
    op.drop_constraint("ck_tenants_price_override_nonneg", "tenants", type_="check")
    op.drop_column("tenants", "price_override_cents")
    op.drop_column("tenants", "billing_plan_id")
    op.drop_column("tenants", "partner_id")
    op.drop_column("partners", "billing_email")
    op.drop_table("billing_plans")
