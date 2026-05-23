"""qa.threads gains a per-thread dry_run flag (ADR-024).

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-23

The QA Playground was always built with the MCP registry forced into
``dry_run=True`` (ADR-020 Fase 3): any tool with non-empty
``side_effects`` was intercepted and returned a synthetic envelope. That
is the right default — the Playground must not silently mutate a
tenant's calendar, WooCommerce store or Composio-backed accounts — but
it also blocks the legitimate "validate end-to-end against the real
connector" workflow. Every WooCommerce read tool inherits
``side_effects=("external_api",)`` so even ``list_products`` /
``get_product`` come back as dry_run placeholders today; the operator
can't actually confirm the connector talks to the real store.

ADR-024 adds an opt-in: per-thread ``dry_run`` flag, default TRUE so
existing threads + the safe path stay unchanged. The Playground send
endpoint reads the flag and selects the dry / live pipeline accordingly.

The column is NOT NULL with a server default of TRUE so existing rows
backfill to dry_run automatically — no caller has to know about the
new column to keep behaving safely.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column(
            "dry_run",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        schema="qa",
    )


def downgrade() -> None:
    op.drop_column("threads", "dry_run", schema="qa")
