"""El sector en la ficha, las guías generadas, los agentes sugeridos y la conversación
de cada pasada — spec 047, enmienda del 2026-10-29 (T199; requisitos 57.1, 58.4, 60.6
y 61.6; research D46, D47, D51, D52 y D58 a D65).

- **``business_profiles.sector``** (JSONB): la clave de una guía de Auphere (u
  ``otro``), la etiqueta (de 1 a 40), la confianza, de dónde salió y quién lo decidió.
  ``NULL`` mientras se identifica. La base comprueba la forma (un objeto con clave
  y etiqueta acotadas): la etiqueta sale de un modelo o de una persona y es dato no
  confiable (§III).
- **``generated_guides``**: la guía del sector que el constructor genera **para un
  cliente** cuyo sector no tiene guía de Auphere, con sus 12 pruebas, ``generated``
  (requisito 58.4, D47). Es del cliente (garantía 1), nunca compartida; la escribe
  la T201. Una viva por etiqueta y cliente.
- **``suggested_agents``**: los agentes que propone el constructor del cliente
  (requisito 60.6). No se crean solos; «Descartar» los aparta y no vuelven.
- **``agent_tests.generated_guide_id``**: la prueba del sector que salió de una guía
  generada del propio cliente (``origin: generated`` en la consola, T201).
- **``agent_test_results.stop``**: por qué terminó la conversación de cada pasada
  con el cliente simulado (requisito 61.3); la conversación ya vive en
  ``transcript`` (0187). Las escribe la T206.
- **``jobs``** gana el tipo ``sector_identify`` (T200).
- **Auditoría**: ``suggested_agent.dismissed``.

Tablas de cliente: RLS ENABLE + FORCE con la política canónica, ``UNIQUE (tenant_id,
id)`` y FK compuestas (garantía 1, ``test_43``; caso adversarial en ``test_53``).
Ninguna lleva ``agent_id``.

Revision ID: 0206_sector_guides_builder
Revises: 0205_retire_agendapro
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0206_sector_guides_builder"
down_revision: str | Sequence[str] | None = "0205_retire_agendapro"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

JOB_KINDS_BEFORE = (
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
JOB_KINDS = (*JOB_KINDS_BEFORE, "sector_identify")
GUIDE_STATUSES = ("generated", "reviewed", "promoted", "archived")
SUGGESTION_STATUSES = ("open", "dismissed", "superseded")
ROLES = ("reception", "sales", "billing", "support")
STOPS = ("plan_done", "goodbye", "handoff", "turn_limit")

#: (acción, categoría, gravedad, español, inglés)
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("suggested_agent.dismissed", "agents", "info",
     "{actor} descartó un agente sugerido para {client}.",
     "{actor} dismissed a suggested agent for {client}."),
)  # fmt: skip


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


SECTOR_CHECK = (
    "sector IS NULL OR ("
    "jsonb_typeof(sector) = 'object' "
    "AND sector ? 'key' AND sector ? 'label' "
    "AND (sector->>'key') ~ '^[a-z_]{1,40}$' "
    "AND char_length(sector->>'label') BETWEEN 1 AND 40)"
)

GUIDES = f"""
CREATE TABLE generated_guides (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    sector_label varchar(40) NOT NULL,
    label_key varchar(60) NOT NULL,
    guide jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    tests jsonb NOT NULL DEFAULT '[]'::jsonb,
    status varchar(12) NOT NULL DEFAULT 'generated',
    job_id uuid,
    reviewed_by varchar(160),
    reviewed_at timestamptz,
    promoted_to varchar(40),
    promoted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_generated_guides_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_generated_guides_status CHECK (status IN ({_in(GUIDE_STATUSES)})),
    CONSTRAINT ck_generated_guides_label CHECK (char_length(sector_label) BETWEEN 1 AND 40),
    CONSTRAINT ck_generated_guides_key CHECK (label_key ~ '^[a-z0-9_ ]{{1,60}}$'),
    CONSTRAINT ck_generated_guides_guide CHECK (jsonb_typeof(guide) = 'object'),
    CONSTRAINT ck_generated_guides_tests CHECK (
        jsonb_typeof(tests) = 'array' AND jsonb_array_length(tests) <= 12
    ),
    CONSTRAINT ck_generated_guides_promoted CHECK (
        (status = 'promoted') = (promoted_to IS NOT NULL AND promoted_at IS NOT NULL)
    ),
    CONSTRAINT fk_generated_guides_job FOREIGN KEY (tenant_id, job_id)
        REFERENCES jobs (tenant_id, id) ON DELETE SET NULL (job_id)
)
"""

SUGGESTED = f"""
CREATE TABLE suggested_agents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name varchar(40) NOT NULL,
    name_key varchar(60) NOT NULL,
    description varchar(1024) NOT NULL,
    role varchar(12),
    status varchar(12) NOT NULL DEFAULT 'open',
    fingerprint char(64),
    job_id uuid,
    decided_by varchar(160),
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_suggested_agents_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_suggested_agents_status CHECK (status IN ({_in(SUGGESTION_STATUSES)})),
    CONSTRAINT ck_suggested_agents_role CHECK (role IS NULL OR role IN ({_in(ROLES)})),
    CONSTRAINT ck_suggested_agents_name CHECK (char_length(name) BETWEEN 1 AND 40),
    CONSTRAINT ck_suggested_agents_description CHECK (
        char_length(description) BETWEEN 20 AND 1024
    ),
    CONSTRAINT ck_suggested_agents_fingerprint CHECK (
        fingerprint IS NULL OR fingerprint ~ '^[a-f0-9]{{64}}$'
    ),
    CONSTRAINT ck_suggested_agents_decided CHECK ((status = 'open') = (decided_at IS NULL)),
    CONSTRAINT fk_suggested_agents_job FOREIGN KEY (tenant_id, job_id)
        REFERENCES jobs (tenant_id, id) ON DELETE SET NULL (job_id)
)
"""


def _client_table(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def upgrade() -> None:
    # 1. El sector, en la ficha.
    op.execute("ALTER TABLE business_profiles ADD COLUMN sector jsonb")
    op.execute(
        "ALTER TABLE business_profiles "
        f"ADD CONSTRAINT ck_business_profiles_sector CHECK ({SECTOR_CHECK})"
    )

    # 2. El trabajo que lo identifica.
    op.execute("ALTER TABLE jobs DROP CONSTRAINT ck_jobs_kind")
    op.execute(f"ALTER TABLE jobs ADD CONSTRAINT ck_jobs_kind CHECK (kind IN ({_in(JOB_KINDS)}))")

    # 3. Las guías generadas por cliente.
    op.execute(GUIDES)
    op.execute(
        "CREATE UNIQUE INDEX uq_generated_guides_live_label ON generated_guides "
        "(tenant_id, label_key) WHERE status <> 'archived'"
    )
    _client_table("generated_guides")

    # 4. Los agentes sugeridos.
    op.execute(SUGGESTED)
    op.execute(
        "CREATE UNIQUE INDEX uq_suggested_agents_open_name ON suggested_agents "
        "(tenant_id, name_key) WHERE status = 'open'"
    )
    op.execute("CREATE INDEX ix_suggested_agents_status ON suggested_agents (tenant_id, status)")
    _client_table("suggested_agents")

    # 5. Las pruebas: de qué guía generada salió y por qué terminó cada pasada.
    op.execute("ALTER TABLE agent_tests ADD COLUMN generated_guide_id uuid")
    op.execute(
        "ALTER TABLE agent_tests ADD CONSTRAINT fk_agent_tests_generated_guide "
        "FOREIGN KEY (tenant_id, generated_guide_id) "
        "REFERENCES generated_guides (tenant_id, id) ON DELETE SET NULL (generated_guide_id)"
    )
    op.execute("ALTER TABLE agent_test_results ADD COLUMN stop varchar(16)")
    op.execute(
        "ALTER TABLE agent_test_results ADD CONSTRAINT ck_agent_test_results_stop "
        f"CHECK (stop IS NULL OR stop IN ({_in(STOPS)}))"
    )

    # 6. La frase de Auditoría.
    vocabulary = sa.table(
        "console_audit_vocabulary",
        sa.column("action", sa.String),
        sa.column("category", sa.String),
        sa.column("severity", sa.String),
        sa.column("summary_es", sa.Text),
        sa.column("summary_en", sa.Text),
    )
    for action, category, severity, es, en in VOCABULARY:
        op.execute(
            sa.dialects.postgresql.insert(vocabulary)
            .values(
                action=action, category=category, severity=severity, summary_es=es, summary_en=en
            )
            .on_conflict_do_nothing(index_elements=["action"])
        )


def downgrade() -> None:
    actions = ", ".join(f"'{row[0]}'" for row in VOCABULARY)
    op.execute(f"DELETE FROM console_audit_vocabulary WHERE action IN ({actions})")
    op.execute(
        "ALTER TABLE agent_test_results DROP CONSTRAINT IF EXISTS ck_agent_test_results_stop"
    )
    op.execute("ALTER TABLE agent_test_results DROP COLUMN IF EXISTS stop")
    op.execute("ALTER TABLE agent_tests DROP CONSTRAINT IF EXISTS fk_agent_tests_generated_guide")
    op.execute("ALTER TABLE agent_tests DROP COLUMN IF EXISTS generated_guide_id")
    op.execute("DROP TABLE IF EXISTS suggested_agents CASCADE")
    op.execute("DROP TABLE IF EXISTS generated_guides CASCADE")
    # Los trabajos del tipo que desaparece se van antes de volver a la lista de antes.
    op.execute(
        "DO $$ BEGIN "
        "SET LOCAL row_security = off; "
        "DELETE FROM jobs WHERE kind = 'sector_identify'; "
        "END $$"
    )
    op.execute("ALTER TABLE jobs DROP CONSTRAINT ck_jobs_kind")
    op.execute(
        f"ALTER TABLE jobs ADD CONSTRAINT ck_jobs_kind CHECK (kind IN ({_in(JOB_KINDS_BEFORE)}))"
    )
    op.execute(
        "ALTER TABLE business_profiles DROP CONSTRAINT IF EXISTS ck_business_profiles_sector"
    )
    op.execute("ALTER TABLE business_profiles DROP COLUMN IF EXISTS sector")
