"""``usage_records.source`` — separa el consumo del cliente del de las pruebas.

Un turno del QA Playground gasta tokens de Anthropic reales y **no dejaba
ninguna fila** en ``usage_records``: el contexto ``usage_turn`` se abría
sólo en el camino de canal (``dispatcher.py``) y el Playground ejecuta el
pipeline en proceso dentro de la API. ``record_usage`` es no-op fuera de
turno a propósito, así que fallaba en silencio. El emisor de esta tanda lo
cierra; esta migración decide **dónde cae ese gasto**.

Medirlo sin distinguirlo sería cambiar un agujero por una mentira: las
pruebas del operador entrarían en el panel de margen como tráfico
facturable e inflarían el coste del cliente. Y un cliente con un agente en
revisión activa es justo el que más pruebas recibe, así que el error no
sería ni pequeño ni aleatorio — castigaría a los tenants más atendidos.

Se elige **una columna y no una tabla aparte**: la idempotencia, la
partición, la RLS, el precio y el DLQ ya están resueltos aquí, y duplicar
esa maquinaria para el consumo interno la haría divergir a la primera
corrección. El coste del QA es consumo con la misma forma; lo que cambia
es quién lo paga.

``DEFAULT 'channel'`` + ``NOT NULL``: en Postgres 11+ un default no
volátil no reescribe la tabla, así que el ``ADD COLUMN`` sobre la
particionada es metadata en el padre y en cada partición. Las filas que ya
existen son, todas, tráfico de canal — el QA no había escrito ninguna —,
así que el default retroactivo dice la verdad y no hace falta backfill.

El CHECK va **con nombre y validado**: el conjunto de orígenes es cerrado
por diseño (un origen inventado sobre la marcha es una categoría de
facturación fantasma, el mismo criterio que ``USAGE_METERS``). Se valida
en el momento porque la tabla es joven; si algún día pesa, el patrón es
``NOT VALID`` + ``VALIDATE CONSTRAINT``.

La vista ``reporting_tenant_cost_monthly`` (0078) se recrea con ``source``
en el corte. **Desglosa, no filtra**: filtrar dentro de la vista volvería
a hacer invisible el gasto de QA, que es el problema que veníamos a
resolver — hoy no es que no se facture, es que no se registra en ninguna
parte. Quien quiera el coste del cliente pone ``source = 'channel'`` en la
consulta; el panel de margen ya lo hace.

Revision ID: 0079_usage_source
Revises: 0078_reporting_role
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0079_usage_source"
down_revision: str | Sequence[str] | None = "0078_reporting_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE = "nexus_reporting"


def upgrade() -> None:
    op.execute("ALTER TABLE usage_records ADD COLUMN source text NOT NULL DEFAULT 'channel'")
    op.execute(
        "ALTER TABLE usage_records ADD CONSTRAINT ck_usage_source "
        "CHECK (source IN ('channel', 'qa'))"
    )

    # El panel necesita leer la columna por la que corta. Sin esto la vista
    # (``security_invoker``) devolvería un error de permisos al rol de
    # reporting, no una lista incompleta.
    op.execute(f"GRANT SELECT (source) ON usage_records TO {ROLE}")

    op.execute("DROP VIEW IF EXISTS reporting_tenant_cost_monthly")
    op.execute(
        """
        CREATE VIEW reporting_tenant_cost_monthly
        WITH (security_invoker = true) AS
        SELECT u.tenant_id,
               t.name                                   AS tenant_name,
               t.plan,
               t.tier,
               u.partner_id,
               u.agent_config_id,
               ac.version                               AS agent_version,
               date_trunc('month', u.occurred_at)       AS month,
               u.meter,
               u.provider,
               u.model,
               u.source,
               sum(u.cost_usd)                          AS cost_usd_total,
               sum(u.billable_qty)                      AS billable_qty_total,
               count(*)                                 AS records,
               count(*) FILTER (WHERE u.cost_usd IS NULL) AS unpriced_records
          FROM usage_records u
          LEFT JOIN tenants t       ON t.id = u.tenant_id
          LEFT JOIN agent_configs ac ON ac.id = u.agent_config_id
         GROUP BY u.tenant_id, t.name, t.plan, t.tier, u.partner_id,
                  u.agent_config_id, ac.version,
                  date_trunc('month', u.occurred_at),
                  u.meter, u.provider, u.model, u.source
        """
    )
    op.execute(f"GRANT SELECT ON reporting_tenant_cost_monthly TO {ROLE}")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting_tenant_cost_monthly")
    op.execute(
        """
        CREATE VIEW reporting_tenant_cost_monthly
        WITH (security_invoker = true) AS
        SELECT u.tenant_id,
               t.name                                   AS tenant_name,
               t.plan,
               t.tier,
               u.partner_id,
               u.agent_config_id,
               ac.version                               AS agent_version,
               date_trunc('month', u.occurred_at)       AS month,
               u.meter,
               u.provider,
               u.model,
               sum(u.cost_usd)                          AS cost_usd_total,
               sum(u.billable_qty)                      AS billable_qty_total,
               count(*)                                 AS records,
               count(*) FILTER (WHERE u.cost_usd IS NULL) AS unpriced_records
          FROM usage_records u
          LEFT JOIN tenants t       ON t.id = u.tenant_id
          LEFT JOIN agent_configs ac ON ac.id = u.agent_config_id
         GROUP BY u.tenant_id, t.name, t.plan, t.tier, u.partner_id,
                  u.agent_config_id, ac.version,
                  date_trunc('month', u.occurred_at),
                  u.meter, u.provider, u.model
        """
    )
    op.execute(f"GRANT SELECT ON reporting_tenant_cost_monthly TO {ROLE}")

    # Las filas de QA se quedan: son consumo que ocurrió. Al perder la
    # columna dejan de ser distinguibles del tráfico de canal, que es
    # exactamente el estado anterior a esta migración y el motivo por el
    # que existe.
    op.execute("ALTER TABLE usage_records DROP CONSTRAINT IF EXISTS ck_usage_source")
    op.execute("ALTER TABLE usage_records DROP COLUMN IF EXISTS source")
