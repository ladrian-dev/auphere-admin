"""La vida de cada agente — spec 047, T122 (requisitos 25.1 y 26.2; ``data-model.md`` §3, §12).

``agents`` gana:

- ``lifecycle``: ``draft``, ``published``, ``paused`` o ``archived``. Se rellena con
  lo que hay: ``archived`` se queda; un agente con versión activa pasa a
  ``published`` y uno sin ella, a ``draft``. ``status`` sigue (lo leen las rutas de
  hoy) y se mantiene igual que la vida para ``archived``;
- la pausa con su motivo y su autor: ``pause_reason`` (``manual``,
  ``no_balance``, ``agent_cap``, ``client_paused``, ``client_archived``),
  ``paused_at``, ``paused_by_kind``, ``paused_by_id``, ``paused_origin`` y
  ``before_pause`` (lo que hay que devolver al reanudar);
- ``is_default``: exactamente uno por cliente entre los no archivados (índice
  único parcial). Se rellena con el agente principal de hoy: el más antiguo de
  los activos;
- ``is_reception`` (P3) y ``monthly_cap_micros`` (el tope mensual, en la moneda
  de la bolsa).

Revision ID: 0190_agent_lifecycle
Revises: 0189_agent_spec_from_prompts
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0190_agent_lifecycle"
down_revision: str | Sequence[str] | None = "0189_agent_spec_from_prompts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIVES = "'draft', 'published', 'paused', 'archived'"
REASONS = "'manual', 'no_balance', 'agent_cap', 'client_paused', 'client_archived'"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE agents
            ADD COLUMN lifecycle varchar(16) NOT NULL DEFAULT 'draft',
            ADD COLUMN pause_reason varchar(16),
            ADD COLUMN paused_at timestamptz,
            ADD COLUMN paused_by_kind varchar(16),
            ADD COLUMN paused_by_id varchar(160),
            ADD COLUMN paused_origin varchar(16),
            ADD COLUMN before_pause jsonb,
            ADD COLUMN is_default boolean NOT NULL DEFAULT false,
            ADD COLUMN is_reception boolean NOT NULL DEFAULT false,
            ADD COLUMN monthly_cap_micros bigint,
            ADD CONSTRAINT ck_agents_lifecycle CHECK (lifecycle IN ({LIVES})),
            ADD CONSTRAINT ck_agents_pause_reason CHECK (
                pause_reason IS NULL OR pause_reason IN ({REASONS})
            ),
            ADD CONSTRAINT ck_agents_paused_has_reason CHECK (
                (lifecycle = 'paused') = (pause_reason IS NOT NULL)
            ),
            ADD CONSTRAINT ck_agents_cap CHECK (monthly_cap_micros IS NULL OR monthly_cap_micros >= 0)
        """
    )
    op.execute(
        """
        UPDATE agents a SET lifecycle = CASE
            WHEN a.status = 'archived' THEN 'archived'
            WHEN EXISTS (
                SELECT 1 FROM agent_configs c
                WHERE c.tenant_id = a.tenant_id AND c.agent_id = a.id AND c.status = 'active'
            ) THEN 'published'
            ELSE 'draft'
        END
        """
    )
    op.execute(
        """
        UPDATE agents a SET is_default = true
        FROM (
            SELECT DISTINCT ON (tenant_id) id
            FROM agents WHERE status = 'active'
            ORDER BY tenant_id, created_at, id
        ) principal
        WHERE a.id = principal.id
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_agents_one_default ON agents (tenant_id) "
        "WHERE is_default AND lifecycle <> 'archived'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_agents_one_default")
    op.execute(
        """
        ALTER TABLE agents
            DROP CONSTRAINT IF EXISTS ck_agents_cap,
            DROP CONSTRAINT IF EXISTS ck_agents_paused_has_reason,
            DROP CONSTRAINT IF EXISTS ck_agents_pause_reason,
            DROP CONSTRAINT IF EXISTS ck_agents_lifecycle,
            DROP COLUMN IF EXISTS monthly_cap_micros,
            DROP COLUMN IF EXISTS is_reception,
            DROP COLUMN IF EXISTS is_default,
            DROP COLUMN IF EXISTS before_pause,
            DROP COLUMN IF EXISTS paused_origin,
            DROP COLUMN IF EXISTS paused_by_id,
            DROP COLUMN IF EXISTS paused_by_kind,
            DROP COLUMN IF EXISTS paused_at,
            DROP COLUMN IF EXISTS pause_reason,
            DROP COLUMN IF EXISTS lifecycle
        """
    )
