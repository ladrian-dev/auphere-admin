"""Identidad de la consola de partners **dentro de la API**.

Supersede parcialmente ADR-030 D2. Hasta ahora la consola (`apps/console`)
tenía su propia base de datos: better-auth + Drizzle sobre el esquema
``console_auth`` (tablas ``user``/``session``/``account``/``verification``)
y una consulta SQL directa a ``public.partner_memberships`` para resolver
el principal. Eso obliga a que Vercel alcance la Postgres, y la Aurora de
producción es privada (`infra/terraform/10-data/aurora.tf`). La consola
deja de tener base de datos: **todo pasa por la API**.

Dos tablas, ambas de PLATAFORMA (sin ``tenant_id``, sin RLS — no son datos
de un tenant, son las credenciales de las personas del partner):

- ``console_auth.principals`` — la persona: correo, hash de contraseña,
  idioma, y el contador de intentos fallidos con su bloqueo temporal.
- ``console_auth.principal_sessions`` — la sesión opaca: se guarda **solo**
  el SHA-256 del token (mismo patrón que ``api_keys.key_hash``), de modo
  que un volcado de esta tabla no permite entrar en ninguna cuenta.

Decisiones que se ven en el esquema:

- **Nombres nuevos, esquema compartido.** Las tablas de better-auth siguen
  existiendo en el ``console_auth`` de las bases locales; esta migración no
  las toca (en staging/producción nunca llegaron a crearse). Por eso las
  tablas se llaman ``principals``/``principal_sessions`` y no ``user``/
  ``session``: convivir es más barato que coordinar un borrado.
- **``email`` es ``varchar`` + índice único sobre ``lower(email)``**, no
  ``citext``: la extensión está disponible pero NO instalada en la base
  local, y crearla en Aurora exige ``rds_superuser``. El código normaliza a
  minúsculas antes de escribir; el índice lo impone.
- **La pertenencia sigue siendo ``public.partner_memberships``** (0080), la
  única verdad. ``principals.id`` es el ``user_id`` textual de esa tabla:
  la unión sigue siendo por texto, sin FK, exactamente como estaba.
- **Sin grant a ``nexus_app``.** Estas tablas solo las toca la API con el
  rol dueño, en endpoints que no cambian de rol. El rol degradado del
  runtime no tiene por qué ver contraseñas.
- **``downgrade()`` real**, pero NO borra el esquema: puede contener las
  tablas viejas de better-auth.

Revision ID: 0088_console_identity
Revises: 0087_usage_alerts
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID

from alembic import op

revision: str = "0088_console_identity"
down_revision: str | Sequence[str] | None = "0087_usage_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "console_auth"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "principals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        # ``scrypt$n$r$p$<salt_b64>$<hash_b64>`` — el formato lleva los
        # parámetros para poder subirlos sin migrar filas.
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("locale", sa.String(5), nullable=False, server_default="es"),
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
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # Unicidad case-insensitive sin ``citext``.
    op.create_index(
        "uq_console_principals_email",
        "principals",
        [sa.text("lower(email)")],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "principal_sessions",
        # SHA-256 hex del token opaco. El token en claro solo existe en la
        # cookie del navegador y en la respuesta del login.
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "principal_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ip", INET(), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_console_sessions_principal",
        "principal_sessions",
        ["principal_id"],
        schema=SCHEMA,
    )
    # Barrido de caducadas (se hace de forma oportunista al crear sesión).
    op.create_index(
        "ix_console_sessions_expires",
        "principal_sessions",
        ["expires_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_console_sessions_expires", table_name="principal_sessions", schema=SCHEMA)
    op.drop_index("ix_console_sessions_principal", table_name="principal_sessions", schema=SCHEMA)
    op.drop_table("principal_sessions", schema=SCHEMA)
    op.drop_index("uq_console_principals_email", table_name="principals", schema=SCHEMA)
    op.drop_table("principals", schema=SCHEMA)
    # El esquema NO se borra: puede contener las tablas de better-auth de
    # una base local anterior a este cambio.
