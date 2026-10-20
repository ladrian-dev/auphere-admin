"""client_push_events — el outbox de avisos (spec 031, data-model §0160).

Un hecho que puede producir avisos al teléfono. Se escribe **en la misma
transacción que el hecho** (el escalado, el mensaje entrante, el aviso de
saldo), así el worker solo ve lo que quedó confirmado (R8.5). Es el patrón de
``messages.status = 'pending'``: una fila es el trabajo, y el disparador avisa
al worker con el tenant para que no recorra tenants sin trabajo (0062).

**Sin contenido.** Ni nombre, ni texto, ni motivo: referencias. El texto del
aviso se compone al repartir, con los datos de ese momento.

Revision ID: 0160_client_push_events
Revises: 0159_session_codes_purpose
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0160_client_push_events"
down_revision: str | Sequence[str] | None = "0159_session_codes_purpose"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"


def upgrade() -> None:
    op.create_table(
        "client_push_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("notification_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_principal_id", sa.String(64), nullable=True),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("fanned_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('client.balance', 'inbox.message_for_you', 'inbox.waiting')",
            name="ck_client_push_events_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'fanned_out', 'failed')", name="ck_client_push_events_status"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_client_push_events_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_client_push_events_dedupe"),
    )
    op.create_index(
        "ix_client_push_events_pending",
        "client_push_events",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON client_push_events TO nexus_app")
    op.execute("ALTER TABLE client_push_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE client_push_events FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY client_push_events_tenant_isolation ON client_push_events {_POLICY}"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_push_pending() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('nexus_push', NEW.tenant_id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_notify_push_pending
        AFTER INSERT ON client_push_events
        FOR EACH ROW
        WHEN (NEW.status = 'pending')
        EXECUTE FUNCTION notify_push_pending();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_notify_push_pending ON client_push_events")
    op.execute("DROP FUNCTION IF EXISTS notify_push_pending()")
    op.execute("DROP POLICY IF EXISTS client_push_events_tenant_isolation ON client_push_events")
    op.execute("REVOKE ALL ON client_push_events FROM nexus_app")
    op.drop_table("client_push_events")
