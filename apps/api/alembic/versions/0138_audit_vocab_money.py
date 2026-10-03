"""Spec 027: the audit says how much balance moved, in money.

The summary of ``console.allocation.move`` said «movió {qty} créditos de
{from} a {to}» and none of those three values was ever filled in, so the
partner read «movió ? créditos de ? a ?». Now: «movió 10,00 US$ de A a B».

Revision ID: 0138_audit_vocab_money
Revises: 0137_payment_reviews
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0138_audit_vocab_money"
down_revision: str | Sequence[str] | None = "0137_payment_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTION = "console.allocation.move"
NEW = ("{actor} movió {amount} de {from} a {to}.", "{actor} moved {amount} from {from} to {to}.")
OLD = (
    "{actor} movió {qty} créditos de {from} a {to}.",
    "{actor} moved {qty} credits from {from} to {to}.",
)


def _set(es: str, en: str) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE console_audit_vocabulary SET summary_es = :es, summary_en = :en "
            "WHERE action = :action"
        ),
        {"es": es, "en": en, "action": ACTION},
    )


def upgrade() -> None:
    _set(*NEW)


def downgrade() -> None:
    _set(*OLD)
