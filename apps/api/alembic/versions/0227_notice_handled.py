"""El aviso «Espera a una persona» se da por atendido — spec 056, T006 (requisitos 8.1 y 8.2).

``console_notifications.handled_at``: cuando alguien toma la conversación, la
devuelve al agente, la resuelve o la elimina, o cuando se libera su motivo, su
aviso ``inbox.waiting`` pasa a atendido. Deja de contar en el número de la
campana y sigue en la lista. Un escalado nuevo de la misma conversación crea un
aviso nuevo, pendiente.

El índice parcial ``((payload->>'conversation_id')) WHERE kind = 'inbox.waiting'
AND handled_at IS NULL`` encuentra los avisos pendientes de una conversación sin
recorrer los de todo el partner. El ``UPDATE`` filtra además por el partner y por
el cliente (``external_client_ref``).

La bajada quita el índice y la columna.

Revision ID: 0227_notice_handled
Revises: 0226_correction_batches
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0227_notice_handled"
down_revision: str | Sequence[str] | None = "0226_correction_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_console_notifications_waiting_pending"


def upgrade() -> None:
    op.execute("ALTER TABLE console_notifications ADD COLUMN handled_at timestamptz")
    op.execute(
        f"CREATE INDEX {_INDEX} ON console_notifications ((payload->>'conversation_id')) "
        "WHERE kind = 'inbox.waiting' AND handled_at IS NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
    op.execute("ALTER TABLE console_notifications DROP COLUMN IF EXISTS handled_at")
