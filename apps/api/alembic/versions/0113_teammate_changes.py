"""Spec 003 — la nota de «este teammate cambió», del partner y no de un hilo.

El Requisito 2.4 pide que, al cambiar el oficio o los permisos de un teammate,
**el hilo de cada persona lo anote**. El plan decía escribir un mensaje
``role=system`` en cada hilo activo, y ahí choca con la garantía que hace
privado el hilo: la RLS de ``companion.messages`` cuelga de
``threads.principal_id``, así que insertar en el hilo de otra persona exige
romper exactamente lo que protege que nadie más lea su conversación (0090).

Así que la nota **no se copia, se deriva**: aquí queda un registro por cambio,
del partner (misma RLS que ``teammates``), y cada hilo lo pinta al cargar. Sale
gratis un efecto que la copia no daba: quien abre la aplicación tres semanas
después ve los cambios que hubo mientras no miraba, aunque su hilo no existiera
cuando ocurrieron.

Qué guarda y qué **no**: los nombres de los campos que cambiaron y quién lo
hizo. Ni valores viejos ni nuevos — la pantalla ya enseña lo que hay hoy, y un
histórico de configuraciones es otra cosa y tendría que decidirse aparte.

Revision ID: 0113_teammate_changes
Revises: 0112_local_exec_policy
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0113_teammate_changes"
down_revision: str | Sequence[str] | None = "0112_local_exec_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "NULLIF(current_setting('app.partner_id', true), '')::uuid"

#: Los campos que cambian lo que el teammate **puede hacer**. Cambiar el nombre
#: no entra: no cambia el catálogo y una nota por eso sería ruido.
CHANGED_FIELDS = ("job", "permissions", "local_exec", "model")


def upgrade() -> None:
    fields = ", ".join(f"'{f}'" for f in CHANGED_FIELDS)
    op.create_table(
        "teammate_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "teammate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teammates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        #: Lista de campos, no un campo por fila: un cambio es un acto, y
        #: partirlo en tres notas contaría tres veces lo que pasó una.
        sa.Column(
            "fields",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        #: Quién lo hizo, con el nombre que tenía entonces. Denormalizado a
        #: propósito: si esa persona deja el partner, la nota sigue diciendo
        #: quién cambió el teammate en vez de quedarse en un id huérfano.
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("changed_by_label", sa.Text(), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            f"fields <@ ARRAY[{fields}]::text[] AND array_length(fields, 1) >= 1",
            name="teammate_changes_fields_check",
        ),
    )
    op.create_index(
        "ix_teammate_changes_teammate_at",
        "teammate_changes",
        ["teammate_id", "changed_at"],
    )
    op.execute("ALTER TABLE teammate_changes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE teammate_changes FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY teammate_changes_partner ON teammate_changes
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )
    # Una nota es un hecho ocurrido: se lee, no se reescribe ni se borra.
    op.execute("REVOKE UPDATE, DELETE ON teammate_changes FROM nexus_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS teammate_changes_partner ON teammate_changes")
    op.drop_index("ix_teammate_changes_teammate_at", table_name="teammate_changes")
    op.drop_table("teammate_changes")
