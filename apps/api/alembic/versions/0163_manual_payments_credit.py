"""A partner's payment received outside Stripe credits its balance.

Owner, 2026-10-20: the partner pays Auphere, not the client. Recording a
payment in the Admin now credits the partner's recharged balance once
(``credit_manual``) and voiding it takes that back (``credit_reversal``).
``tenant_payments.credited_cents`` says how much a payment credited; the rows
recorded before this change stay NULL — a record, no credit (owner's call).

Revision ID: 0163_manual_payments_credit
Revises: 0162_audit_vocab_cards_and_links
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0163_manual_payments_credit"
down_revision: str | Sequence[str] | None = "0162_audit_vocab_cards_and_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
    "debit",
    "credit_admin",
    "credit_stripe",
    "expiry",
    "allocation_legacy",
    "opening_credit",
    "opening_debit",
)
NEW = (*OLD, "credit_manual", "credit_reversal")


def _check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint("ck_usage_ledger_kind", "usage_ledger", type_="check")
    op.create_check_constraint(
        "ck_usage_ledger_kind",
        "usage_ledger",
        "kind IN (" + ", ".join(f"'{k}'" for k in kinds) + ")",
    )


REVERSED = (
    "wallet.payment_reversed",
    "billing",
    "warning",
    "{actor} anuló un pago y descontó {amount} del saldo.",
    "{actor} voided a payment and took {amount} off the balance.",
)


def upgrade() -> None:
    _check(NEW)
    op.add_column("tenant_payments", sa.Column("credited_cents", sa.Integer(), nullable=True))
    action, category, severity, es, en = REVERSED
    op.get_bind().execute(
        sa.text(
            "INSERT INTO console_audit_vocabulary "
            "(action, category, severity, summary_es, summary_en) "
            "VALUES (:action, :category, :severity, :es, :en) "
            "ON CONFLICT (action) DO NOTHING"
        ),
        {"action": action, "category": category, "severity": severity, "es": es, "en": en},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": REVERSED[0]}
    )
    op.drop_column("tenant_payments", "credited_cents")
    op.execute("DELETE FROM usage_ledger WHERE kind IN ('credit_manual', 'credit_reversal')")
    _check(OLD)
