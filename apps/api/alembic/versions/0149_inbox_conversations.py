"""La conversación que pinta la Bandeja — spec 030, iteración 2 (plan D11 a D13).

Tres cosas sobre ``conversations`` y una tabla nueva:

* ``assigned_user_id`` — la persona del cliente que responde cuando el agente
  está en pausa (``agent_active = false``). Cuenta de consola, por valor.
* ``closed_at`` — «resuelta» es ``status = CLOSED``; hasta hoy nadie escribía
  ``CLOSED``. Si el contacto vuelve a escribir, la fila se reabre (D11).
* ``last_message_at`` — última actividad en cualquier sentido, con su índice:
  la Bandeja ordena por esto y tiene que contestar en < 1,5 s con 5.000
  conversaciones (CE-007). Se rellena con el último mensaje de cada fila.

``conversation_events`` guarda lo que le pasó a la conversación (pidió ayuda,
control tomado, devuelta, resuelta, reabierta) con quién. El motivo y el
resumen del escalado viven aquí y no solo en ``audit_log``: la Bandeja los
enseña. **Nunca texto de mensajes.**

``messages.actor_kind`` = ``member`` es la persona del cliente que escribe
desde la Bandeja. No hace falta tocar el esquema para eso: el ``CHECK`` que
puso 0041 no sobrevivió a la tabla particionada (0063) y la columna ya no
tiene restricción. Volver a ponerla sobre una tabla particionada grande es
otra migración, con su propia prueba de carga, y no entra aquí.

Revision ID: 0149_inbox_conversations
Revises: 0148_client_audience_vocab
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0149_inbox_conversations"
down_revision: str | Sequence[str] | None = "0148_client_audience_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
_EVENT_KINDS = "('escalated', 'takeover', 'released', 'resolved', 'reopened', 'agent_changed')"


def upgrade() -> None:
    op.add_column("conversations", sa.Column("assigned_user_id", sa.String(64), nullable=True))
    op.add_column(
        "conversations", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "conversations", sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        """
        UPDATE conversations c
           SET last_message_at = sub.m
          FROM (SELECT conversation_id, max(created_at) AS m
                  FROM messages GROUP BY conversation_id) sub
         WHERE c.id = sub.conversation_id
        """
    )
    op.execute(
        "UPDATE conversations SET last_message_at = COALESCE(last_inbound_at, updated_at) "
        "WHERE last_message_at IS NULL"
    )
    op.create_index(
        "ix_conversations_tenant_last_message",
        "conversations",
        ["tenant_id", sa.text("last_message_at DESC"), "id"],
    )

    op.create_table(
        "conversation_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(320), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(f"kind IN {_EVENT_KINDS}", name="ck_conversation_events_kind"),
    )
    op.create_index(
        "ix_conversation_events_conversation",
        "conversation_events",
        ["conversation_id", sa.text("created_at DESC")],
    )
    op.execute("ALTER TABLE conversation_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversation_events FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY conversation_events_tenant_isolation ON conversation_events {_POLICY}"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS conversation_events_tenant_isolation ON conversation_events")
    op.drop_table("conversation_events")
    op.drop_index("ix_conversations_tenant_last_message", table_name="conversations")
    op.drop_column("conversations", "last_message_at")
    op.drop_column("conversations", "closed_at")
    op.drop_column("conversations", "assigned_user_id")
