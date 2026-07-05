"""messages.template_payload — HSM template send path for broadcasts

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-05

ADR-028 — the outbound dispatcher historically routes pending rows as
interactive / media / text only; templates were sent inline by the
operator endpoint and the ``notification.send_template`` tool, outside
the dispatcher. Broadcast fan-out needs templates to flow through the
dispatcher's pending-row path (retry, opt-out, SKIP LOCKED batching),
so this column mirrors the ``interactive_payload`` pattern:

    {"name": str, "language": str,
     "params": {"body": {<named var>: <value>}, "header": [...], "buttons": [...]}}

Rows with a non-NULL ``template_payload`` route through
``adapter.send_template`` (named parameters already supported by
``_build_template_components``); every other row is untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0049_message_template_payload"
down_revision: str | Sequence[str] | None = "0048_broadcasts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("template_payload", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "template_payload")
