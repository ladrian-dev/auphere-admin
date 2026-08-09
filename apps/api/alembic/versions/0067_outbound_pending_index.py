"""Índice parcial de salientes pendientes (WP-24, plataforma v2).

El dispatcher de egress hace dos consultas contra ``messages`` que hasta
ahora no tenían índice y que, sobre una tabla PARTICIONADA con millones de
filas, se resolvían con seq scan de TODAS las particiones:

1. el drain por tenant — ``WHERE direction='outbound' AND status='pending'``
   (más el ``tenant_id`` que impone la RLS) ordenado por ``created_at``,
   una vez por tenant notificado y por cada tenant activo en el sweep de
   30 s;
2. el gauge ``outbound_pending_messages`` que estrena esta rama, que es
   el count global del que autoescala el servicio egress (WP-24).

Un índice PARCIAL los sirve a los dos y es diminuto: solo contiene lo que
está pendiente de enviar, que en régimen normal son unidades, no millones
— el resto de la tabla (delivered/read/failed) no entra. El orden
``(tenant_id, created_at)`` da el prefijo del drain y deja el count/min
global como recorrido completo de un índice que cabe en un par de páginas.

Se crea sobre el padre particionado, así que Postgres lo propaga a cada
partición existente y a las que cree ``ensure_month_partition()`` (0064)
en el futuro. NO puede ser CONCURRENTLY: Postgres no lo admite sobre una
tabla particionada. Con el volumen actual (200k filas en staging, menos en
prod) el bloqueo es de menos de un segundo; si algún día deja de serlo, la
alternativa es crearlo partición a partición con CONCURRENTLY y luego
``ATTACH PARTITION`` al índice del padre.

Revision ID: 0067_outbound_pending_index
Revises: 0066_checkpoint_rls
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0067_outbound_pending_index"
down_revision: str | Sequence[str] | None = "0066_checkpoint_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_messages_outbound_pending"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {INDEX_NAME}
        ON messages (tenant_id, created_at)
        WHERE status = 'pending' AND direction = 'outbound'
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
