"""Las sugerencias semanales de cada agente — spec 047, T173 y T174 (requisito 51;
``data-model.md`` §9).

- **``agent_suggestions``**: lo que el worker encontró la semana pasada en las
  conversaciones de un agente, ya agregado. Cada fila agrupa al menos 5
  conversaciones de al menos 5 contactos distintos (51.3), lleva una paráfrasis
  sin datos personales (``topic``) y apunta a su propuesta (``proposals``, autor
  ``suggestion``), que trae el parche y la prueba nueva. Aceptar la lleva al
  borrador; descartar guarda el motivo y la aparta 30 días (``suppress_until``).
  Nunca guarda cuerpos de mensaje ni a qué conversaciones o contactos se refiere:
  solo cuántas (C1 y C8).
- **El vocabulario de Auditoría** gana ``suggestion.accepted`` y
  ``suggestion.discarded``, en la categoría Mejora (``events.md`` §4).

Tabla de cliente: RLS ENABLE + FORCE, ``UNIQUE (tenant_id, id)`` y FK compuestas
(garantía 1). Lleva ``agent_id``, así que entra en el barrido de la garantía 9.

Revision ID: 0199_agent_suggestions
Revises: 0198_lite_and_corrections
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0199_agent_suggestions"
down_revision: str | Sequence[str] | None = "0198_lite_and_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

STATUSES = ("open", "accepted", "discarded")

#: (acción, categoría, gravedad, español, inglés)
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("suggestion.accepted", "improvement", "info",
     "{actor} aceptó una sugerencia para un agente de {client}.",
     "{actor} accepted a suggestion for an agent of {client}."),
    ("suggestion.discarded", "improvement", "info",
     "{actor} descartó una sugerencia para un agente de {client}.",
     "{actor} discarded a suggestion for an agent of {client}."),
)  # fmt: skip


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


TABLE = f"""
CREATE TABLE agent_suggestions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    agent_id uuid NOT NULL,
    week date NOT NULL,
    topic_key varchar(60) NOT NULL,
    topic varchar(300) NOT NULL,
    summary varchar(300),
    conversations_count integer NOT NULL,
    contacts_count integer NOT NULL,
    proposal_id uuid,
    diff_hash char(64) NOT NULL,
    test_id uuid,
    job_id uuid,
    status varchar(12) NOT NULL DEFAULT 'open',
    discard_reason varchar(300),
    suppress_until timestamptz,
    decided_by varchar(160),
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_agent_suggestions_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_agent_suggestions_topic UNIQUE (tenant_id, agent_id, week, topic_key),
    CONSTRAINT ck_agent_suggestions_status CHECK (status IN ({_in(STATUSES)})),
    CONSTRAINT ck_agent_suggestions_counts CHECK (
        conversations_count >= 5 AND contacts_count >= 5
        AND contacts_count <= conversations_count
    ),
    CONSTRAINT ck_agent_suggestions_topic CHECK (char_length(topic) BETWEEN 1 AND 300),
    CONSTRAINT ck_agent_suggestions_key CHECK (topic_key ~ '^[a-z0-9_]{{1,60}}$'),
    CONSTRAINT ck_agent_suggestions_hash CHECK (diff_hash ~ '^[a-f0-9]{{64}}$'),
    CONSTRAINT ck_agent_suggestions_discarded CHECK (
        (status = 'discarded') = (discard_reason IS NOT NULL AND suppress_until IS NOT NULL)
    ),
    CONSTRAINT ck_agent_suggestions_reason CHECK (
        discard_reason IS NULL OR char_length(discard_reason) BETWEEN 3 AND 300
    ),
    CONSTRAINT ck_agent_suggestions_decided CHECK (status = 'open' OR decided_at IS NOT NULL),
    CONSTRAINT fk_agent_suggestions_agent FOREIGN KEY (tenant_id, agent_id)
        REFERENCES agents (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_suggestions_proposal FOREIGN KEY (tenant_id, proposal_id)
        REFERENCES proposals (tenant_id, id) ON DELETE SET NULL (proposal_id),
    CONSTRAINT fk_agent_suggestions_test FOREIGN KEY (tenant_id, test_id)
        REFERENCES agent_tests (tenant_id, id) ON DELETE SET NULL (test_id),
    CONSTRAINT fk_agent_suggestions_job FOREIGN KEY (tenant_id, job_id)
        REFERENCES jobs (tenant_id, id) ON DELETE SET NULL (job_id)
)
"""


def upgrade() -> None:
    op.execute(TABLE)
    op.execute(
        "CREATE INDEX ix_agent_suggestions_agent "
        "ON agent_suggestions (tenant_id, agent_id, status, week DESC)"
    )
    op.execute("ALTER TABLE agent_suggestions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_suggestions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agent_suggestions_tenant_isolation ON agent_suggestions "
        f"USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON agent_suggestions TO nexus_app")

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
    op.execute("DROP TABLE IF EXISTS agent_suggestions CASCADE")
