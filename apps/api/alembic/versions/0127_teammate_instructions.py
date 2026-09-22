"""Instrucciones propias del teammate — spec 015, Requisito 6.

**La única migración de la spec**, y va en el último tramo. Dos cosas:

1. ``teammates.instructions``: texto, **nulo y sin `server_default`**. ``NULL``
   significa «no escritas», que es lo que tienen los teammates que ya existen, y
   el R6.2 depende de esa distinción para garantizar que **nadie tiene que
   reconfigurar nada**. Un ``DEFAULT ''`` convertiría todas las filas en
   «escritas y vacías», que es otra cosa.

2. ``teammate_changes_fields_check``, que enumera los campos permitidos. **Esto
   casi se escapa**: sin ensancharlo, registrar un cambio de instrucciones viola
   la restricción y la edición falla **en producción, no en los tests del camino
   feliz**. Se encontró leyendo el modelo antes de escribir la migración — la
   lección directa de la spec 012, donde el vocabulario de auditoría sembrado
   por migración costó una enmienda a mitad de implementación.

Lo que **no** hace falta y se comprobó leyéndolo: el vocabulario de auditoría no
se toca. ``teammate.updated`` ya existe (``0110_teammate_audit_vocab.py``) y es
la acción que ya se escribe al editar un teammate. Cambia qué campos se nombran,
no qué acción se registra.

El tope de 4.000 caracteres vive en el **esquema de entrada**, no aquí: un tope
de producto que cambie no debería exigir una migración.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0127_teammate_instructions"
down_revision = "0126_drop_pairing_codes"
branch_labels = None
depends_on = None

_CHECK = "teammate_changes_fields_check"
_ANTES = "'job', 'permissions', 'local_exec', 'model'"
_DESPUES = "'job', 'permissions', 'local_exec', 'model', 'instructions'"


def _fields_check(valores: str) -> str:
    return f"fields <@ ARRAY[{valores}]::text[] AND array_length(fields, 1) >= 1"


def upgrade() -> None:
    op.add_column("teammates", sa.Column("instructions", sa.Text(), nullable=True))
    op.drop_constraint(_CHECK, "teammate_changes", type_="check")
    op.execute(
        f"ALTER TABLE teammate_changes ADD CONSTRAINT {_CHECK} CHECK ({_fields_check(_DESPUES)})"
    )


def downgrade() -> None:
    """Bajar no puede dejar el esquema roto, y aquí cuesta algo.

    Al estrechar el ``CHECK``, cualquier fila de ``teammate_changes`` que ya
    nombre ``instructions`` lo violaría. Así que primero se retira ese valor de
    los arrays existentes, y se borran las filas que se queden **sin ningún
    campo** —``array_length >= 1`` es parte de la restricción—.

    Se pierde el registro de que alguien cambió las instrucciones. No se pierde
    ninguna otra fila ni ningún otro campo, y el teammate conserva su historia
    de oficio, permisos, máquina y modelo.
    """
    op.execute("UPDATE teammate_changes SET fields = array_remove(fields, 'instructions')")
    op.execute("DELETE FROM teammate_changes WHERE array_length(fields, 1) IS NULL")
    op.drop_constraint(_CHECK, "teammate_changes", type_="check")
    op.execute(
        f"ALTER TABLE teammate_changes ADD CONSTRAINT {_CHECK} CHECK ({_fields_check(_ANTES)})"
    )
    op.drop_column("teammates", "instructions")
