"""El piloto del Companion: pausa, tickets de soporte y bandera (CO-08).

Cuatro cambios pequeños y una ausencia que conviene dejar escrita.

1. **``companion.runs.status`` admite ``'paused'``.** El tope mensual deja
   de matar el turno y pasa a pausarlo (§6 de ``CONTRACT-V2.md``, §23.2 de
   la investigación). Un run pausado conserva su historia, su respuesta
   parcial y sus tokens, y es **terminal**: no cuenta en el tope de
   concurrencia y el reaper no lo toca. No se confunde con el run aparcado
   del HITL, que sigue en ``'running'`` porque su turno no ha terminado —
   solo está quieto.

2. **``console_support_ticket_seq``.** El identificador de un ticket es
   ``AU-<n>`` con ``n`` de esta secuencia: monótono, corto y decible por
   teléfono. No es un uuid a propósito — un uuid en un correo de soporte no
   lo repite nadie, y §25.1 de la investigación es explícito en que sin
   identificador el ticket es un agujero negro.

3. **``partners.companion_enabled``.** Por defecto ``false``: el piloto es
   interno (Auphere dos semanas sobre sus propios tenants) antes de que lo
   vea ningún partner. La puerta es ``companion:use`` **y** esta bandera.

4. **Vocabulario de auditoría** de las dos acciones nuevas, para que la
   página de auditoría del partner las pinte como una frase y no como el
   respaldo ``{actor} · {action} · {target}``.

Y la ausencia: **los ``kind`` de notificación no necesitan migración.**
``console_notifications.kind`` es ``varchar(60)`` sin CHECK que enumere los
valores (0086), y ``companion.cap_reached`` de CO-01 ya usa uno fuera de
``NotificationKind``. Se anota aquí para que nadie lo vuelva a buscar.

Revision ID: 0092_companion_pilot
Revises: 0091_companion_action_states
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0092_companion_pilot"
# El orquestador pidió ``down_revision = "0091"``; el identificador real de
# esa revisión es ``0091_companion_action_states`` (los ids de este
# repositorio son el nombre completo del archivo, no el número), y con
# ``"0091"`` a secas Alembic no resuelve la cadena. Es el mismo eslabón,
# escrito con el id que existe.
down_revision: str | Sequence[str] | None = "0091_companion_action_states"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_CONSTRAINT = "ck_companion_runs_status"
_RUN_OLD = "'running', 'completed', 'cancelled', 'error', 'interrupted'"
_RUN_NEW = _RUN_OLD + ", 'paused'"

SEQUENCE = "console_support_ticket_seq"

#: ``action`` → (categoría, severidad, resumen ES, resumen EN).
#: Las plantillas usan los mismos marcadores que ``api/console/audit.py``
#: pone a disposición; uno desconocido se pinta ``?`` y nunca rompe la
#: página.
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "console.support.ticket_opened",
        "support",
        "info",
        "{actor} abrió el ticket de soporte {ticket} sobre {topic}",
        "{actor} opened support ticket {ticket} about {topic}",
    ),
    (
        "console.support.capability_requested",
        "support",
        "info",
        "{actor} pidió la capacidad {topic} (ticket {ticket})",
        "{actor} requested capability {topic} (ticket {ticket})",
    ),
)


def upgrade() -> None:
    op.execute(f"ALTER TABLE companion.runs DROP CONSTRAINT IF EXISTS {RUN_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE companion.runs ADD CONSTRAINT {RUN_CONSTRAINT} "
        f"CHECK (status IN ({_RUN_NEW}))"
    )

    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1")
    # El endpoint corre con el rol por defecto de la conexión, así que hoy
    # esto no hace falta. Se concede igual: una llamada futura bajo
    # ``SET LOCAL ROLE nexus_app`` fallaría con un permiso denegado que
    # nadie relacionaría con una secuencia.
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {SEQUENCE} TO nexus_app")

    op.execute(
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS companion_enabled "
        "boolean NOT NULL DEFAULT false"
    )

    for action, category, severity, es, en in VOCABULARY:
        es_q = es.replace("'", "''")
        en_q = en.replace("'", "''")
        op.execute(
            "INSERT INTO console_audit_vocabulary "
            "(action, category, severity, summary_es, summary_en) "
            f"VALUES ('{action}', '{category}', '{severity}', '{es_q}', '{en_q}') "
            "ON CONFLICT (action) DO UPDATE SET category = EXCLUDED.category, "
            "severity = EXCLUDED.severity, summary_es = EXCLUDED.summary_es, "
            "summary_en = EXCLUDED.summary_en, updated_at = now()"
        )


def downgrade() -> None:
    for action, _category, _severity, _es, _en in VOCABULARY:
        op.execute(f"DELETE FROM console_audit_vocabulary WHERE action = '{action}'")
    op.execute("ALTER TABLE partners DROP COLUMN IF EXISTS companion_enabled")
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQUENCE}")
    # Las filas pausadas no caben en el CHECK viejo. Se reencaminan al
    # terminal más cercano ANTES de estrecharlo, en vez de dejar que el
    # ALTER falle a mitad de una bajada de versión. ``completed`` y no
    # ``cancelled``: el turno hizo su trabajo hasta donde el presupuesto
    # llegó, y nadie lo canceló.
    op.execute("UPDATE companion.runs SET status = 'completed' WHERE status = 'paused'")
    op.execute(f"ALTER TABLE companion.runs DROP CONSTRAINT IF EXISTS {RUN_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE companion.runs ADD CONSTRAINT {RUN_CONSTRAINT} "
        f"CHECK (status IN ({_RUN_OLD}))"
    )
