"""conversations.agent_active — per-thread human takeover flag

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-13

Block M.3 — the operator can take control of a specific conversation
without pausing the whole tenant. Pipeline runs inside
``process_inbound`` check ``conversation.agent_active`` after the
tenant.status gate (M.1); when false, the inbound is still persisted
for audit + panel surface but the agent does NOT respond. Reactivating
the agent on the conversation does NOT trigger a backlog flush —
the agent picks up at the next inbound turn.

Default ``true`` so existing rows pre-Block-M behave exactly as before
(agent always on). New conversations created by ``upsert_conversation_for_customer``
inherit the column default — no application change required.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "agent_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "agent_active")
