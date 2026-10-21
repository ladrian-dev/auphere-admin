"""A partner's client with unlimited consumption: the agent never stops for
lack of balance and its consumption is not taken from the partner.

Owner, 2026-10-20: only Auphere turns it on, from the Admin. While it is on,
``allow_channel_turn`` lets every turn through (no balance, no cap) and the
worker writes the turn as ``absorbed`` in the ledger instead of a ``debit``:
measured, visible to Auphere, and outside the partner's money.

Revision ID: 0164_unlimited_consumption
Revises: 0163_manual_payments_credit
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0164_unlimited_consumption"
down_revision: str | Sequence[str] | None = "0163_manual_payments_credit"
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
    "credit_manual",
    "credit_reversal",
)
NEW = (*OLD, "absorbed")

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "client_consumption.unlimited_on",
        "billing",
        "info",
        "Auphere activó el consumo ilimitado de {client}: su consumo lo asume Auphere.",
        "Auphere turned on unlimited consumption for {client}: Auphere covers it.",
    ),
    (
        "client_consumption.unlimited_off",
        "billing",
        "warning",
        "Auphere desactivó el consumo ilimitado de {client}: vuelve a gastar de tu saldo.",
        "Auphere turned off unlimited consumption for {client}: it spends your balance again.",
    ),
)


def _check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint("ck_usage_ledger_kind", "usage_ledger", type_="check")
    op.create_check_constraint(
        "ck_usage_ledger_kind",
        "usage_ledger",
        "kind IN (" + ", ".join(f"'{k}'" for k in kinds) + ")",
    )


def upgrade() -> None:
    _check(NEW)
    op.add_column(
        "tenants",
        sa.Column("unlimited_consumption", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    bind = op.get_bind()
    for action, category, severity, es, en in VOCABULARY:
        bind.execute(
            sa.text(
                "INSERT INTO console_audit_vocabulary "
                "(action, category, severity, summary_es, summary_en) "
                "VALUES (:action, :category, :severity, :es, :en) "
                "ON CONFLICT (action) DO NOTHING"
            ),
            {"action": action, "category": category, "severity": severity, "es": es, "en": en},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for action, *_ in VOCABULARY:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": action}
        )
    op.drop_column("tenants", "unlimited_consumption")
    op.execute("DELETE FROM usage_ledger WHERE kind = 'absorbed'")
    _check(OLD)
