"""CP-15 · documentos y URLs de conocimiento por cliente (carril A).

Tabla ``knowledge_documents``, tenant-scoped con RLS **forzada** (mismo
patrón que ``tenant_connectors``): el runtime la lee sin ``WHERE
tenant_id`` apoyándose en la policy, y ningún rol —ni el dueño— la ve por
encima del tenant. FK a ``tenants`` con ``ON DELETE CASCADE`` para que
``test_22_tenant_delete_leaves_nothing`` tenga su camino de borrado.

v1 sin pgvector: se guarda el texto extraído (``content_text``) y el
worker lo inyecta en el prompt con tope de caracteres. ``s3_key`` y
``chunk_count`` quedan preparados para la evolución a búsqueda semántica.

Revision ID: 0085_knowledge_documents
Revises: 0084_console_audit_events
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0085_knowledge_documents"
down_revision: str | Sequence[str] | None = "0084_console_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "knowledge_documents"
_POLICY = f"{_TABLE}_tenant_isolation"
_TENANT_MATCH = "tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE", name="fk_kd_tenant"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("s3_key", sa.String(512), nullable=True),
        sa.Column("mime", sa.String(120), nullable=False, server_default="text/plain"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("kind IN ('file','url')", name="ck_kd_kind"),
        sa.CheckConstraint("status IN ('pending','indexed','failed')", name="ck_kd_status"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_kd_size"),
        sa.CheckConstraint("chunk_count >= 0", name="ck_kd_chunks"),
    )
    op.create_index(f"ix_{_TABLE}_tenant_id", _TABLE, ["tenant_id"])
    op.create_index(f"ix_{_TABLE}_tenant_status", _TABLE, ["tenant_id", "status"])

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_POLICY} ON {_TABLE} USING ({_TENANT_MATCH}) WITH CHECK ({_TENANT_MATCH})"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_index(f"ix_{_TABLE}_tenant_status", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_tenant_id", table_name=_TABLE)
    op.drop_table(_TABLE)
