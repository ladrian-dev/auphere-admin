"""Nativos de caché en ``companion.runs`` (P5 / C5).

``input_tokens`` del run es la CUOTA (uncached + 0.1 x cache_read, C3).
El panel de ratio ``cache_read / (input + cache_read)`` sobre
``llm_tokens_total`` necesita los nativos; sin estas columnas el P5
miente (cache_read siempre 0 en la fila).

Nullable, igual que ``input_tokens`` / ``output_tokens``: un run
interrumpido antes de la primera llamada no tiene recuento, y un cero
ahí sería indistinguible de un turno que de verdad no cacheó.

Revision ID: 0093_companion_run_cache
Revises: 0092_companion_pilot
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0093_companion_run_cache"
down_revision: str | Sequence[str] | None = "0092_companion_pilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE companion.runs ADD COLUMN cache_read integer NULL")
    op.execute("ALTER TABLE companion.runs ADD COLUMN cache_write integer NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE companion.runs DROP COLUMN IF EXISTS cache_write")
    op.execute("ALTER TABLE companion.runs DROP COLUMN IF EXISTS cache_read")
