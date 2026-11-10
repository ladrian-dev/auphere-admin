"""El conocimiento en dos capas — spec 047, T132 (requisitos 37.1, 38.2 y 38.3;
``data-model.md`` §5 y research D14).

- ``knowledge_documents`` gana ``agent_id`` (nulo = la capa del negocio; FK
  compuesta), ``removed_at``, ``removed_by`` y ``restore_until`` (quitar se deshace
  durante 10 minutos), y el tipo ``note`` («Enseñar»).
- ``knowledge_chunks``: los fragmentos de cada fuente, con su capa y su ``tsv``
  (``spanish``, generado). Índice btree por ``(tenant_id, agent_id)``.
- ``knowledge_chunk_vectors``: el embedding de cada fragmento (``halfvec(1024)``,
  Titan v2), solo si hay quien lo calcule. Tabla aparte y en la fila (``STORAGE
  PLAIN``): cada vía de la búsqueda recorre solo lo suyo. **Sin índice ANN**: la
  búsqueda es exacta sobre las filas del cliente (38.4).
- ``knowledge_revisions``: la revisión de cada capa; subir, quitar o enseñar la sube.
- ``agent_memories`` gana ``agent_id`` (nulo = compartida): un agente con memoria
  propia solo lee y escribe la suya (garantía 9). El disparador de versiones copia
  la columna, y la clave única la incluye.
- ``turn_sources``: las fuentes que usó cada respuesta (38.3).

Revision ID: 0193_knowledge_layers
Revises: 0192_audience_to_channels
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0193_knowledge_layers"
down_revision: str | Sequence[str] | None = "0192_audience_to_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
_AGENT_FK = "FOREIGN KEY (tenant_id, agent_id) REFERENCES agents (tenant_id, id) ON DELETE CASCADE"
_TRIGGER_FN = "agent_memories_audit_trigger_fn"

STATEMENTS = (
    """
    ALTER TABLE knowledge_documents
        ADD COLUMN agent_id uuid,
        ADD COLUMN removed_at timestamptz,
        ADD COLUMN removed_by varchar(255),
        ADD COLUMN restore_until timestamptz,
        ADD CONSTRAINT uq_knowledge_documents_tenant_id UNIQUE (tenant_id, id),
        DROP CONSTRAINT ck_kd_kind,
        ADD CONSTRAINT ck_kd_kind CHECK (kind IN ('file', 'url', 'note'))
    """,
    f"ALTER TABLE knowledge_documents ADD CONSTRAINT fk_kd_agent {_AGENT_FK}",
    "CREATE INDEX ix_knowledge_documents_layer ON knowledge_documents (tenant_id, agent_id)",
    f"""
    CREATE TABLE knowledge_chunks (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        document_id uuid NOT NULL,
        agent_id uuid,
        ordinal integer NOT NULL,
        text text NOT NULL,
        tsv tsvector GENERATED ALWAYS AS (to_tsvector('spanish', text)) STORED,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_knowledge_chunks_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_knowledge_chunks_ordinal UNIQUE (tenant_id, document_id, ordinal),
        CONSTRAINT fk_knowledge_chunks_document FOREIGN KEY (tenant_id, document_id)
            REFERENCES knowledge_documents (tenant_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_knowledge_chunks_agent {_AGENT_FK}
    )
    """,
    "CREATE INDEX ix_knowledge_chunks_layer ON knowledge_chunks (tenant_id, agent_id)",
    f"""
    CREATE TABLE knowledge_chunk_vectors (
        chunk_id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        document_id uuid NOT NULL,
        agent_id uuid,
        embedding halfvec(1024) NOT NULL,
        CONSTRAINT fk_knowledge_chunk_vectors_chunk FOREIGN KEY (tenant_id, chunk_id)
            REFERENCES knowledge_chunks (tenant_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_knowledge_chunk_vectors_agent {_AGENT_FK}
    )
    """,
    "CREATE INDEX ix_knowledge_chunk_vectors_layer ON knowledge_chunk_vectors (tenant_id, agent_id)",
    # La búsqueda es exacta y recorre todos los vectores del cliente: en la fila,
    # sin TOAST (descomprimir 5.000 costaba 28 ms) y en su tabla, para que la vía
    # por palabras no arrastre 2 KB por fragmento.
    "ALTER TABLE knowledge_chunk_vectors ALTER COLUMN embedding SET STORAGE PLAIN",
    """
    CREATE TABLE knowledge_revisions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid,
        rev bigint NOT NULL DEFAULT 0,
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_knowledge_revisions_layer UNIQUE NULLS NOT DISTINCT (tenant_id, agent_id),
        CONSTRAINT fk_knowledge_revisions_agent FOREIGN KEY (tenant_id, agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE CASCADE
    )
    """,
    f"""
    ALTER TABLE agent_memories
        ADD COLUMN agent_id uuid,
        ADD CONSTRAINT fk_agent_memories_agent {_AGENT_FK}
    """,
    "ALTER TABLE agent_memory_versions ADD COLUMN agent_id uuid",
    "DROP INDEX IF EXISTS uq_agent_memories_tenant_customer_path",
    """
    CREATE UNIQUE INDEX uq_agent_memories_tenant_customer_path
        ON agent_memories (
            tenant_id, COALESCE(agent_id::text, '_shared'), COALESCE(customer_id::text, '_tenant'), path
        )
    """,
    f"""
    CREATE OR REPLACE FUNCTION {_TRIGGER_FN}()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        IF (TG_OP = 'INSERT') THEN
            INSERT INTO agent_memory_versions (
                memory_id, tenant_id, customer_id, agent_id, path, content, operation
            ) VALUES (
                NEW.id, NEW.tenant_id, NEW.customer_id, NEW.agent_id, NEW.path,
                NEW.content, 'insert'
            );
            RETURN NEW;
        ELSIF (TG_OP = 'UPDATE') THEN
            INSERT INTO agent_memory_versions (
                memory_id, tenant_id, customer_id, agent_id, path, content, operation
            ) VALUES (
                NEW.id, NEW.tenant_id, NEW.customer_id, NEW.agent_id, NEW.path,
                NEW.content, 'update'
            );
            RETURN NEW;
        ELSIF (TG_OP = 'DELETE') THEN
            INSERT INTO agent_memory_versions (
                memory_id, tenant_id, customer_id, agent_id, path, content, operation
            ) VALUES (
                OLD.id, OLD.tenant_id, OLD.customer_id, OLD.agent_id, OLD.path,
                OLD.content, 'delete'
            );
            RETURN OLD;
        END IF;
        RETURN NULL;
    END;
    $$
    """,
    f"""
    CREATE TABLE turn_sources (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        message_id uuid NOT NULL,
        agent_id uuid,
        sources jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_turn_sources_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_turn_sources_message UNIQUE (tenant_id, message_id),
        CONSTRAINT fk_turn_sources_agent {_AGENT_FK}
    )
    """,
)
TENANT_TABLES = (
    "knowledge_chunks",
    "knowledge_chunk_vectors",
    "knowledge_revisions",
    "turn_sources",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} USING {_POLICY} WITH CHECK {_POLICY}"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_TRIGGER_FN}()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF (TG_OP = 'INSERT') THEN
                INSERT INTO agent_memory_versions (
                    memory_id, tenant_id, customer_id, path, content, operation
                ) VALUES (NEW.id, NEW.tenant_id, NEW.customer_id, NEW.path, NEW.content, 'insert');
                RETURN NEW;
            ELSIF (TG_OP = 'UPDATE') THEN
                INSERT INTO agent_memory_versions (
                    memory_id, tenant_id, customer_id, path, content, operation
                ) VALUES (NEW.id, NEW.tenant_id, NEW.customer_id, NEW.path, NEW.content, 'update');
                RETURN NEW;
            ELSIF (TG_OP = 'DELETE') THEN
                INSERT INTO agent_memory_versions (
                    memory_id, tenant_id, customer_id, path, content, operation
                ) VALUES (OLD.id, OLD.tenant_id, OLD.customer_id, OLD.path, OLD.content, 'delete');
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_agent_memories_tenant_customer_path")
    op.execute("DELETE FROM agent_memories WHERE agent_id IS NOT NULL")
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_memories_tenant_customer_path ON agent_memories "
        "(tenant_id, COALESCE(customer_id::text, '_tenant'), path)"
    )
    op.execute("ALTER TABLE agent_memory_versions DROP COLUMN IF EXISTS agent_id")
    op.execute(
        "ALTER TABLE agent_memories DROP CONSTRAINT IF EXISTS fk_agent_memories_agent, "
        "DROP COLUMN IF EXISTS agent_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_knowledge_documents_layer")
    op.execute("DELETE FROM knowledge_documents WHERE kind = 'note'")
    op.execute(
        """
        ALTER TABLE knowledge_documents
            DROP CONSTRAINT IF EXISTS fk_kd_agent,
            DROP CONSTRAINT IF EXISTS uq_knowledge_documents_tenant_id,
            DROP CONSTRAINT IF EXISTS ck_kd_kind,
            ADD CONSTRAINT ck_kd_kind CHECK (kind IN ('file', 'url')),
            DROP COLUMN IF EXISTS restore_until,
            DROP COLUMN IF EXISTS removed_by,
            DROP COLUMN IF EXISTS removed_at,
            DROP COLUMN IF EXISTS agent_id
        """
    )
