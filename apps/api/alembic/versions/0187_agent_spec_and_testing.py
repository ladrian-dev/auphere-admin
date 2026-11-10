"""El AgentSpec, las propuestas, las pruebas y la revisión — spec 047, T077
(requisitos 15.3, 16.1, 21.1, 21.2 y 23; ``data-model.md`` §3 y §4).

- **``agent_configs``** gana ``spec`` (el AgentSpec v1 de la versión), ``gate``
  (el resultado de la puerta), ``override_reason`` (solo owner o admin),
  ``undo_until`` (10 minutos tras publicar), ``published_by`` y ``published_at``.
  ``system_prompt_rendered`` sigue siendo la verdad del runtime.
- **``proposals``**: lo que propone el constructor (o el copiloto, una sugerencia
  o una corrección), con su ``state_hash`` y caducidad. El ``id`` es un uuid5 del
  contenido y del estado: proponer dos veces lo mismo no crea dos (§IV).
- **La suite**: ``agent_test_suites`` (una por agente), ``agent_tests``,
  ``agent_test_runs`` y ``agent_test_results`` (tres pasadas por prueba).
- **``agent_reviews``**: los hallazgos de la revisión de una versión.
- **De plataforma** (sin datos de clientes, solo los escribe el admin):
  ``sector_test_catalog`` y ``builder_eval_runs``.

Todas las tablas de cliente nacen con RLS ENABLE + FORCE, ``UNIQUE (tenant_id,
id)`` y FK compuestas (garantía 1); las que tienen ``agent_id`` entran en el
barrido de la garantía 9.

Revision ID: 0187_agent_spec_and_testing
Revises: 0186_migrate_hours_to_ficha
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0187_agent_spec_and_testing"
down_revision: str | Sequence[str] | None = "0186_migrate_hours_to_ficha"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

PROPOSAL_KINDS = (
    "agent_spec_patch",
    "client_spec_patch",
    "test_add",
    "fix",
    "channel_config_patch",
)
PROPOSAL_AUTHORS = ("builder", "copilot", "suggestion", "correction")
PROPOSAL_STATUSES = ("open", "applied", "rejected", "expired", "stale")
TEST_KINDS = ("case", "sector", "person", "conversation", "correction")
RUN_SCOPES = ("all", "affected", "one")
RUN_REASONS = ("manual", "publish", "fix", "business_change", "certification")
RUN_STATUSES = ("queued", "running", "done", "failed")
PAID_BY = ("partner", "auphere")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _agent_fk(table: str, column: str = "agent_id") -> str:
    return (
        f"CONSTRAINT fk_{table}_agent FOREIGN KEY (tenant_id, {column}) "
        "REFERENCES agents (tenant_id, id) ON DELETE CASCADE"
    )


STATEMENTS = (
    """
    ALTER TABLE agent_configs
        ADD COLUMN spec jsonb,
        ADD COLUMN gate jsonb,
        ADD COLUMN override_reason text,
        ADD COLUMN undo_until timestamptz,
        ADD COLUMN published_by varchar(160),
        ADD COLUMN published_at timestamptz,
        ADD CONSTRAINT ck_agent_configs_override_reason
            CHECK (override_reason IS NULL OR char_length(override_reason) BETWEEN 1 AND 500)
    """,
    f"""
    CREATE TABLE proposals (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid,
        kind varchar(24) NOT NULL,
        author varchar(16) NOT NULL,
        summary varchar(300),
        diff jsonb NOT NULL,
        state_hash char(64) NOT NULL,
        status varchar(12) NOT NULL DEFAULT 'open',
        job_id uuid,
        created_by varchar(160),
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        decided_by varchar(160),
        decided_at timestamptz,
        CONSTRAINT uq_proposals_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_proposals_kind CHECK (kind IN ({_in(PROPOSAL_KINDS)})),
        CONSTRAINT ck_proposals_author CHECK (author IN ({_in(PROPOSAL_AUTHORS)})),
        CONSTRAINT ck_proposals_status CHECK (status IN ({_in(PROPOSAL_STATUSES)})),
        CONSTRAINT ck_proposals_hash CHECK (state_hash ~ '^[a-f0-9]{{64}}$'),
        CONSTRAINT ck_proposals_decided CHECK (
            status IN ('open', 'expired', 'stale') OR decided_at IS NOT NULL
        ),
        {_agent_fk("proposals")}
    )
    """,
    "CREATE INDEX ix_proposals_agent ON proposals (tenant_id, agent_id, status, created_at DESC)",
    f"""
    CREATE TABLE agent_test_suites (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid NOT NULL,
        revision integer NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_test_suites_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_agent_test_suites_agent UNIQUE (tenant_id, agent_id),
        CONSTRAINT ck_agent_test_suites_revision CHECK (revision >= 1),
        {_agent_fk("agent_test_suites")}
    )
    """,
    f"""
    CREATE TABLE agent_tests (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        suite_id uuid NOT NULL,
        kind varchar(16) NOT NULL,
        name varchar(120) NOT NULL,
        persona text NOT NULL DEFAULT '',
        first_message text NOT NULL,
        plan text NOT NULL DEFAULT '',
        expected_state jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
        critical boolean NOT NULL DEFAULT false,
        not_applicable_reason text,
        sector_test_ref varchar(120),
        stale boolean NOT NULL DEFAULT false,
        created_by_kind varchar(16) NOT NULL DEFAULT 'builder',
        archived_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_tests_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_agent_tests_kind CHECK (kind IN ({_in(TEST_KINDS)})),
        CONSTRAINT ck_agent_tests_name CHECK (char_length(name) BETWEEN 1 AND 120),
        CONSTRAINT ck_agent_tests_first_message CHECK (char_length(first_message) BETWEEN 1 AND 2000),
        CONSTRAINT ck_agent_tests_na_only_sector CHECK (
            not_applicable_reason IS NULL OR (kind = 'sector' AND char_length(not_applicable_reason) >= 3)
        ),
        CONSTRAINT fk_agent_tests_suite FOREIGN KEY (tenant_id, suite_id)
            REFERENCES agent_test_suites (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_agent_tests_suite ON agent_tests (tenant_id, suite_id, kind)",
    f"""
    CREATE TABLE agent_test_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid NOT NULL,
        agent_config_id uuid,
        model_policy jsonb,
        scope varchar(12) NOT NULL DEFAULT 'all',
        reason varchar(20) NOT NULL DEFAULT 'manual',
        status varchar(12) NOT NULL DEFAULT 'queued',
        paid_by varchar(12) NOT NULL DEFAULT 'partner',
        cost_micros bigint NOT NULL DEFAULT 0,
        job_id uuid,
        summary jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        created_by varchar(160),
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz,
        CONSTRAINT uq_agent_test_runs_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_agent_test_runs_scope CHECK (scope IN ({_in(RUN_SCOPES)})),
        CONSTRAINT ck_agent_test_runs_reason CHECK (reason IN ({_in(RUN_REASONS)})),
        CONSTRAINT ck_agent_test_runs_status CHECK (status IN ({_in(RUN_STATUSES)})),
        CONSTRAINT ck_agent_test_runs_paid_by CHECK (paid_by IN ({_in(PAID_BY)})),
        CONSTRAINT ck_agent_test_runs_cost CHECK (cost_micros >= 0),
        {_agent_fk("agent_test_runs")},
        CONSTRAINT fk_agent_test_runs_version FOREIGN KEY (tenant_id, agent_config_id)
            REFERENCES agent_configs (tenant_id, id) ON DELETE SET NULL (agent_config_id)
    )
    """,
    "CREATE INDEX ix_agent_test_runs_agent ON agent_test_runs (tenant_id, agent_id, created_at DESC)",
    """
    CREATE TABLE agent_test_results (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        run_id uuid NOT NULL,
        test_id uuid NOT NULL,
        attempt smallint NOT NULL,
        passed boolean,
        dimensions jsonb NOT NULL DEFAULT '[]'::jsonb,
        explanation text,
        final_state jsonb NOT NULL DEFAULT '{}'::jsonb,
        transcript jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_test_results_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_agent_test_results_attempt UNIQUE (tenant_id, run_id, test_id, attempt),
        CONSTRAINT ck_agent_test_results_attempt CHECK (attempt BETWEEN 1 AND 3),
        CONSTRAINT fk_agent_test_results_run FOREIGN KEY (tenant_id, run_id)
            REFERENCES agent_test_runs (tenant_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_agent_test_results_test FOREIGN KEY (tenant_id, test_id)
            REFERENCES agent_tests (tenant_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE agent_reviews (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_config_id uuid NOT NULL,
        findings jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_reviews_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_agent_reviews_version FOREIGN KEY (tenant_id, agent_config_id)
            REFERENCES agent_configs (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_agent_reviews_version ON agent_reviews (tenant_id, agent_config_id, created_at DESC)",
)

TENANT_TABLES = (
    "proposals",
    "agent_test_suites",
    "agent_tests",
    "agent_test_runs",
    "agent_test_results",
    "agent_reviews",
)

PLATFORM_STATEMENTS = (
    """
    CREATE TABLE sector_test_catalog (
        sector_key varchar(40) NOT NULL,
        version integer NOT NULL,
        tests jsonb NOT NULL,
        published_at timestamptz NOT NULL DEFAULT now(),
        published_by varchar(160) NOT NULL,
        PRIMARY KEY (sector_key, version),
        CONSTRAINT ck_sector_test_catalog_key CHECK (sector_key ~ '^[a-z0-9_]{2,40}$'),
        CONSTRAINT ck_sector_test_catalog_version CHECK (version >= 1),
        CONSTRAINT ck_sector_test_catalog_tests CHECK (jsonb_typeof(tests) = 'array')
    )
    """,
    """
    CREATE TABLE builder_eval_runs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        bank_version varchar(40) NOT NULL,
        results jsonb NOT NULL DEFAULT '[]'::jsonb,
        validator_first_pass_pct numeric(5, 2),
        sector_pass_unedited_pct numeric(5, 2),
        draft_p90_ms integer,
        created_at timestamptz NOT NULL DEFAULT now(),
        created_by varchar(160) NOT NULL
    )
    """,
)
PLATFORM_TABLES = ("sector_test_catalog", "builder_eval_runs")


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING {_POLICY} WITH CHECK {_POLICY}"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")
    for statement in PLATFORM_STATEMENTS:
        op.execute(statement)
    for table in PLATFORM_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def downgrade() -> None:
    for table in reversed(PLATFORM_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute(
        """
        ALTER TABLE agent_configs
            DROP CONSTRAINT IF EXISTS ck_agent_configs_override_reason,
            DROP COLUMN IF EXISTS published_at,
            DROP COLUMN IF EXISTS published_by,
            DROP COLUMN IF EXISTS undo_until,
            DROP COLUMN IF EXISTS override_reason,
            DROP COLUMN IF EXISTS gate,
            DROP COLUMN IF EXISTS spec
        """
    )
