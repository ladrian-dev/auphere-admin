"""invoices + invoice_lines — monthly billing documents

Revision ID: 0055_invoices
Revises: 0054_billing_model
Create Date: 2026-07-21

Second half of the internal billing model. One invoice per payer per
month; a payer is EITHER a partner (agency, billed for all its tenants)
OR a single direct tenant. The ``ck_invoices_one_payer`` CHECK enforces
exactly-one — an invoice with both or neither is a modelling bug, caught
by the database rather than trusted to application code.

Lines are the breakdown: one per tenant on the invoice. A partner
invoice has N lines (its N tenants), a direct invoice has exactly one
(the tenant itself).

Amounts are USD cents everywhere. Platform-level, no RLS — these are
Auphere's billing records, never exposed to the tenant.

The partial unique indexes stop a double-run of the monthly cron from
issuing two invoices for the same payer and period.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0055_invoices"
down_revision: str | Sequence[str] | None = "0054_billing_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        # Exactly one of these is set (see CHECK). Both RESTRICT: a payer
        # with invoices on file cannot be silently deleted.
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("period_year", sa.Integer, nullable=False),
        sa.Column("period_month", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("total_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
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
            "(partner_id IS NOT NULL) <> (tenant_id IS NOT NULL)",
            name="ck_invoices_one_payer",
        ),
        sa.CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_invoices_period_month"),
        sa.CheckConstraint(
            "status IN ('draft', 'issued', 'paid', 'void')", name="ck_invoices_status"
        ),
    )
    # One invoice per payer per period — the cron's replay guard.
    op.create_index(
        "uq_invoices_partner_period",
        "invoices",
        ["partner_id", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("partner_id IS NOT NULL"),
    )
    op.create_index(
        "uq_invoices_tenant_period",
        "invoices",
        ["tenant_id", "period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )

    op.create_table(
        "invoice_lines",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "invoice_id",
            UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON invoices, invoice_lines TO nexus_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON invoices, invoice_lines FROM nexus_app")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
