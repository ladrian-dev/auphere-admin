"""owner_phone_index.confirmed_at — Phase 2 TOFU onboarding

Revision ID: 0043
Revises: 0042
Create Date: 2026-05-25

Phase 2 backchannel — Trust-On-First-Use for the owner channel.

The admin registers an owner phone in ``owner_phone_index`` via the
backchannel UI. Before this migration, that registration immediately
unlocks the full slash-command + consultation surface for whoever
controls that number. A typo (wrong country code, transposed digits,
ex-employee number recycled by the carrier) silently routes a stranger
into the tenant's backchannel.

This migration adds the bookkeeping for an explicit confirmation step:

- ``confirmed_at`` (DateTime, nullable) — set by the webhook on the
  first ``/yes`` from the registered phone. Rows where this is NULL
  cannot drive consultations, slash side effects, or any tenant write
  — they only receive an instructions reply.

Existing rows are backfilled to ``added_at`` so Phase 1 owners stay
operational without re-confirming. The backfill runs only for ACTIVE
rows; inactive ones get left at NULL since they're not in use anyway.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043"
down_revision: str | Sequence[str] | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "owner_phone_index",
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Back-compat: existing ACTIVE owners are already in production use,
    # don't force them through the TOFU welcome — backfill to added_at.
    op.execute(
        "UPDATE owner_phone_index "
        "SET confirmed_at = added_at "
        "WHERE active = TRUE AND confirmed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("owner_phone_index", "confirmed_at")
