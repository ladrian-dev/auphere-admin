"""``usage_records`` — consumo por evento (WP-16, plataforma v2 Fase 2).

Sin esta tabla no se puede cobrar por consumo ni contener el coste: hoy
``messages.cost_usd`` guarda lo que factura **Meta** y los tokens del LLM
no se persisten en ninguna tabla de producción.

Decisiones de la tabla (las de negocio están en el modelo ORM):

- **Particionada por mes sobre ``occurred_at``**, igual que ``messages``
  (0063): es la tabla de mayor escritura de la Fase 2 y la retención
  acabará siendo un ``DROP PARTITION``. La PK incluye la clave de
  partición porque Postgres lo exige en todo índice único de una tabla
  particionada — y lo mismo obliga a que el índice de idempotencia sea
  ``(idempotency_key, occurred_at)``.
- **Partición DEFAULT** como red: un evento con fecha fuera de rango (reloj
  torcido, backfill viejo) se guarda en vez de reventar la inserción. El
  cron de mantenimiento (WP-13) crea el mes corriente y el siguiente.
- **RLS ENABLE + FORCE**. La policy usa el patrón ``NULLIF`` del resto del
  repo, no el ``current_setting(...)::uuid`` pelado del plan: con el GUC
  ausente, el cast de la cadena vacía lanza y convierte un fallo de
  aislamiento en un 500 en vez de en cero filas.
- **Sin FK a ``conversations`` ni a ``agent_configs``**: el consumo es un
  hecho contable y tiene que sobrevivir al borrado de lo que lo originó,
  incluido el borrado GDPR. La FK a ``partners`` sí existe, con SET NULL:
  hay que poder facturar el mes en el que un partner se dio de baja.

Revision ID: 0068_usage_records
Revises: 0067_outbound_pending_index
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op

revision: str = "0068_usage_records"
down_revision: str | Sequence[str] | None = "0067_outbound_pending_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _month_bounds(year: int, month: int) -> tuple[str, str, str]:
    start = datetime(year, month, 1, tzinfo=UTC)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    end = datetime(ny, nm, 1, tzinfo=UTC)
    return (
        f"usage_records_y{year:04d}m{month:02d}",
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE usage_records (
            id              uuid          NOT NULL DEFAULT gen_random_uuid(),
            tenant_id       uuid          NOT NULL,
            partner_id      uuid          NULL REFERENCES partners(id) ON DELETE SET NULL,
            occurred_at     timestamptz   NOT NULL,
            created_at      timestamptz   NOT NULL DEFAULT now(),
            meter           text          NOT NULL,
            quantity        numeric(20,6) NOT NULL,
            cost_usd        numeric(14,8) NOT NULL,
            billable_qty    numeric(20,6) NOT NULL,
            provider        text          NULL,
            model           text          NULL,
            agent_config_id uuid          NULL,
            conversation_id uuid          NULL,
            workflow_run_id uuid          NULL,
            idempotency_key text          NOT NULL,
            PRIMARY KEY (id, occurred_at)
        ) PARTITION BY RANGE (occurred_at)
        """
    )

    # Mes corriente + siguiente, para no depender de que el cron de
    # mantenimiento haya corrido antes del primer evento.
    bind = op.get_bind()
    now = bind.exec_driver_sql("SELECT now()").scalar_one()
    year, month = now.year, now.month
    for _ in range(2):
        name, start, end = _month_bounds(year, month)
        op.execute(
            f"CREATE TABLE {name} PARTITION OF usage_records "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    op.execute("CREATE TABLE usage_records_default PARTITION OF usage_records DEFAULT")

    op.execute(
        "CREATE UNIQUE INDEX uq_usage_idem ON usage_records (idempotency_key, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_usage_tenant_meter ON usage_records "
        "(tenant_id, meter, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_usage_partner ON usage_records (partner_id, occurred_at DESC) "
        "WHERE partner_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_usage_agent_cfg ON usage_records (agent_config_id, occurred_at DESC)"
    )

    op.execute("ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_records FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY usage_records_tenant_isolation ON usage_records
        USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON usage_records TO nexus_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_records")
