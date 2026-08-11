"""``usage_records.cost_usd`` pasa a NULL-able: NULL = contado, sin precio.

WP-18 (el consumidor) tiene que insertar antes de que exista WP-19
(`model_profiles`), que es de donde saldrá el precio. Con la columna NOT
NULL las únicas salidas eran malas:

- insertar ``0`` → filas que dicen "esto no costó nada", indistinguibles
  de las que de verdad no cuestan nada. Nadie sabría después qué
  reprecificar, y un panel de margen sumaría ceros creyéndolos datos.
- bloquear la inserción hasta WP-19 → se pierden las cantidades de todo
  ese periodo, que es justo lo que veníamos a dejar de perder.

``NULL`` dice exactamente lo que pasa: la cantidad está medida, el precio
todavía no. ``SUM(cost_usd)`` ignora los NULL sin trampas, y
``WHERE cost_usd IS NULL`` es la consulta de backfill de WP-19.

``billable_qty`` se queda NOT NULL: el consumidor la rellena con la
cantidad medida, que es la identidad correcta mientras no exista política
de precios.

Revision ID: 0071_usage_cost_nullable
Revises: 0070_messages_conversation_fk
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0071_usage_cost_nullable"
down_revision: str | Sequence[str] | None = "0070_messages_conversation_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE usage_records ALTER COLUMN cost_usd DROP NOT NULL")


def downgrade() -> None:
    # Volver a NOT NULL exige un valor para las filas sin precio; 0 es el
    # único disponible y es precisamente lo que esta migración evita, así
    # que el downgrade lo hace explícito en vez de a escondidas.
    op.execute("UPDATE usage_records SET cost_usd = 0 WHERE cost_usd IS NULL")
    op.execute("ALTER TABLE usage_records ALTER COLUMN cost_usd SET NOT NULL")
