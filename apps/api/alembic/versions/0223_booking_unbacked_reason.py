"""Un motivo de espera más: el agente dio por hecha una cita que no existe — spec 056, T002 (requisito 1.2).

El freno de citas (``nexus_worker.runtime.booking_brake``) comprueba que la
respuesta que afirma una reserva tiene una reserva real detrás. Si el segundo
intento vuelve a afirmarla sin respaldo, la conversación pasa a una persona con
``waiting_reason = 'booking_unbacked'``. Esta migración rehace
``ck_conversations_waiting_reason`` (0176) con ese código.

No es un motivo de puerta (``inbox_lifecycle.GATE_REASONS``): la siguiente
respuesta del agente no lo libera, como ``escalated``.

La bajada devuelve esas conversaciones como ``escalated``, que es lo más
parecido (el agente pidió ayuda) y tampoco se libera solo.

Revision ID: 0223_booking_unbacked_reason
Revises: 0222_merge_0220_heads
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0223_booking_unbacked_reason"
down_revision: str | Sequence[str] | None = "0222_merge_0220_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: La lista de la 0176, tal cual.
WAITING_REASONS_BEFORE: tuple[str, ...] = (
    "no_balance",
    "agent_cap",
    "paused_agent",
    "paused_channel",
    "paused_client",
    "archived_client",
    "channel_problem",
    "agent_unpublished",
    "out_of_audience",
    "no_model",
    "provider_failure",
    "turn_limit",
    "escalated",
    "human_takeover",
    "reception_loop",
)
WAITING_REASONS_AFTER: tuple[str, ...] = (*WAITING_REASONS_BEFORE, "booking_unbacked")

_CHECK = "ck_conversations_waiting_reason"


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _check(values: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE conversations DROP CONSTRAINT IF EXISTS {_CHECK}")
    # NOT VALID + VALIDATE: la comprobación de las filas que ya hay no bloquea
    # las escrituras de los entrantes mientras corre.
    op.execute(
        f"ALTER TABLE conversations ADD CONSTRAINT {_CHECK} "
        f"CHECK (waiting_reason IS NULL OR waiting_reason IN ({_in(values)})) NOT VALID"
    )
    op.execute(f"ALTER TABLE conversations VALIDATE CONSTRAINT {_CHECK}")


def upgrade() -> None:
    _check(WAITING_REASONS_AFTER)


def downgrade() -> None:
    op.execute(
        "UPDATE conversations SET waiting_reason = 'escalated' "
        "WHERE waiting_reason = 'booking_unbacked'"
    )
    _check(WAITING_REASONS_BEFORE)
