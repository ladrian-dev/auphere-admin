"""agent_sales — WhatsApp-attributed WooCommerce orders for commission

Revision ID: 0056_agent_sales
Revises: 0055_invoices
Create Date: 2026-07-21

Barber Supply pays Facelad a 2.5% commission on sales its WhatsApp agent
closes. The agent doesn't create the order — it sends a checkout link
tagged ``wa=1``; WooCommerce creates the paid order later. So the source
of truth is WooCommerce itself: a daily poll finds paid orders carrying
the WhatsApp tag and records them here.

Captured faithfully in the store's own currency (``gross_amount`` +
``currency``), NOT pre-converted: the sale is CLP-or-whatever, and the
FX-to-USD needed for the invoice is a later, auditable step. Amounts are
Numeric, not integer cents, because the store currency's minor unit is
unknown at this layer (CLP has none).

Tenant-scoped (RLS): these are the tenant's sales, same trust model as
``messages``. UNIQUE ``(tenant_id, wc_order_id)`` makes the poll
idempotent — re-seeing an order updates it, never duplicates it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0056_agent_sales"
down_revision: str | Sequence[str] | None = "0055_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sales",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        # WooCommerce order id — the store's own primary key for the sale.
        sa.Column("wc_order_id", sa.BigInteger, nullable=False),
        # Attribution, best-effort: resolved from the conversation when the
        # poll can match it; NULL when only the order is known.
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Money, in the store's currency — captured, not converted.
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("commission_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("commission_amount", sa.Numeric(14, 2), nullable=False),
        # WooCommerce lifecycle. ``date_paid`` non-null is the pay signal;
        # ``wc_status`` lets a later refund/cancel reverse the commission.
        sa.Column("wc_status", sa.String(20), nullable=False),
        sa.Column("date_paid", sa.DateTime(timezone=True), nullable=True),
        # Set once this sale has been rolled into an issued invoice line,
        # so the next commission run doesn't bill it twice.
        sa.Column(
            "invoice_line_id",
            UUID(as_uuid=True),
            sa.ForeignKey("invoice_lines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Raw order snapshot (tag, transaction_id, totals) for audit.
        sa.Column("source_meta", JSONB, nullable=True),
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
        sa.CheckConstraint("gross_amount >= 0", name="ck_agent_sales_gross_nonneg"),
        sa.CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 1", name="ck_agent_sales_rate_range"
        ),
    )
    # Idempotency of the poll: one row per (tenant, order).
    op.create_index(
        "uq_agent_sales_tenant_order",
        "agent_sales",
        ["tenant_id", "wc_order_id"],
        unique=True,
    )
    # The commission run scans a tenant's paid, not-yet-invoiced sales.
    op.create_index(
        "ix_agent_sales_tenant_paid",
        "agent_sales",
        ["tenant_id", "date_paid"],
    )

    # RLS — exact 0002 pattern (see 0048_broadcasts).
    op.execute("ALTER TABLE agent_sales ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_sales FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY agent_sales_tenant_isolation ON agent_sales
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON agent_sales TO nexus_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON agent_sales FROM nexus_app")
    op.execute("DROP POLICY IF EXISTS agent_sales_tenant_isolation ON agent_sales")
    op.drop_table("agent_sales")
