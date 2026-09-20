"""El subdirectorio de una ejecución local, que se validaba y se tiraba.

**El defecto.** ``shell_local`` acepta ``cwd_relative`` y la puerta lo comprueba
contra fugas —ni rutas absolutas, ni ``~``, ni ``..`` — antes de dejar pasar
nada. La máquina, al otro lado, sabe resolverlo dentro del directorio declarado
(``resolveDirInside``). Entre medias no había **dónde guardarlo**: la fila de
``local_executions`` no tenía la columna y el poll mandaba ``cwd_relative: None``
escrito a mano.

Resultado: todo corría en la raíz del directorio del cliente, por muy bien que
el modelo pidiera otra cosa, y sin decírselo a nadie. Validar un dato y después
tirarlo es peor que no aceptarlo — el gate cobra el precio de la comprobación y
el producto no entrega la capacidad.

**Nullable y sin backfill, a propósito.** ``NULL`` **es** la raíz del
directorio, que es exactamente lo que hicieron todas las filas anteriores. No
hay nada que reconstruir ni valor por defecto que inventar: el histórico ya
dice la verdad.

**Por qué no lleva CHECK.** La validación de fugas vive en la puerta
(``local_exec_gate._escapes_workdir``) y la resolución real, en la máquina, que
es la única que puede comprobar symlinks y carreras contra un sistema de
ficheros concreto. Un CHECK aquí sería una tercera copia de una regla que ya
tiene dos dueños, y la más débil de las tres: no sabe de enlaces.

Revision ID: 0123_local_execution_cwd
Revises: 0122_session_codes
Create Date: 2026-09-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0123_local_execution_cwd"
down_revision = "0122_session_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "local_executions",
        sa.Column("cwd_relative", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("local_executions", "cwd_relative")
