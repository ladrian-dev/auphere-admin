"""Backfill ``operator_auth`` when 0089 was skipped (stamp jumped 0088→0090).

Staging applied 0090 before 0089 existed, so Alembic never ran
``0089_operator_identity``. 0100 FKs to ``operator_auth.principals`` then
fail. Numbered 0104 because origin already took 0102/0103 (almacenista).
This revision copies 0089's DDL as-is, only if the schema is
absent. No RLS, no FORCE, no grant to ``nexus_app``, no BYPASSRLS.
Does not rewrite 0089 or 0100.

Revision ID: 0104_operator_auth_if_missing
Revises: 0103_local_catalog_products
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID

from alembic import op

revision: str = "0104_operator_auth_if_missing"
down_revision: str | Sequence[str] | None = "0103_local_catalog_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "operator_auth"


def _schema_exists() -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'operator_auth')")
        ).scalar()
    )


def upgrade() -> None:
    if _schema_exists():
        return

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
        # ``scrypt$n$r$p$<salt_b64>$<hash_b64>`` — ver services/identity.py.
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
        # El rol que hoy vive en ``auth.user.role``. CHECK y no ENUM: añadir
        # un valor a un ENUM de Postgres es una migración con bloqueo, y esta
        # lista se va a mover.
        sa.Column("role", sa.String(32), nullable=False, server_default="qa_operator"),
        sa.CheckConstraint(
            "role IN ('admin', 'qa_operator', 'viewer')",
            name="ck_operator_principals_role",
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        # Revocación sin borrado: la fila sobrevive para que el rastro de
        # auditoría siga resolviendo, pero no abre sesión ni la mantiene.
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # Unicidad case-insensitive sin ``citext`` — misma razón que en 0088:
    # la extensión no está instalada en la base local y crearla en Aurora
    # exige ``rds_superuser``.
    op.create_index(
        "uq_operator_principals_email",
        "principals",
        [sa.text("lower(email)")],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "principal_sessions",
        # La PK es el hash del token: buscar una sesión es un índice único
        # sobre 64 caracteres, y un volcado de la tabla no permite entrar en
        # ninguna cuenta (mismo patrón que ``api_keys``).
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
        "ix_operator_sessions_principal", "principal_sessions", ["principal_id"], schema=SCHEMA
    )
    # Lo usa el barrido oportunista de sesiones caducadas al crear una nueva.
    op.create_index(
        "ix_operator_sessions_expires", "principal_sessions", ["expires_at"], schema=SCHEMA
    )

    # **Sin grant a ``nexus_app``**, igual que 0088: estas tablas solo las
    # toca la API con el rol dueño, en endpoints que no cambian de rol. El
    # rol degradado del runtime no tiene por qué ver contraseñas.


def downgrade() -> None:
    # 0089 owns this schema on DBs that already ran it. Do not DROP here.
    return
