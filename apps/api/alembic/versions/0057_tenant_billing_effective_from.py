"""tenants.billing_effective_from — first month a subscription is billed

Revision ID: 0057_tenant_billing_effective_from
Revises: 0056_agent_sales
Create Date: 2026-07-22

The monthly partner receipt charges a subscription **in advance** for its
emission month. A tenant whose service begins later (e.g. New Air starting
August) must not be billed before then. ``billing_effective_from`` (a DATE,
NULL = active from the start) gates the subscription line: it is charged only
when the receipt's emission month (the 1st of the month after the billed
period) is on or after this date.

Nullable, no default — existing tenants keep billing from the start.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_tenant_billing_effective_from"
down_revision: str | Sequence[str] | None = "0056_agent_sales"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("billing_effective_from", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "billing_effective_from")
