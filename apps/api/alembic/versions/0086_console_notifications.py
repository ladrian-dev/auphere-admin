"""Notificaciones in-app del partner y marca de activación (CP-29, CP-24).

PLAN-CONSOLE-V1. La consola necesita un centro de notificaciones (CP-29) y
las alertas de consumo (CP-24) necesitan un sitio donde caer además del
correo. Una sola tabla de PLATAFORMA sirve a las dos: una notificación es
del partner (``partner_id``), opcionalmente dirigida a un usuario concreto
(``recipient_user_id`` = id de Better Auth en texto; NULL = todos los
miembros) y opcionalmente referida a un cliente por
``external_client_ref`` — el identificador que el partner ya conoce; NO
se guarda ``tenant_id`` interno (la tabla es de partner, no de tenant:
sin RLS por tenant ni FK a ``tenants``, ver ``test_21``/``test_22``).

- ``kind`` es un vocabulario cerrado en código (``db/models/console_notification.py``)
  y la UI lo traduce con ``payload``: aquí no se guarda texto en ningún
  idioma. Nada de cuerpos de mensaje de clientes finales (C8).
- ``dedupe_key`` único (nullable) evita repetir la misma alerta
  ("partner:X:usage:80:2026-08").
- ``read_at`` por notificación; con ``recipient_user_id`` NULL la lectura
  se guarda por usuario en ``console_notification_reads``.

Además ``partners.activated_at``: instante del primer cliente activo con
agente publicado — la métrica de activación de CP-29 (tiempo hasta el
primer cliente activo).

Revision ID: 0086_console_notifications
Revises: 0085_knowledge_documents
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0086_console_notifications"
down_revision: str | Sequence[str] | None = "0085_knowledge_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE console_notifications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
            recipient_user_id varchar(64) NULL,
            external_client_ref varchar(255) NULL,
            kind varchar(60) NOT NULL,
            severity varchar(10) NOT NULL DEFAULT 'info'
                CHECK (severity IN ('info', 'warning', 'critical')),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            dedupe_key varchar(200) NULL,
            read_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_console_notifications_dedupe "
        "ON console_notifications (dedupe_key) WHERE dedupe_key IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_console_notifications_partner_created "
        "ON console_notifications (partner_id, created_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE console_notification_reads (
            notification_id uuid NOT NULL
                REFERENCES console_notifications(id) ON DELETE CASCADE,
            user_id varchar(64) NOT NULL,
            read_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (notification_id, user_id)
        )
        """
    )
    op.execute("ALTER TABLE partners ADD COLUMN activated_at timestamptz NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE partners DROP COLUMN activated_at")
    op.execute("DROP TABLE console_notification_reads")
    op.execute("DROP TABLE console_notifications")
