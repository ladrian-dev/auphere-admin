"""Console principals — ``partner_memberships`` + ``partner_invitations``.

PLAN-CONSOLE-V1, CP-02. Hoy ``auth.user`` (el Better Auth del admin) no
tiene ninguna relación con ``partners``: dar el panel a un partner es
darle los tenants de todos. Estas dos tablas son la relación que falta,
y son la primera pieza del camino nuevo:

    sesión de la consola → membership → partner_id + rol → JWT de 60 s →
    ``require_console_principal`` → ``partner_tenants`` → RLS

Decisiones que se ven en el esquema:

- **Sin FK a las tablas de Better Auth.** La consola guarda su usuario en
  el esquema ``console_auth`` (Drizzle); Alembic no lo toca. La unión es
  por ``user_id`` textual. ``email``/``display_name`` se copian aquí
  porque el backend no tiene grant sobre ese esquema y el listado del
  equipo tiene que poder mostrarlos.
- **``UNIQUE (user_id)``**: en v1 un usuario pertenece a exactamente un
  partner. El acceso de soporte de Auphere a otros partners es
  impersonación auditada (CP-39), nunca una segunda fila.
- **Roles con nombre** (owner/admin/builder/analyst/billing), CHECK con
  nombre. La matriz de permisos vive en código (``core/console_auth.py``).
- **Invitaciones con caducidad de 21 días**, token guardado como SHA-256,
  una sola pendiente por e-mail y partner (índice único parcial).
- **Grants a ``nexus_app``**: solo SELECT, y solo porque el verificador de
  la consola re-comprueba la pertenencia dentro de transacciones que
  pueden ir ya con el rol cambiado. La escritura ocurre siempre desde el
  dueño de la tabla (superficie ``/console/team``), igual que en 0047.
- **``partners.console_enabled``** es la llave por partner (regla 4 del
  plan: la consola vive tras ``NEXUS_CONSOLE_ENABLED`` y se enciende por
  partner). Nace en ``false``: nadie entra hasta que Auphere lo enciende,
  aunque tenga membership. Va aquí y no en 0081 porque decide *quién
  entra*, no *cuánto puede aprovisionar*.
- **El último owner no se puede quedar sin sustituto.** Eso NO se puede
  expresar con un CHECK (es una propiedad del conjunto, no de la fila);
  lo garantiza el repositorio con ``SELECT … FOR UPDATE`` y lo devuelve
  la API como 409. Se documenta aquí para que nadie lo busque en la BD.

Revision ID: 0080_console_principals
Revises: 0079_usage_source
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0080_console_principals"
down_revision: str | Sequence[str] | None = "0079_usage_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES = "('owner', 'admin', 'builder', 'analyst', 'billing')"


def upgrade() -> None:
    op.execute("ALTER TABLE partners ADD COLUMN console_enabled boolean NOT NULL DEFAULT false")

    op.create_table(
        "partner_memberships",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "invited_by",
            UUID(as_uuid=True),
            sa.ForeignKey("partner_memberships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(f"role IN {_ROLES}", name="ck_partner_memberships_role"),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')", name="ck_partner_memberships_status"
        ),
    )
    op.create_index("uq_partner_memberships_user", "partner_memberships", ["user_id"], unique=True)
    op.create_index("ix_partner_memberships_partner", "partner_memberships", ["partner_id"])

    op.create_table(
        "partner_invitations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "invited_by",
            UUID(as_uuid=True),
            sa.ForeignKey("partner_memberships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_membership_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partner_memberships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(f"role IN {_ROLES}", name="ck_partner_invitations_role"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_partner_invitations_status",
        ),
    )
    op.create_index(
        "uq_partner_invitations_pending_email",
        "partner_invitations",
        ["partner_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_partner_invitations_partner", "partner_invitations", ["partner_id"])

    op.execute("GRANT SELECT ON partner_memberships, partner_invitations TO nexus_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON partner_memberships, partner_invitations FROM nexus_app")
    op.drop_index("ix_partner_invitations_partner", table_name="partner_invitations")
    op.drop_index("uq_partner_invitations_pending_email", table_name="partner_invitations")
    op.drop_table("partner_invitations")
    op.drop_index("ix_partner_memberships_partner", table_name="partner_memberships")
    op.drop_index("uq_partner_memberships_user", table_name="partner_memberships")
    op.drop_table("partner_memberships")
    op.execute("ALTER TABLE partners DROP COLUMN IF EXISTS console_enabled")
