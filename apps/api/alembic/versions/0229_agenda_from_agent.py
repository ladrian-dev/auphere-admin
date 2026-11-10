"""Spec 057: la agenda desde el agente — dos restricciones que admiten un valor más.

1. ``jobs.kind`` admite ``agenda_text`` (requisito 3.6). Al encender o apagar
   «Gestiona citas» en un agente ya creado, el constructor propone en un trabajo aparte
   cómo cambian sus procedimientos, reglas, escalado, habilidades y lo que sabe de
   citas. Corre en el worker, como ``agent_draft``, y se mide como construcción.
2. ``conversations.waiting_reason`` admite ``agenda_not_ready`` (requisito 4.2). Con la
   agenda sin terminar, un agente sin herramienta de derivar no puede pasar la cita a
   una persona: lo hace el runtime, por el camino del freno de citas, con este motivo.
   No es un motivo de puerta (``inbox_lifecycle.GATE_REASONS``): la siguiente respuesta
   del agente no lo libera, como ``booking_unbacked``.

La bajada borra los trabajos ``agenda_text`` y devuelve esas conversaciones como
``escalated``, que es lo más parecido y tampoco se libera solo.

Revision ID: 0229_agenda_from_agent
Revises: 0228_staff_calendar_connections
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0229_agenda_from_agent"
down_revision: str | Sequence[str] | None = "0228_staff_calendar_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Los tipos de antes, congelados: la migración no lee el modelo, que seguirá cambiando.
JOB_KINDS_BEFORE: tuple[str, ...] = (
    "client_read",
    "client_builder",
    "agent_draft",
    "tests",
    "publish",
    "fix",
    "copilot",
    "quality_check",
    "suggestions",
    "sector_identify",
)
JOB_KINDS: tuple[str, ...] = (*JOB_KINDS_BEFORE, "agenda_text")

#: La lista de la 0223, tal cual.
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
    "booking_unbacked",
)
WAITING_REASONS: tuple[str, ...] = (*WAITING_REASONS_BEFORE, "agenda_not_ready")

_WAITING_CHECK = "ck_conversations_waiting_reason"


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


#: Lo que espera un ``ALTER`` por su candado: con una transacción larga abierta sobre la
#: tabla, mejor fallar el despliegue que dejar en cola a los mensajes entrantes detrás.
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s'"


def _jobs(values: Sequence[str]) -> None:
    op.execute("ALTER TABLE jobs DROP CONSTRAINT ck_jobs_kind")
    op.execute(
        f"ALTER TABLE jobs ADD CONSTRAINT ck_jobs_kind CHECK (kind IN ({_in(values)})) NOT VALID"
    )


def _waiting(values: Sequence[str]) -> None:
    op.execute(f"ALTER TABLE conversations DROP CONSTRAINT IF EXISTS {_WAITING_CHECK}")
    op.execute(
        f"ALTER TABLE conversations ADD CONSTRAINT {_WAITING_CHECK} "
        f"CHECK (waiting_reason IS NULL OR waiting_reason IN ({_in(values)})) NOT VALID"
    )


def _validate() -> None:
    """``env.py`` corre todas las migraciones en una transacción: un ``VALIDATE`` dentro de
    ella mantiene el candado del ``ADD CONSTRAINT`` hasta el final. Fuera de ella, la
    comprobación de las filas que ya hay no bloquea las escrituras (revisión de seguridad
    de la 057; la 0223 tenía el mismo hueco)."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TABLE jobs VALIDATE CONSTRAINT ck_jobs_kind")
        op.execute(f"ALTER TABLE conversations VALIDATE CONSTRAINT {_WAITING_CHECK}")


def upgrade() -> None:
    op.execute(LOCK_TIMEOUT)
    _jobs(JOB_KINDS)
    _waiting(WAITING_REASONS)
    _validate()


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "SET LOCAL row_security = off; "
        "DELETE FROM jobs WHERE kind = 'agenda_text'; "
        "UPDATE conversations SET waiting_reason = 'escalated' "
        "WHERE waiting_reason = 'agenda_not_ready'; "
        "END $$"
    )
    op.execute(LOCK_TIMEOUT)
    _waiting(WAITING_REASONS_BEFORE)
    _jobs(JOB_KINDS_BEFORE)
    _validate()
