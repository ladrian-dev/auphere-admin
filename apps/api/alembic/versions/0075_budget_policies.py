"""``budget_policies`` — presupuesto, degradación y corte (WP-20).

Hoy existe ``daily_cost_snapshots`` y su alerta, pero **no existe el
corte**: un tenant que se dispara genera un aviso por WhatsApp y sigue
gastando. La alerta llega cuando el dinero ya se fue.

Dos niveles obligatorios, ``tenant`` y ``partner``, y no es simetría
decorativa: en el canal de partners Auphere factura al PARTNER, así que
el saldo que de verdad corta es el suyo agregado sobre todos sus
clientes. Con solo el nivel de tenant, veinte clientes de un partner por
debajo de su límite individual pueden hundir el margen del partner sin
que ninguno active nada.

De ahí ``scope`` + ``scope_id`` en vez de ``tenant_id``: la fila puede
apuntar a un tenant o a un partner. No lleva RLS porque no es dato de un
tenant sino configuración de plataforma, y porque una policy por
``tenant_id`` ni siquiera podría expresar la fila del partner — el mismo
motivo por el que ``model_profiles`` tampoco la lleva.

``soft_action`` sale del catálogo de WP-19: ``downgrade`` pasa al modelo
más barato disponible, ``grader_off`` apaga el grader (WP-21), ``both``
las dos. Son exactamente las dos palancas de coste que existen sin
degradar lo que el cliente final percibe.

Revision ID: 0075_budget_policies
Revises: 0074_agent_config_grader_mode
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0075_budget_policies"
down_revision: str | Sequence[str] | None = "0074_agent_config_grader_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE budget_policies (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scope text NOT NULL,
            scope_id uuid NOT NULL,
            meter text NOT NULL,
            period text NOT NULL,
            soft_limit numeric(14,4) NOT NULL,
            hard_limit numeric(14,4) NOT NULL,
            soft_action text NOT NULL DEFAULT 'downgrade',
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_budget_scope CHECK (scope IN ('tenant', 'partner')),
            CONSTRAINT ck_budget_period CHECK (period IN ('day', 'month')),
            CONSTRAINT ck_budget_soft_action
                CHECK (soft_action IN ('downgrade', 'grader_off', 'both')),
            -- El blando por encima del duro dejaría la degradación
            -- inalcanzable: se cortaría en seco sin haber intentado
            -- antes la vía barata.
            CONSTRAINT ck_budget_limits CHECK (soft_limit <= hard_limit),
            CONSTRAINT uq_budget_scope_meter_period UNIQUE (scope, scope_id, meter, period)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS budget_policies")
