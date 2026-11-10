"""La consola lite gana Agentes y Negocio, y las correcciones desde la Bandeja — spec 047, T166 a T167 y T175 a T176 (requisitos 50 y 52; ``data-model.md`` §9 y §10).

- ``client_access.modules`` admite ``agents`` y ``business`` (el CHECK
  ``ck_client_access_modules``). Con la consola nueva vienen por defecto sin
  escribirse aquí: los añade ``client_auth.open_client``.
- ``inbox_corrections``: «Corregir esta respuesta». Lo que escribió la persona del
  cliente (la lección), la paráfrasis sin datos personales de lo que preguntó el
  cliente final, dónde están los datos personales que quedan (posiciones, nunca
  los datos) y en qué acabó: un cambio de la ficha, una fuente del agente o una
  propuesta al partner. FK compuestas al cliente, la conversación, el agente, el
  cambio de la ficha, la fuente y la propuesta. ``message_id`` va sin FK:
  ``messages`` está particionada y no tiene ``UNIQUE (tenant_id, id)``.
- La acción de auditoría ``correction.proposed`` (categoría Mejora).

Revision ID: 0198_lite_and_corrections
Revises: 0197_audit_vocabulary_047
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0198_lite_and_corrections"
down_revision: str | Sequence[str] | None = "0197_audit_vocabulary_047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
_MODULES_BEFORE = "'panel', 'inbox', 'usage', 'reservas'"
_MODULES_AFTER = "'panel', 'inbox', 'usage', 'reservas', 'agents', 'business'"
_TABLE = "inbox_corrections"

#: (acción, categoría, gravedad, español, inglés)
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("correction.proposed", "improvement", "info",
     "{actor} propuso una mejora a un agente de {client} desde una conversación.",
     "{actor} proposed an improvement to an agent of {client} from a conversation."),
)  # fmt: skip


def _fk(column: str, table: str, *, on_delete: str) -> str:
    return (
        f"CONSTRAINT fk_{_TABLE}_{column.removesuffix('_id')} FOREIGN KEY (tenant_id, {column}) "
        f"REFERENCES {table} (tenant_id, id) ON DELETE {on_delete}"
    )


def _set_null(column: str) -> str:
    return f"SET NULL ({column})"


#: Lo que se borra con su conversación o su agente; lo que solo se olvida si
#: desaparece el cambio, la fuente o la propuesta a la que llevó.
_FKS = ",\n        ".join(
    (
        _fk("conversation_id", "conversations", on_delete="CASCADE"),
        _fk("agent_id", "agents", on_delete="CASCADE"),
        _fk("applied_change_id", "business_changes", on_delete=_set_null("applied_change_id")),
        _fk(
            "knowledge_document_id",
            "knowledge_documents",
            on_delete=_set_null("knowledge_document_id"),
        ),
        _fk("proposal_id", "proposals", on_delete=_set_null("proposal_id")),
    )
)

STATEMENTS = (
    f"""
    CREATE TABLE {_TABLE} (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        conversation_id uuid NOT NULL,
        message_id uuid NOT NULL,
        agent_id uuid NOT NULL,
        author_client_user_id varchar(64) NOT NULL,
        origin varchar(16) NOT NULL,
        scope varchar(16) NOT NULL,
        kind varchar(16) NOT NULL,
        lesson text NOT NULL,
        paraphrase text,
        pii jsonb NOT NULL DEFAULT '[]'::jsonb,
        status varchar(16) NOT NULL DEFAULT 'draft',
        revision integer NOT NULL DEFAULT 1,
        applied_change_id uuid,
        knowledge_document_id uuid,
        proposal_id uuid,
        idempotency_key varchar(80),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        sent_at timestamptz,
        undone_at timestamptz,
        CONSTRAINT uq_{_TABLE}_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_{_TABLE}_origin CHECK (origin IN ('lite_web', 'app')),
        CONSTRAINT ck_{_TABLE}_scope CHECK (scope IN ('business', 'agent')),
        CONSTRAINT ck_{_TABLE}_kind CHECK (kind IN ('data', 'behavior')),
        CONSTRAINT ck_{_TABLE}_status CHECK (
            status IN ('draft', 'applied', 'proposed', 'accepted', 'rejected', 'undone')
        ),
        CONSTRAINT ck_{_TABLE}_lesson CHECK (char_length(lesson) BETWEEN 1 AND 2000),
        CONSTRAINT ck_{_TABLE}_paraphrase CHECK (
            paraphrase IS NULL OR char_length(paraphrase) <= 300
        ),
        CONSTRAINT ck_{_TABLE}_pii CHECK (jsonb_typeof(pii) = 'array'),
        CONSTRAINT ck_{_TABLE}_revision CHECK (revision >= 1),
        {_FKS}
    )
    """,
    f"CREATE INDEX ix_{_TABLE}_agent ON {_TABLE} (tenant_id, agent_id, status, created_at DESC)",
    f"CREATE INDEX ix_{_TABLE}_conversation ON {_TABLE} (tenant_id, conversation_id)",
    f"CREATE UNIQUE INDEX uq_{_TABLE}_idempotency ON {_TABLE} "
    "(tenant_id, author_client_user_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
)


def _modules(condition: str) -> None:
    op.drop_constraint("ck_client_access_modules", "client_access", type_="check")
    op.create_check_constraint("ck_client_access_modules", "client_access", condition)


def upgrade() -> None:
    _modules(f"modules <@ ARRAY[{_MODULES_AFTER}]::varchar[]")
    for statement in STATEMENTS:
        op.execute(statement)
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_TABLE}_tenant_isolation ON {_TABLE} USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {_TABLE} TO nexus_app")
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
    op.execute(f"DROP TABLE IF EXISTS {_TABLE} CASCADE")
    op.execute(
        "UPDATE client_access SET modules = "
        "array_remove(array_remove(modules, 'agents'), 'business')"
    )
    _modules(f"modules <@ ARRAY[{_MODULES_BEFORE}]::varchar[]")
