"""La petición de restablecer contraseña — spec 011, Requisito 1.

**La única migración de la spec.** Una tabla en la partición de identidad, y
nada más: la retirada de acceso que el canje compone (R3) ya tiene su
vocabulario sembrado por 0124 y su motivo de archivado cerrado por el CHECK de
0107, así que aquí no se inventa ninguno de los dos.

Tres decisiones de forma, heredadas de las dos tablas hermanas que ya están en
producción:

* **El hash, no el enlace** (``SignupRequest``, 0118). Un volcado de esta tabla
  no restablece ninguna contraseña. Índice único sobre ``token_hash`` porque
  buscar una petición es buscar exactamente eso.
* **``used_at`` en vez de borrar la fila** (``session_codes``, 0122). Borrar
  haría indistinguible «ya usado» de «no existió», y esa indistinguibilidad
  tiene que decidirla la respuesta (R5.3), no la tabla.
* **``ON DELETE CASCADE`` hacia ``principals``**: una petición sin cuenta
  detrás no es nada que valga la pena conservar.

**Sin índice único parcial de «una viva por cuenta»**, por la misma razón que
``session_codes``: pedir otro enlace **invalida** el anterior (R1.6), no falla.
Un único devolvería un error de base de datos donde lo correcto es una
sustitución silenciosa.

Revision ID: 0128_password_reset_requests
Revises: 0127_teammate_instructions
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0128_password_reset_requests"
down_revision: str | Sequence[str] | None = "0127_teammate_instructions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("console_auth.principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        schema="console_auth",
    )
    op.create_index(
        "uq_password_reset_token_hash",
        "password_reset_requests",
        ["token_hash"],
        unique=True,
        schema="console_auth",
    )
    op.create_index(
        "ix_password_reset_account",
        "password_reset_requests",
        ["account_id"],
        schema="console_auth",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_account",
        table_name="password_reset_requests",
        schema="console_auth",
    )
    op.drop_index(
        "uq_password_reset_token_hash",
        table_name="password_reset_requests",
        schema="console_auth",
    )
    op.drop_table("password_reset_requests", schema="console_auth")
