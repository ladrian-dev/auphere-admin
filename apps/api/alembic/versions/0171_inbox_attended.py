"""La Bandeja solo enseña lo que el agente atiende o atendió — spec 045.

Dos columnas en ``conversations``:

- ``attended_at``: el primer mensaje del contacto que el agente pudo atender
  (uno que la puerta de números permitidos de la spec 024 no silenció, en un
  número con agente). ``NULL`` = la conversación no existe para la Bandeja.
- ``last_attended_inbound_at``: el último. Contra él se mide el «sin leer»;
  ``last_inbound_at`` sigue siendo la ventana de 24 h de WhatsApp.

El relleno sale de los mensajes: entrantes con ``skipped_reason IS NULL`` en
un número que no es solo de envío. Solo escribe donde difiere: repetirlo no
cambia nada.

Y en ``client_phones``, ``quiet_outside_hours`` (R5): silenciar fuera del
horario del negocio los avisos que no son urgentes, encendido por defecto. La
entrega silenciada queda ``skipped`` con ``quiet_hours``, que entra en el CHECK
de ``client_push_deliveries``.

Revision ID: 0171_inbox_attended
Revises: 0170_canonical_business_hours
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0171_inbox_attended"
down_revision: str | Sequence[str] | None = "0170_canonical_business_hours"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SKIP_BEFORE = (
    "'module_missing', 'no_longer_true', 'no_push_token', 'kind_disabled', "
    "'phone_revoked', 'token_owned_elsewhere'"
)
_SKIP_AFTER = _SKIP_BEFORE + ", 'quiet_hours'"

BACKFILL = sa.text(
    """
    UPDATE conversations AS c
       SET attended_at = m.first_at,
           last_attended_inbound_at = m.last_at
      FROM (
            SELECT msg.conversation_id,
                   MIN(msg.created_at) AS first_at,
                   MAX(msg.created_at) AS last_at
              FROM messages AS msg
              JOIN conversations AS c2 ON c2.id = msg.conversation_id
              JOIN channels AS ch ON ch.id = c2.channel_id
             WHERE msg.direction = 'inbound'
               AND msg.skipped_reason IS NULL
               AND COALESCE(ch.config ->> 'agent_enabled', 'true') <> 'false'
             GROUP BY msg.conversation_id
           ) AS m
     WHERE m.conversation_id = c.id
       AND (c.attended_at IS DISTINCT FROM m.first_at
            OR c.last_attended_inbound_at IS DISTINCT FROM m.last_at)
    """
)


def upgrade() -> None:
    op.add_column(
        "conversations", sa.Column("attended_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("last_attended_inbound_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(BACKFILL)
    op.execute(
        "CREATE INDEX ix_conversations_attended "
        "ON conversations (tenant_id, last_message_at DESC) "
        "WHERE attended_at IS NOT NULL"
    )
    op.add_column(
        "client_phones",
        sa.Column(
            "quiet_outside_hours", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )
    _skip_check(_SKIP_AFTER)


def _skip_check(values: str) -> None:
    op.drop_constraint(
        "ck_client_push_deliveries_skip_reason", "client_push_deliveries", type_="check"
    )
    op.create_check_constraint(
        "ck_client_push_deliveries_skip_reason",
        "client_push_deliveries",
        f"skip_reason IS NULL OR skip_reason IN ({values})",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE client_push_deliveries SET skip_reason = 'kind_disabled' "
        "WHERE skip_reason = 'quiet_hours'"
    )
    _skip_check(_SKIP_BEFORE)
    op.drop_column("client_phones", "quiet_outside_hours")
    op.execute("DROP INDEX IF EXISTS ix_conversations_attended")
    op.drop_column("conversations", "last_attended_inbound_at")
    op.drop_column("conversations", "attended_at")
