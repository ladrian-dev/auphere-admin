"""La persona de un cliente — spec 030, Requisitos 1 y 2.

Tres tablas, y la decisión que las separa de las del partner:

* ``client_access`` — si un cliente tiene consola lite y con qué módulos. Una
  fila por cliente, con RLS por tenant como cualquier dato del cliente.
* ``client_memberships`` — una cuenta de consola atada a **un** tenant de un
  partner. Hermana de ``partner_memberships``, **no** un rol más dentro de
  ella: hoy hay código que recorre los miembros del partner (Equipo, correos
  de avisos, plazas por nivel) y con un rol nuevo cada uno tendría que
  acordarse de excluirlo. Con tabla propia, lo que existe sigue siendo
  correcto sin tocarlo (plan D1). Sin RLS por tenant, igual que la del
  partner: se lee por cuenta al resolver la sesión.
* ``client_invitations`` — el enlace de un solo uso para entrar, guardado como
  hash (como ``partner_invitations``).

Una cuenta es de una de las dos tablas de membresía, nunca de las dos: lo
comprueba el servicio bajo bloqueo consultivo y lo fija un test; una
restricción entre tablas no se puede declarar.

Revision ID: 0147_client_access
Revises: 0146_checkout_link_creates_order
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

revision: str = "0147_client_access"
down_revision: str | Sequence[str] | None = "0146_checkout_link_creates_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "client_access",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("modules", ARRAY(sa.String(16)), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_by", sa.String(320), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "modules <@ ARRAY['panel','inbox','usage']::varchar[]",
            name="ck_client_access_modules",
        ),
    )
    op.execute("ALTER TABLE client_access ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE client_access FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY client_access_tenant_isolation ON client_access {_POLICY}")

    op.create_table(
        "client_memberships",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("invited_by", sa.String(320), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_client_memberships_status"),
    )
    op.create_index("uq_client_memberships_user", "client_memberships", ["user_id"], unique=True)
    op.create_index("ix_client_memberships_tenant", "client_memberships", ["tenant_id"])

    op.create_table(
        "client_invitations",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by", sa.String(320), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accepted_membership_id",
            UUID(as_uuid=True),
            sa.ForeignKey("client_memberships.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_client_invitations_status",
        ),
    )
    op.create_index(
        "uq_client_invitations_pending_email",
        "client_invitations",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_client_invitations_tenant", "client_invitations", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("client_invitations")
    op.drop_table("client_memberships")
    op.execute("DROP POLICY IF EXISTS client_access_tenant_isolation ON client_access")
    op.drop_table("client_access")
