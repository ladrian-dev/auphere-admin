"""partner card, automatic charges and the postpaid credit line — spec 041

Three things, all partner-scoped money:

- ``partner_wallets.credit_limit`` (credits): how far below zero the
  purchased balance may go. ``0`` = prepaid, as before, for everyone. Auphere
  grants a line to a partner it trusts; the partner then may choose postpaid.
  The CHECK moves from ``purchased_remaining >= 0`` to
  ``purchased_remaining >= -credit_limit``: the database, not the code, is
  what stops a balance going past its line.
- ``partner_billing``: the partner's card on file (Stripe customer and
  payment method ids, brand, last four, expiry — never the number) and how it
  is charged: ``manual`` (buys balance by hand), ``auto_recharge`` (below a
  threshold, a fixed amount) or ``postpaid`` (the debt is charged on the 1st).
- ``partner_charges``: every automatic charge, one row per attempt, unique on
  its idempotency key so a retried job cannot charge twice. A card that asks
  for authentication (3D Secure) leaves the charge ``action_required`` with
  the Stripe page where the partner confirms it (``action_url``).
- ``partner_billing.granted_credit_limit`` / ``credit_frozen_at``: the line
  Auphere granted, and when a failed postpaid charge froze it — the wallet's
  ``credit_limit`` then drops to what is already owed until the debt is paid.

Both new tables carry FORCE RLS by ``app.partner_id``, like the wallet.

Revision ID: 0161_partner_card_and_charges
Revises: 0160_channel_signup_links
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0161_partner_card_and_charges"
down_revision: str | Sequence[str] | None = "0160_channel_signup_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"
_TABLES = ("partner_billing", "partner_charges")


def upgrade() -> None:
    op.add_column(
        "partner_wallets",
        sa.Column("credit_limit", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_partner_wallets_credit_limit_nonneg", "partner_wallets", "credit_limit >= 0"
    )
    op.drop_constraint("ck_partner_wallets_purchased_nonneg", "partner_wallets", type_="check")
    op.create_check_constraint(
        "ck_partner_wallets_purchased_floor",
        "partner_wallets",
        "purchased_remaining >= -credit_limit",
    )

    op.create_table(
        "partner_billing",
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("payment_method_id", sa.String(64), nullable=True),
        sa.Column("card_brand", sa.String(24), nullable=True),
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("card_exp_month", sa.SmallInteger(), nullable=True),
        sa.Column("card_exp_year", sa.SmallInteger(), nullable=True),
        sa.Column("card_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("recharge_threshold_cents", sa.Integer(), nullable=True),
        sa.Column("recharge_amount_cents", sa.Integer(), nullable=True),
        sa.Column("failed_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("paused_reason", sa.String(64), nullable=True),
        sa.Column("granted_credit_limit", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("credit_frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "mode IN ('manual', 'auto_recharge', 'postpaid')", name="ck_partner_billing_mode"
        ),
        sa.CheckConstraint(
            "mode <> 'auto_recharge' OR (recharge_threshold_cents >= 0 "
            "AND recharge_amount_cents >= 500)",
            name="ck_partner_billing_recharge",
        ),
    )

    op.create_table(
        "partner_charges",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        #: ``YYYY-MM`` of the debt a postpaid charge settles.
        sa.Column("period", sa.String(7), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("stripe_invoice_id", sa.String(64), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("action_url", sa.String(512), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('auto_recharge', 'postpaid')", name="ck_partner_charges_kind"),
        sa.CheckConstraint(
            "status IN ('pending', 'action_required', 'paid', 'failed')",
            name="ck_partner_charges_status",
        ),
        sa.CheckConstraint("amount_cents > 0", name="ck_partner_charges_amount_pos"),
    )
    op.create_index(
        "uq_partner_charges_idempotency", "partner_charges", ["idempotency_key"], unique=True
    )
    op.create_index(
        "ix_partner_charges_partner_created", "partner_charges", ["partner_id", "created_at"]
    )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_partner_isolation ON {table}
            USING (partner_id = {_PARTNER})
            WITH CHECK (partner_id = {_PARTNER})
            """
        )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON partner_billing, partner_charges TO nexus_app"
    )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_partner_isolation ON {table}")
    op.drop_table("partner_charges")
    op.drop_table("partner_billing")
    op.drop_constraint("ck_partner_wallets_purchased_floor", "partner_wallets", type_="check")
    op.create_check_constraint(
        "ck_partner_wallets_purchased_nonneg", "partner_wallets", "purchased_remaining >= 0"
    )
    op.drop_constraint("ck_partner_wallets_credit_limit_nonneg", "partner_wallets", type_="check")
    op.drop_column("partner_wallets", "credit_limit")
