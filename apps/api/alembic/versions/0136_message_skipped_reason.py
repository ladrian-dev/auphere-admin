"""Spec 024: why an inbound got no answer.

``messages.skipped_reason`` (nullable) is set by the worker when a gate
suppresses the reply — today ``not_admin`` (the admin-only whitelist). It
is what lets Conversaciones say «sin responder · número no permitido»
instead of showing a silence that looks like a pending message. No
backfill: older rows have no known reason and none is invented.

Revision ID: 0136_message_skipped_reason
Revises: 0135_catalog_tools
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0136_message_skipped_reason"
down_revision: str | Sequence[str] | None = "0135_catalog_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("skipped_reason", sa.String(length=40), nullable=True))
    # Partial index: the console counts unanswered inbounds per conversation;
    # almost every row is NULL and stays out of the index.
    op.create_index(
        "ix_messages_skipped_reason",
        "messages",
        ["conversation_id"],
        unique=False,
        postgresql_where=sa.text("skipped_reason IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_skipped_reason", table_name="messages")
    op.drop_column("messages", "skipped_reason")
