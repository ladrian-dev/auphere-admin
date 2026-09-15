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
* **``code_challenge`` ata el código a quien lo pidió, y es PKCE (RFC 7636).**
  La columna llegó a llamarse ``machine_hint`` y a guardar un ``hostname``
  hasheado; se retiró al ver que el navegador no conoce la máquina, y vuelve con
  el nombre que le da el estándar. Lo que ata ahora no es *dónde* estás sino
  *que tienes el secreto*: el ``code_verifier`` se genera en la aplicación y no
  sale de su proceso, así que un código visto en la URL del retorno no le sirve
  a nadie más.
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
        sa.Column("code_challenge", sa.String(128), nullable=False),
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
