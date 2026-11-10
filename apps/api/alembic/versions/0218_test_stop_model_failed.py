"""Una pasada también termina porque un modelo no respondió.

``stop = model_failed``: la pasada no dice nada del agente (bug
``el-probador-tapa-los-fallos-del-modelo``). Sin ese valor, el ``CHECK`` de la 0206
rechaza la fila.

Revision ID: 0218_test_stop_model_failed
Revises: 0217_owner_invitation_sent_at
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0218_test_stop_model_failed"
down_revision: str | Sequence[str] | None = "0217_owner_invitation_sent_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = ("plan_done", "goodbye", "handoff", "turn_limit")
AFTER = (*BEFORE, "model_failed")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _stop_is_one_of(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE agent_test_results DROP CONSTRAINT ck_agent_test_results_stop")
    op.execute(
        "ALTER TABLE agent_test_results ADD CONSTRAINT ck_agent_test_results_stop "
        f"CHECK (stop IS NULL OR stop IN ({_in(values)}))"
    )


def upgrade() -> None:
    _stop_is_one_of(AFTER)


def downgrade() -> None:
    op.execute("UPDATE agent_test_results SET stop = NULL WHERE stop = 'model_failed'")
    _stop_is_one_of(BEFORE)
