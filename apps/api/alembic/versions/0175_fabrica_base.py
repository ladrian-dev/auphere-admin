"""La base de la fábrica de agentes — spec 047, T002 (ola 0).

- ``jobs``: los trabajos largos (leer la web, construir, probar, publicar,
  certificar…). Una tabla para los nueve tipos, porque todos tienen el mismo
  ciclo —cola, progreso por bloques, resultado y caducidad— y la consola los
  consulta por una sola ruta (``GET /console/jobs/{id}``). Por cliente, con RLS
  FORCE y clave foránea **compuesta** al agente: la comprobación de una FK no
  pasa por la RLS, así que una de una sola columna dejaría que un trabajo del
  cliente A apuntara a un agente del B.
- ``job_tenant(job_id)``: la ruta de la consola recibe solo el id del trabajo.
  Esta función devuelve **solo** su cliente —como ``resolve_channel_tenant``—
  para que la API compruebe la pertenencia al partner y abra la transacción con
  ese cliente; nunca devuelve el trabajo.
- ``partners.console_v2_enabled_at`` y ``console_v2_enabled_by``: la consola
  nueva se activa partner a partner (research D38). No es un módulo de la spec
  032 (``console_modules``): es un modo de la consola con estado de migración.

Revision ID: 0175_fabrica_base
Revises: 0174_reservation_calendars
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0175_fabrica_base"
down_revision: str | Sequence[str] | None = "0174_reservation_calendars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

JOB_KINDS = (
    "client_read",
    "client_builder",
    "agent_draft",
    "tests",
    "publish",
    "fix",
    "copilot",
    "quality_check",
    "suggestions",
)
JOB_STATUSES = ("queued", "running", "done", "failed")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


STATEMENTS = (
    f"""
    CREATE TABLE jobs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid,
        kind varchar(32) NOT NULL,
        status varchar(16) NOT NULL DEFAULT 'queued',
        progress jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        questions jsonb,
        answers jsonb,
        result jsonb,
        error_code varchar(64),
        cost_micros bigint NOT NULL DEFAULT 0,
        draft_revision integer,
        created_by varchar(160),
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        updated_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz,
        CONSTRAINT uq_jobs_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_jobs_kind CHECK (kind IN ({_in(JOB_KINDS)})),
        CONSTRAINT ck_jobs_status CHECK (status IN ({_in(JOB_STATUSES)})),
        CONSTRAINT ck_jobs_finished CHECK (
            (status IN ('done', 'failed')) = (finished_at IS NOT NULL)
        ),
        CONSTRAINT ck_jobs_failed_has_code CHECK (status <> 'failed' OR error_code IS NOT NULL),
        CONSTRAINT ck_jobs_cost CHECK (cost_micros >= 0),
        CONSTRAINT fk_jobs_agent FOREIGN KEY (tenant_id, agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_jobs_tenant_agent ON jobs (tenant_id, agent_id, kind, created_at DESC)",
    # Lo que caduca: los trabajos vivos sin latido.
    "CREATE INDEX ix_jobs_live ON jobs (tenant_id, updated_at) "
    "WHERE status IN ('queued', 'running')",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE jobs FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY jobs_tenant_isolation ON jobs USING {_POLICY} WITH CHECK {_POLICY}")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON jobs TO nexus_app")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION job_tenant(p_job_id uuid)
        RETURNS uuid
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET row_security = off
        SET search_path = public
        AS $$
            SELECT tenant_id FROM jobs WHERE id = p_job_id
        $$;
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION job_tenant(uuid) TO nexus_app")

    op.execute("ALTER TABLE partners ADD COLUMN console_v2_enabled_at timestamptz")
    op.execute("ALTER TABLE partners ADD COLUMN console_v2_enabled_by varchar(160)")
    op.execute(
        "ALTER TABLE partners ADD CONSTRAINT ck_partners_console_v2_by "
        "CHECK (console_v2_enabled_by IS NULL OR console_v2_enabled_at IS NOT NULL)"
    )
    # La Auditoría del partner lee estas dos acciones en su idioma, no como código.
    op.execute(
        """
        INSERT INTO console_audit_vocabulary (action, category, severity, summary_es, summary_en)
        VALUES
            ('partner.console_v2_enabled', 'admin', 'info',
             'Auphere activó la consola nueva para tu cuenta.',
             'Auphere turned on the new console for your account.'),
            ('partner.console_v2_disabled', 'admin', 'info',
             'Auphere volvió a poner la consola de antes en tu cuenta.',
             'Auphere switched your account back to the previous console.'),
            -- De antes de la 047 y sin frase: no se veía porque el barrido de
            -- ``test_console_audit_words`` no leía acciones con dígitos.
            ('channel.whatsapp_5xx_burst', 'channels', 'warning',
             'WhatsApp falló varias veces seguidas al enviar. Auphere lo está revisando.',
             'WhatsApp failed several times in a row while sending. Auphere is looking into it.')
        ON CONFLICT (action) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM console_audit_vocabulary "
        "WHERE action IN ('partner.console_v2_enabled', 'partner.console_v2_disabled', "
        "'channel.whatsapp_5xx_burst')"
    )
    op.execute("ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_console_v2_by")
    op.execute("ALTER TABLE partners DROP COLUMN IF EXISTS console_v2_enabled_by")
    op.execute("ALTER TABLE partners DROP COLUMN IF EXISTS console_v2_enabled_at")
    op.execute("DROP FUNCTION IF EXISTS job_tenant(uuid)")
    op.execute("DROP TABLE IF EXISTS jobs CASCADE")
