"""El código de un solo uso que trae una sesión de Google a la aplicación
(spec 009, Requisitos 3, 4 y 5).

**Se parece al código de emparejamiento y ata algo distinto.** Aquel ata una
MÁQUINA y entrega una credencial de dispositivo; éste ata una PERSONA y entrega
una sesión. Se teclean igual —mismo alfabeto, misma longitud, mismos diez
minutos— porque la persona los escribe en la misma hoja de la misma barra, y dos
formatos distintos para el mismo gesto no los sabría explicar nadie.

Tres decisiones de forma, y ninguna es de estilo:

* **La PK es el hash**, como en ``principal_sessions``, cuyo docstring lo dice
  mejor: «un volcado de la tabla no permite entrar en ninguna cuenta».
* **No hay columna de máquina.** La tabla llegó a tener una para atar el código
  a quien lo pidió; se retiró al ver que no hay a qué atarlo — el código nace en
  el navegador del sistema, que no conoce el Mac donde corre la aplicación. Una
  columna que nadie lee parece una protección que nadie tiene. Lo que queda
  protegiendo el código son los diez minutos y el uso único, y lo que se registra
  del canje es lo que ``principal_sessions`` ya guarda: ``ip`` y ``user_agent``.
* **``consumed_at`` en vez de borrar la fila.** Borrar haría indistinguible «ya
  usado» de «no existió», y esa indistinguibilidad tiene que ser una decisión de
  la RESPUESTA (R4.5), no un efecto de la tabla. Con la fila delante el servidor
  elige qué contesta; sin ella no puede elegir. Y es lo que permite auditar que
  un código se usó (R5.5).

**Sin índice único parcial para «uno vivo por persona».** Un único devolvería un
error de base de datos donde lo correcto es una sustitución silenciosa: pedir
otro código invalida el anterior, no falla.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from collections.abc import Sequence

revision: str = "0122_session_codes"
down_revision: str | Sequence[str] | None = "0121_companion_run_native_input"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column(
            "principal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("console_auth.principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        schema="console_auth",
    )
    op.create_index(
        "ix_session_codes_principal",
        "session_codes",
        ["principal_id"],
        schema="console_auth",
    )
    op.create_index(
        "ix_session_codes_expires",
        "session_codes",
        ["expires_at"],
        schema="console_auth",
    )


def downgrade() -> None:
    op.drop_index("ix_session_codes_expires", table_name="session_codes", schema="console_auth")
    op.drop_index("ix_session_codes_principal", table_name="session_codes", schema="console_auth")
    op.drop_table("session_codes", schema="console_auth")
