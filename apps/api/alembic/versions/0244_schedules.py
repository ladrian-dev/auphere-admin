"""Spec 082 — rutinas, lo que un agente hace a su hora.

- ``schedules``: la rutina que el partner configura una vez. Es del cliente:
  FORCE RLS por ``tenant_id`` con la política canónica (garantía 1), y clave
  compuesta ``(tenant_id, agent_id)`` al agente, porque una FK de una sola
  columna no pasa por la RLS.
- ``schedule_runs``: cada vez que la rutina corre, con los intentos dentro.
  ``UNIQUE (tenant_id, schedule_id, scheduled_for)`` es lo que impide que dos
  réplicas disparen la misma ejecución: una clave, no un candado.
  ``instruction`` guarda el texto con el que se ejecutó, así editar la rutina
  no reescribe el historial.
- ``due_schedules(max_rows)``: lo que el disparador necesita ver de todos los
  clientes a la vez. ``SECURITY DEFINER`` como ``job_tenant`` (0175), y devuelve
  **solo identificadores y horas**: ni instrucción, ni nombre, ni respuesta.
- Cuatro vocabularios que crecen en una entrada: el tipo de trabajo
  ``schedule_run``, el origen de consumo ``schedule``, su partida ``schedules``
  y el asiento ``debit_schedule`` de la bolsa.

Nada de esto toca datos existentes: todas las ampliaciones son de un ``CHECK``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0244_schedules"
down_revision: str | Sequence[str] | None = "0243_template_edit_vocabulary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

#: Los tipos de trabajo tal como los dejó la 0229, más el nuevo.
_JOB_KINDS = (
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
    "agenda_text",
)
#: Los orígenes y las partidas tal como los dejó la 0220.
_SOURCES = (
    "channel",
    "qa",
    "companion",
    "builder",
    "tests",
    "reader",
    "indexer",
    "suggestions",
    "certification",
    "tests_client",
)
_LINES = ("conversations", "build", "companion", "platform", "client_tests")
#: Los asientos de la bolsa tal como los dejó la 0220.
_ENTRY_KINDS = (
    "assign",
    "lower",
    "move_in",
    "move_out",
    "refill",
    "debit_turn",
    "currency_change",
    "migration",
    "debit_tests",
)

#: Lo que la Auditoría del partner dice de cada acción sobre una rutina.
#: ``{actor}`` y ``{client}`` los rellena la consola.
VOCABULARY: tuple[tuple[str, str, str, str], ...] = (
    (
        "schedule.create",
        "info",
        "{actor} creó una rutina para un agente de {client}.",
        "{actor} created a routine for an agent of {client}.",
    ),
    (
        "schedule.pause",
        "info",
        "{actor} pausó una rutina de {client}.",
        "{actor} paused a routine of {client}.",
    ),
    (
        "schedule.resume",
        "info",
        "{actor} reanudó una rutina de {client}.",
        "{actor} resumed a routine of {client}.",
    ),
    (
        "schedule.archive",
        "warning",
        "{actor} archivó una rutina de {client}: deja de ejecutarse.",
        "{actor} archived a routine of {client}: it stops running.",
    ),
    (
        "schedule.restore",
        "info",
        "{actor} restauró una rutina archivada de {client}, que queda en pausa.",
        "{actor} restored an archived routine of {client}, which stays paused.",
    ),
)

_CADENCES = ("daily", "weekly", "monthly", "once")
_STATES = ("active", "paused", "archived")
_PAUSE_REASONS = ("manual", "agent_unavailable", "no_balance", "failures")
_RUN_STATUSES = ("running", "done", "partial", "failed", "skipped")
_TRIGGERS = ("schedule", "manual")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _check(table: str, name: str, condition: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})")


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE schedules (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            agent_id uuid NOT NULL,
            name varchar(60) NOT NULL,
            instruction text NOT NULL,
            cadence varchar(16) NOT NULL,
            weekdays smallint[],
            day_of_month smallint,
            run_date date,
            local_time time NOT NULL,
            email boolean NOT NULL DEFAULT false,
            state varchar(16) NOT NULL DEFAULT 'active',
            pause_reason varchar(32),
            next_run_at timestamptz,
            consecutive_failures smallint NOT NULL DEFAULT 0,
            created_by varchar(160) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_schedules_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT ck_schedules_name CHECK (length(btrim(name)) > 0),
            CONSTRAINT ck_schedules_instruction
                CHECK (length(btrim(instruction)) > 0 AND length(instruction) <= 2000),
            CONSTRAINT ck_schedules_cadence CHECK (cadence IN ({_in(_CADENCES)})),
            CONSTRAINT ck_schedules_state CHECK (state IN ({_in(_STATES)})),
            CONSTRAINT ck_schedules_pause_reason
                CHECK (pause_reason IS NULL OR pause_reason IN ({_in(_PAUSE_REASONS)})),
            CONSTRAINT ck_schedules_paused_has_reason
                CHECK (state <> 'paused' OR pause_reason IS NOT NULL),
            CONSTRAINT ck_schedules_failures CHECK (consecutive_failures >= 0),
            -- Cada periodicidad trae lo suyo y deja nulo lo que no es suyo.
            -- ``coalesce`` a propósito: para un array vacío ``array_length``
            -- devuelve NULL, un CHECK que da NULL pasa, y una rutina semanal
            -- sin ningún día se colaría hasta el disparador.
            CONSTRAINT ck_schedules_weekly
                CHECK (cadence <> 'weekly' OR coalesce(array_length(weekdays, 1), 0) > 0),
            CONSTRAINT ck_schedules_weekdays_range
                CHECK (weekdays IS NULL OR (weekdays <@ ARRAY[0,1,2,3,4,5,6]::smallint[])),
            CONSTRAINT ck_schedules_monthly
                CHECK (cadence <> 'monthly' OR (day_of_month BETWEEN 1 AND 28)),
            CONSTRAINT ck_schedules_once CHECK (cadence <> 'once' OR run_date IS NOT NULL),
            CONSTRAINT ck_schedules_only_its_own
                CHECK ((cadence = 'weekly') = (weekdays IS NOT NULL)
                   AND (cadence = 'monthly') = (day_of_month IS NOT NULL)
                   AND (cadence = 'once') = (run_date IS NOT NULL)),
            CONSTRAINT fk_schedules_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_schedules_agent
                FOREIGN KEY (tenant_id, agent_id) REFERENCES agents (tenant_id, id)
                ON DELETE CASCADE
        )
        """
    )
    op.create_index("ix_schedules_tenant_id", "schedules", ["tenant_id"])
    op.create_index("ix_schedules_tenant_agent", "schedules", ["tenant_id", "agent_id"])
    # El índice que sostiene el barrido: solo lo que puede vencer.
    op.create_index(
        "ix_schedules_due",
        "schedules",
        ["next_run_at"],
        postgresql_where=sa.text("state = 'active' AND next_run_at IS NOT NULL"),
    )
    _rls("schedules")

    op.execute(
        f"""
        CREATE TABLE schedule_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            schedule_id uuid NOT NULL,
            scheduled_for timestamptz NOT NULL,
            trigger varchar(16) NOT NULL DEFAULT 'schedule',
            status varchar(16) NOT NULL DEFAULT 'running',
            attempts smallint NOT NULL DEFAULT 1,
            instruction text NOT NULL,
            answer text,
            tools_used jsonb,
            withheld jsonb,
            duration_ms integer,
            cost_micros bigint NOT NULL DEFAULT 0,
            error_code varchar(64),
            error_detail text,
            job_id uuid,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_schedule_runs_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_schedule_runs_slot UNIQUE (tenant_id, schedule_id, scheduled_for),
            CONSTRAINT ck_schedule_runs_status CHECK (status IN ({_in(_RUN_STATUSES)})),
            CONSTRAINT ck_schedule_runs_trigger CHECK (trigger IN ({_in(_TRIGGERS)})),
            CONSTRAINT ck_schedule_runs_attempts CHECK (attempts BETWEEN 1 AND 3),
            CONSTRAINT ck_schedule_runs_cost CHECK (cost_micros >= 0),
            CONSTRAINT ck_schedule_runs_finished
                CHECK ((status IN ('done', 'partial', 'failed', 'skipped'))
                       = (finished_at IS NOT NULL)),
            CONSTRAINT ck_schedule_runs_failed_has_code
                CHECK (status <> 'failed' OR error_code IS NOT NULL),
            -- Parcial sin decir qué faltó no se guarda (constitución §V).
            CONSTRAINT ck_schedule_runs_partial_says_why
                CHECK (status <> 'partial' OR withheld IS NOT NULL),
            CONSTRAINT fk_schedule_runs_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_schedule_runs_schedule
                FOREIGN KEY (tenant_id, schedule_id) REFERENCES schedules (tenant_id, id)
                ON DELETE CASCADE
        )
        """
    )
    op.create_index("ix_schedule_runs_tenant_id", "schedule_runs", ["tenant_id"])
    op.execute(
        "CREATE INDEX ix_schedule_runs_thread ON schedule_runs "
        "(tenant_id, schedule_id, scheduled_for DESC)"
    )
    _rls("schedule_runs")

    # El disparador mira a todos los clientes a la vez, y con la RLS una sesión
    # sin cliente puesto no ve nada. Devuelve identificadores y horas, nada más.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION due_schedules(max_rows integer)
        RETURNS TABLE (tenant_id uuid, schedule_id uuid, scheduled_for timestamptz)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET row_security = off
        SET search_path = public
        AS $$
            SELECT s.tenant_id, s.id, s.next_run_at
            FROM schedules s
            WHERE s.state = 'active' AND s.next_run_at IS NOT NULL AND s.next_run_at <= now()
            ORDER BY s.next_run_at
            LIMIT max_rows
        $$;
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION due_schedules(integer) TO nexus_app")

    # La Auditoría del partner lee estas acciones en su idioma, nunca como
    # código: una fila sin frase se lee «Auphere · schedule.pause · schedule:…».
    for action, severity, es, en in VOCABULARY:
        op.execute(
            "INSERT INTO console_audit_vocabulary "
            "(action, category, severity, summary_es, summary_en) "
            f"VALUES ('{action}', 'agents', '{severity}', "
            f"'{es.replace(chr(39), chr(39) * 2)}', '{en.replace(chr(39), chr(39) * 2)}') "
            "ON CONFLICT (action) DO NOTHING"
        )

    _check("jobs", "ck_jobs_kind", f"kind IN ({_in((*_JOB_KINDS, 'schedule_run'))})")
    _check("usage_records", "ck_usage_source", f"source IN ({_in((*_SOURCES, 'schedule'))})")
    _check(
        "usage_records",
        "ck_usage_line",
        f"line IS NULL OR line IN ({_in((*_LINES, 'schedules'))})",
    )
    _check(
        "client_wallet_entries",
        "ck_client_wallet_entries_kind",
        f"kind IN ({_in((*_ENTRY_KINDS, 'debit_schedule'))})",
    )


