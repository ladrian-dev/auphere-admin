"""Modo del grader por agent_config: ``sync`` | ``sampled`` | ``off`` (WP-21).

Hoy el grader corre **en el camino crítico de todos los turnos** de los
agentes que lo tienen activo: una llamada extra al LLM por turno, y hasta
tres más si reescribe. Es la mayor partida de coste y de latencia que no
va a producir la respuesta del cliente.

La observación que justifica el cambio: la mayoría de los turnos son de
bajo riesgo (un saludo, una pregunta de horario) y su corrección *en el
momento* vale poco. Los que sí importan son los que reservan, los que
escalan a un humano y los que ejecutan una herramienta que escribe —
justo los que el runtime puede identificar sin adivinar.

``sampled`` por defecto, no ``sync``: un agente con el grader activo pasa
a graduar sincrónicamente solo los turnos de riesgo y una muestra del
resto. **Es un cambio de comportamiento en agentes ya en producción** y
es intencionado — es el objetivo del WP. El interruptor sigue siendo
``runtime_outcome_grader``: con el grader apagado, el modo no hace nada.

``grader_sample_rate`` va en ``numeric(4,3)``: tres decimales llegan
hasta el 0,1% de muestreo, que es más granularidad de la que ningún
cliente va a necesitar, y evita el error binario de un float en una
comparación que decide gasto.

Revision ID: 0074_agent_config_grader_mode
Revises: 0073_rls_billing_and_audit
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0074_agent_config_grader_mode"
down_revision: str | Sequence[str] | None = "0073_rls_billing_and_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_configs
            ADD COLUMN grader_mode text NOT NULL DEFAULT 'sampled',
            ADD COLUMN grader_sample_rate numeric(4,3) NOT NULL DEFAULT 0.100
        """
    )
    op.execute(
        """
        ALTER TABLE agent_configs
            ADD CONSTRAINT ck_agent_configs_grader_mode
                CHECK (grader_mode IN ('sync', 'sampled', 'off')),
            ADD CONSTRAINT ck_agent_configs_grader_sample_rate
                CHECK (grader_sample_rate >= 0 AND grader_sample_rate <= 1)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_configs
            DROP CONSTRAINT IF EXISTS ck_agent_configs_grader_mode,
            DROP CONSTRAINT IF EXISTS ck_agent_configs_grader_sample_rate,
            DROP COLUMN IF EXISTS grader_mode,
            DROP COLUMN IF EXISTS grader_sample_rate
        """
    )
