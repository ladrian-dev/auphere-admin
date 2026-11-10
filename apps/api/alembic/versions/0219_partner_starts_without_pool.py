"""Un partner nuevo nace sin saldo: su pool semanal empieza en 0 (owner, 2026-11-03).

El trigger ``partner_wallets_on_partner`` abre la cartera con
``NEW.weekly_pool_tokens``, así que basta con cambiar el defecto de la columna.
Los partners que ya existen conservan su pool: esto no los toca.

Revision ID: 0219_partner_starts_without_pool
Revises: 0218_test_stop_model_failed
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0219_partner_starts_without_pool"
down_revision: str | Sequence[str] | None = "0218_test_stop_model_failed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE partners ALTER COLUMN weekly_pool_tokens SET DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE partners ALTER COLUMN weekly_pool_tokens SET DEFAULT 115000")
