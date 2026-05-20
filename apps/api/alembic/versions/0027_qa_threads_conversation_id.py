"""qa.threads gains a conversation_id link (ADR-020, Fase 5 closure).

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-19

When the Playground composer fires a message, the agent graph needs a
real ``conversation_id`` to attach the inbound + outbound ``messages``
to (the ``checkpoint`` node persists the outbound and the FK back to
``conversations`` is NOT NULL). Before this migration we had no place
to remember which conversation a QA thread was bound to — so every
send had to scan or invent one.

This adds ``qa.threads.conversation_id`` as a nullable FK with ON
DELETE SET NULL. The send endpoint reads it lazily:

  - First send: create a customer + conversation + inbound message,
    stamp ``conversation_id`` on the thread.
  - Subsequent sends: reuse the conversation, append a new inbound.

The column is nullable because:
  - Existing rows pre-this-migration have nothing to link.
  - The thread is created BEFORE the first run (operator clicks
    "+ nueva" with no message yet).
  - Archived threads should not block reads of the FK target.

No RLS change required — the policy already scopes by ``operator_id``,
and ``conversation_id`` is just a foreign key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="qa",
    )
    op.create_index(
        "ix_qa_threads_conversation_id",
        "threads",
        ["conversation_id"],
        schema="qa",
    )


def downgrade() -> None:
    op.drop_index("ix_qa_threads_conversation_id", "threads", schema="qa")
    op.drop_column("threads", "conversation_id", schema="qa")