def downgrade() -> None:
    # Lo que ya se cobró sigue cobrado, pero vuelve a las categorías de antes:
    # si no, el CHECK de abajo abortaría. Con la RLS fuera, como la 0205.
    op.execute("SET LOCAL row_security = off")
    op.execute("UPDATE client_wallet_entries SET kind = 'debit_turn' WHERE kind = 'debit_schedule'")
    op.execute("UPDATE usage_records SET line = 'conversations' WHERE line = 'schedules'")
    op.execute("UPDATE usage_records SET source = 'channel' WHERE source = 'schedule'")
    op.execute("DELETE FROM jobs WHERE kind = 'schedule_run'")

    _check("jobs", "ck_jobs_kind", f"kind IN ({_in(_JOB_KINDS)})")
    _check("usage_records", "ck_usage_source", f"source IN ({_in(_SOURCES)})")
    _check("usage_records", "ck_usage_line", f"line IS NULL OR line IN ({_in(_LINES)})")
    _check(
        "client_wallet_entries",
        "ck_client_wallet_entries_kind",
        f"kind IN ({_in(_ENTRY_KINDS)})",
    )

    op.execute("DELETE FROM console_audit_vocabulary WHERE action LIKE 'schedule.%'")
    op.execute("DROP FUNCTION IF EXISTS due_schedules(integer)")
    op.execute("DROP TABLE IF EXISTS schedule_runs")
    op.execute("DROP TABLE IF EXISTS schedules")
