"""Consumo por partidas: lo que el rol de informes necesita leer — spec 047, T158
(requisito 46; research D30).

- ``usage_records.agent_id`` y ``usage_records.line``: el detalle técnico y el CSV
  van por agente y por partida (46.6).
- ``daily_cost_snapshots`` no se abre al rol de informes: una política más sobre
  una tabla de cliente la abriría por otro lado (garantía 1). La partida «Mensajes
  de Meta» la lee cliente a cliente, con su RLS.
- ``client_wallet_entries.seq``: el orden de los asientos de una bolsa. Los de una
  misma transacción comparten ``created_at`` y el cuadre diario necesita el último.

Revision ID: 0196_usage_lines_reporting
Revises: 0195_client_wallets
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0196_usage_lines_reporting"
down_revision: str | Sequence[str] | None = "0195_client_wallets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE = "nexus_reporting"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE client_wallet_entries "
        "ADD COLUMN seq bigint GENERATED ALWAYS AS IDENTITY NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_client_wallet_entries_tenant_seq "
        "ON client_wallet_entries (tenant_id, seq DESC)"
    )
    op.execute(f"GRANT SELECT (agent_id, line) ON usage_records TO {ROLE}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_client_wallet_entries_tenant_seq")
    op.execute("ALTER TABLE client_wallet_entries DROP COLUMN IF EXISTS seq")
    op.execute(f"REVOKE SELECT (agent_id, line) ON usage_records FROM {ROLE}")
