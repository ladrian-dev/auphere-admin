"""Tope de gasto del playground por partner y mes — ``qa_monthly_token_cap``,
``qa_cap_notes``.

PLAN-CONSOLE-V1, CP-16. El playground de la consola quema tokens LLM
reales (con ``usage_records.source='qa'`` desde 0079, fuera de la factura
del cliente) y hasta ahora sin techo: un partner con un bucle de pruebas
podía gastar sin límite a cuenta de Auphere.

- ``qa_monthly_token_cap``: tokens LLM (entrada + salida) que el
  playground del partner puede consumir por mes natural UTC, sumando todos
  sus clientes y todos sus miembros. **En tokens, no en USD** (decisión C9):
  es la misma unidad que el partner ve en la página de consumo; el coste
  en dólares es de Auphere y no se enseña. Se comprueba ANTES de arrancar
  cada turno; alcanzado el tope el playground responde 429 con
  ``Retry-After`` hasta el día 1 del mes siguiente. La fuente de la suma es
  ``qa.runs`` (input_tokens + output_tokens, cerrados por la propia API al
  terminar cada turno), no ``usage_records``: es síncrona con el turno y no
  depende del consumidor del stream de metering.
- ``qa_cap_notes``: texto libre para el operador ("subido a 5M el
  2026-09-01, piloto X"). No se enseña al partner.

Default 2.000.000 tokens/mes: ~1.000 turnos de prueba con Sonnet, holgado
para un piloto y acotado como pérdida.

Revision ID: 0082_qa_budget_cap
Revises: 0081_partner_provisioning_quota
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0082_qa_budget_cap"
down_revision: str | Sequence[str] | None = "0081_partner_provisioning_quota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_QA_MONTHLY_TOKEN_CAP = 2_000_000


def upgrade() -> None:
    op.execute(
        "ALTER TABLE partners "
        "ADD COLUMN qa_monthly_token_cap bigint NOT NULL "
        f"DEFAULT {DEFAULT_QA_MONTHLY_TOKEN_CAP}, "
        "ADD COLUMN qa_cap_notes text NULL"
    )
    op.execute(
        "ALTER TABLE partners ADD CONSTRAINT ck_partners_qa_monthly_token_cap "
        "CHECK (qa_monthly_token_cap >= 0)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_qa_monthly_token_cap")
    op.execute(
        "ALTER TABLE partners "
        "DROP COLUMN IF EXISTS qa_cap_notes, "
        "DROP COLUMN IF EXISTS qa_monthly_token_cap"
    )
