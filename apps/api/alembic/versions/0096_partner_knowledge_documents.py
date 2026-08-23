"""Playbook del partner — ``partner_knowledge_documents`` (Fase 3 RAG).

Segunda partición, no un scope en ``knowledge_documents``. FORCE RLS por
``app.partner_id`` (mismo fail-closed que ``partner_wallets`` 0094): sin
GUC, cero filas. CASCADE al borrar el partner. Borrar un cliente no toca
esta tabla.

Revision ID: 0096_partner_knowledge_documents
Revises: 0095_gpt56_respond_catalog
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0096_partner_knowledge_documents"
down_revision: str | Sequence[str] | None = "0095_gpt56_respond_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "partner_knowledge_documents"
_POLICY = f"{_TABLE}_partner_isolation"
_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"


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
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE", name="fk_pkd_partner"),
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
        sa.CheckConstraint("kind IN ('file','url')", name="ck_pkd_kind"),
        sa.CheckConstraint("status IN ('pending','indexed','failed')", name="ck_pkd_status"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_pkd_size"),
        sa.CheckConstraint("chunk_count >= 0", name="ck_pkd_chunks"),
    )
    op.create_index(f"ix_{_TABLE}_partner_id", _TABLE, ["partner_id"])
    op.create_index(f"ix_{_TABLE}_partner_status", _TABLE, ["partner_id", "status"])

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE}
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {_TABLE} TO nexus_app"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_index(f"ix_{_TABLE}_partner_status", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_partner_id", table_name=_TABLE)
    op.drop_table(_TABLE)
