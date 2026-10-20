"""client_phones — el teléfono de una persona de cliente (spec 031, data-model §0158).

Cada teléfono donde una persona de cliente ha entrado con la app Auphere
Customers. Es identidad: la comprobación de la credencial, el canje y el
registro del destino de avisos la leen sin el rol ``nexus_app`` (research D3).
Todo lo demás la lee bajo la RLS de su cliente, que aquí va **forzada**.

Antes, ``client_memberships`` gana ``UNIQUE (tenant_id, id)``: es lo que deja
que la FK del teléfono sea compuesta. Una FK de una sola columna no pasa por la
RLS y podría atar un teléfono a la membresía de otro cliente.

Revision ID: 0158_client_phones
Revises: 0157_tenant_payments
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

revision: str = "0158_client_phones"
down_revision: str | Sequence[str] | None = "0157_tenant_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
_KINDS = "'client.balance', 'inbox.message_for_you', 'inbox.waiting'"
_REASONS = (
    "'abandoned', 'access_disabled', 'closed_by_auphere', 'closed_by_person', "
    "'member_removed', 'password_reset', 'refresh_reused', 'signed_out'"
)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_client_memberships_tenant_id_id", "client_memberships", ["tenant_id", "id"]
    )
    op.create_table(
        "client_phones",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("partner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_membership_id", UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("install_id", sa.String(64), nullable=False),
        sa.Column("app_version", sa.String(32), nullable=False),
        sa.Column("refresh_hash", sa.LargeBinary, nullable=False),
        sa.Column("refresh_prev_hash", sa.LargeBinary, nullable=True),
        sa.Column("refresh_rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credential_generation", sa.Integer, nullable=False, server_default="1"),
        sa.Column("push_provider", sa.String(8), nullable=True),
        sa.Column("push_token", sa.String(512), nullable=True),
        sa.Column("push_token_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("apns_environment", sa.String(12), nullable=True),
        sa.Column(
            "notice_kinds",
            ARRAY(sa.String(32)),
            nullable=False,
            server_default=sa.text(
                "ARRAY['inbox.waiting','inbox.message_for_you','client.balance']::varchar[]"
            ),
        ),
        sa.Column("locale", sa.String(2), nullable=False, server_default="es"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(24), nullable=True),
        sa.Column("revoked_by", sa.String(320), nullable=True),
        sa.CheckConstraint("platform IN ('android', 'ios')", name="ck_client_phones_platform"),
        sa.CheckConstraint(
            "push_provider IS NULL OR push_provider IN ('apns', 'fcm')",
            name="ck_client_phones_push_provider",
        ),
        sa.CheckConstraint(
            "apns_environment IS NULL OR apns_environment IN ('sandbox', 'production')",
            name="ck_client_phones_apns_environment",
        ),
        sa.CheckConstraint(
            f"notice_kinds <@ ARRAY[{_KINDS}]::varchar[]", name="ck_client_phones_notice_kinds"
        ),
        sa.CheckConstraint("locale IN ('es', 'en')", name="ck_client_phones_locale"),
        sa.CheckConstraint(
            f"revoked_reason IS NULL OR revoked_reason IN ({_REASONS})",
            name="ck_client_phones_revoked_reason",
        ),
        sa.CheckConstraint("length(display_name) <= 80", name="ck_client_phones_display_name"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_client_phones_tenant_id_id"),
    )
    op.execute(
        "ALTER TABLE client_phones ADD CONSTRAINT fk_client_phones_membership "
        "FOREIGN KEY (tenant_id, client_membership_id) "
        "REFERENCES client_memberships (tenant_id, id) ON DELETE CASCADE"
    )
    op.create_index(
        "uq_client_phones_install_live",
        "client_phones",
        ["install_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_client_phones_principal_live",
        "client_phones",
        ["tenant_id", "principal_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_client_phones_push_token_live",
        "client_phones",
        ["push_token"],
        postgresql_where=sa.text("revoked_at IS NULL AND push_token IS NOT NULL"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON client_phones TO nexus_app")
    op.execute("ALTER TABLE client_phones ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE client_phones FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY client_phones_tenant_isolation ON client_phones {_POLICY}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS client_phones_tenant_isolation ON client_phones")
    op.execute("REVOKE ALL ON client_phones FROM nexus_app")
    op.drop_table("client_phones")
    op.drop_constraint(
        "uq_client_memberships_tenant_id_id", "client_memberships", type_="unique"
    )
