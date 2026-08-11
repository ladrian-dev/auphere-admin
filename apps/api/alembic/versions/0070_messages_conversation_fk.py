"""Restaurar la FK de ``messages`` que 0063 perdió sin querer — y con ella
el borrado GDPR.

``0063_messages_partitioned`` construyó la tabla nueva con::

    CREATE TABLE messages_new (LIKE messages INCLUDING DEFAULTS INCLUDING GENERATED)

``LIKE`` **no copia constraints** salvo que se pida ``INCLUDING
CONSTRAINTS``. El docstring de 0063 documenta a conciencia la FK ENTRANTE
que se dropea (``broadcast_recipients.message_id``, imposible contra una
clave no única), pero la SALIENTE se perdió en silencio: ``messages`` quedó
con su PRIMARY KEY y nada más.

Por qué importa más de lo que parece — la cadena del borrado de tenant:

    tenants ──CASCADE──> conversations ──(FK PERDIDA)──> messages

``DELETE /admin/tenants/{id}`` se apoya en el CASCADE de la base. Con el
eslabón roto, borrar un tenant elimina sus conversaciones y **deja sus
mensajes para siempre**, con el `tenant_id` de un tenant que ya no existe.
Es exactamente lo que el criterio de aceptación del WP de GDPR prohíbe
("cero filas con su tenant_id en todas las tablas"), y lo que la web y el
DPA prometen. Reproducido el 2026-08-09: borrar 50 tenants sintéticos dejó
200.000 mensajes huérfanos.

Producción (Railway) todavía NO ha corrido 0063, así que allí la FK sigue
viva: esta migración impide que la pérdida llegue a producción con WP-26.

Sobre los huérfanos previos: se borran antes de crear la constraint. No es
una decisión difícil — un mensaje cuya conversación ya no existe no es
alcanzable por ninguna consulta de la aplicación (todas parten de la
conversación o del tenant) y, en el caso que nos ocupa, es precisamente el
dato que debería haberse borrado. Se cuenta y se anota en el log antes de
borrar. **No se puede usar ``NOT VALID``**: Postgres no admite claves
foráneas sin validar sobre una tabla particionada.

Revision ID: 0070_messages_conversation_fk
Revises: 0069_partition_rls_inherit
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0070_messages_conversation_fk"
down_revision: str | Sequence[str] | None = "0069_partition_rls_inherit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "messages_conversation_id_fkey"


def upgrade() -> None:
    bind = op.get_bind()

    orphans = bind.exec_driver_sql(
        """
        SELECT count(*) FROM messages m
        WHERE NOT EXISTS (SELECT 1 FROM conversations c WHERE c.id = m.conversation_id)
        """
    ).scalar_one()
    if orphans:
        print(
            f"0070: {orphans} mensajes huérfanos (su conversación ya no existe) "
            "se borran antes de restaurar la clave foránea"
        )
        op.execute(
            """
            DELETE FROM messages m
            WHERE NOT EXISTS (SELECT 1 FROM conversations c WHERE c.id = m.conversation_id)
            """
        )

    op.execute(
        f"""
        ALTER TABLE messages
        ADD CONSTRAINT {CONSTRAINT_NAME}
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE messages DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}")
