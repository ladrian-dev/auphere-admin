"""messages.idempotency_key — replay protection for direct sends

Revision ID: 0053_message_idempotency_key
Revises: 0052_api_key_tenant_scope
Create Date: 2026-07-20

``POST /v1/messages/template`` is called from automation (n8n, cron)
where a retry after a timeout is normal: the message was queued, the
response never made it back, the caller tries again. Without a dedupe
key that is a second WhatsApp message to a real customer — and for a
MARKETING template, a second charge.

Mirrors ``broadcasts.idempotency_key`` exactly (same width, same partial
unique index scoped by tenant) so both surfaces behave identically and
one mental model covers the API.

Scoped per tenant, not global: two clients picking the same key —
``"2026-07-20-fila-15"`` is an entirely plausible collision — must not
be able to suppress each other's messages. NULL is exempt from the
unique index, so every send that does not opt in stays unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0053_message_idempotency_key"
down_revision: str | Sequence[str] | None = "0052_api_key_tenant_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("idempotency_key", sa.String(80), nullable=True))
    op.create_index(
        "uq_messages_tenant_idempotency",
        "messages",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_tenant_idempotency", table_name="messages")
    op.drop_column("messages", "idempotency_key")
