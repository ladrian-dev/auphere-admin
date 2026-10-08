"""Lo que la Bandeja guarda del negocio — spec 030, iteración 2.

Cuatro tablas por cliente, todas con RLS ``FORCE`` por ``tenant_id``:

* ``inbox_reads`` — hasta dónde leyó cada persona cada conversación, y si la
  marcó como no leída. *Sin leer* = hay un entrante posterior a ``read_at``.
* ``conversation_tags`` — etiquetas del negocio en una conversación. Únicas sin
  distinguir mayúsculas.
* ``contact_notes`` — la nota interna de un contacto. **No la lee nadie fuera
  de la Bandeja**: ni el worker ni los servidores MCP (barrido
  ``test_contact_notes_never_reach_agent.py``). Ni la recibe el contacto ni
  llega al agente.
* ``saved_replies`` — respuestas guardadas del negocio. Borrar es archivar
  (``archived_at``): constitución §IV, «borrar no existe».

Revision ID: 0150_inbox_tables
Revises: 0149_inbox_conversations
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0150_inbox_tables"
down_revision: str | Sequence[str] | None = "0149_inbox_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
_TABLES = ("inbox_reads", "conversation_tags", "contact_notes", "saved_replies")


def _tenant() -> sa.Column[object]:
    return sa.Column(
        "tenant_id",
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )


def _conversation() -> sa.Column[object]:
    return sa.Column(
        "conversation_id",
        UUID(as_uuid=True),
        sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )


def _now(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        "inbox_reads",
        _tenant(),
        _conversation(),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_unread", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("conversation_id", "user_id", name="pk_inbox_reads"),
    )
    op.create_table(
        "conversation_tags",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        _tenant(),
        _conversation(),
        sa.Column("tag", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=True),
        _now("created_at"),
        sa.CheckConstraint("length(btrim(tag)) > 0", name="ck_conversation_tags_not_blank"),
    )
    op.create_index(
        "uq_conversation_tags_tag",
        "conversation_tags",
        ["conversation_id", sa.text("lower(tag)")],
        unique=True,
    )
    op.create_index("ix_conversation_tags_tenant", "conversation_tags", ["tenant_id"])
    op.create_table(
        "contact_notes",
        _tenant(),
        sa.Column(
            "customer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(320), nullable=True),
        _now("updated_at"),
        sa.CheckConstraint("length(body) <= 4000", name="ck_contact_notes_length"),
    )
    op.create_table(
        "saved_replies",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        _tenant(),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(body) <= 1000", name="ck_saved_replies_length"),
    )
    op.create_index("ix_saved_replies_tenant", "saved_replies", ["tenant_id"])
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} {_POLICY}")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.drop_table(table)
