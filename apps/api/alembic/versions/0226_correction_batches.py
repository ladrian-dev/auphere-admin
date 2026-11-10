"""Las correcciones de «Todo el negocio» van en lote — spec 056, T005 (requisito 9.1).

Con «Todo el negocio», una corrección de comportamiento se propone a cada agente
activo del cliente, no solo al que respondió. La que envió la persona del
cliente es la cabeza del lote (``batch_id = id``); sus hermanas, una por cada
otro agente ``published`` o ``paused``, llevan el ``batch_id`` de la cabeza. El
lote no tiene estado propio: aceptarlo o descartarlo cambia cada fila.

- ``inbox_corrections.batch_id uuid NULL``.
- FK **compuesta** ``(tenant_id, batch_id) → inbox_corrections (tenant_id, id)``
  sobre ``uq_inbox_corrections_tenant_id`` (0198): la comprobación de una FK no
  pasa por la RLS, y una de una columna dejaría colgar una corrección del lote
  de otro cliente. ``ON DELETE SET NULL (batch_id)``: si se borra la cabeza (su
  conversación o su agente desaparecen), las hermanas se quedan, sin lote.
- Índice ``(tenant_id, batch_id) WHERE batch_id IS NOT NULL``: las hermanas de
  un lote, sin recorrer las correcciones sueltas.

La bajada quita la columna con su FK y su índice.

Revision ID: 0226_correction_batches
Revises: 0225_client_access_audit_actor
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0226_correction_batches"
down_revision: str | Sequence[str] | None = "0225_client_access_audit_actor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "inbox_corrections"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN batch_id uuid")
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT fk_{_TABLE}_batch "
        f"FOREIGN KEY (tenant_id, batch_id) REFERENCES {_TABLE} (tenant_id, id) "
        "ON DELETE SET NULL (batch_id)"
    )
    op.execute(
        f"CREATE INDEX ix_{_TABLE}_batch ON {_TABLE} (tenant_id, batch_id) "
        "WHERE batch_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS ix_{_TABLE}_batch")
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS fk_{_TABLE}_batch")
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS batch_id")
