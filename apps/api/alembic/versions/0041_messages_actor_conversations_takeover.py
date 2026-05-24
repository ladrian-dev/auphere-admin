"""messages.actor_* + conversations.takeover_context + agent_active_version

Revision ID: 0041
Revises: 0040
Create Date: 2026-05-25

Bloque C — Operator intervention. Adds the schema scaffolding for the
operator-takeover loop:

``messages.actor_kind`` (varchar[20], nullable, CHECK in agent | operator |
owner | system) identifies WHO produced an outbound row. NULL on inbound
rows (the customer is always implied) and on every row written before this
migration (back-compat). Outbound rows written from now on set it
explicitly — ``agent`` for pipeline-generated, ``operator`` for the new
``POST .../conversations/:id/send`` endpoint, ``owner`` for backchannel
replies (Phase 2), ``system`` for templates / opt-out confirmations.

``messages.actor_id`` (uuid, nullable) is the admin user uuid for
operator rows, NULL otherwise. There's no FK because admin auth is
token-based; we just store the resolved uuid for audit/UX.

``conversations.takeover_context`` (jsonb, nullable) holds operator notes
captured at pause time (``{reason, notes, started_at, operator_id}``).
The pipeline consumes it on the first turn after the agent is reactivated
to build the "what the human did while you were paused" briefing, then
clears the column.

``conversations.agent_active_version`` (int, NOT NULL, default 0) is the
optimistic-locking counter for the PATCH ``.../agent`` endpoint. Every
flip increments it; clients send the previous value via ``If-Match`` and
a mismatch returns 412.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041"
down_revision: str | Sequence[str] | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("actor_kind", sa.String(20), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("actor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_messages_actor_kind",
        "messages",
        "actor_kind IS NULL OR actor_kind IN ('agent', 'operator', 'owner', 'system')",
    )

    op.add_column(
        "conversations",
        sa.Column(
            "takeover_context",
            sa.dialects.postgresql.JSONB,
            nullable=True,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "agent_active_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "agent_active_version")
    op.drop_column("conversations", "takeover_context")
    op.drop_constraint("ck_messages_actor_kind", "messages", type_="check")
    op.drop_column("messages", "actor_id")
    op.drop_column("messages", "actor_kind")
