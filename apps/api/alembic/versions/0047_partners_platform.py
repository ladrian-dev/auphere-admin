"""partner platform — partners, api_keys, partner_tenants, embed_audit_log

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-05

ADR-028 — embed widget partner platform, phase 0 foundations.

Platform tables (NOT tenant-scoped, no RLS — same trust model as
``tenants``): they are reachable only from the ``/v1/partners/*``
surface (secret API key auth), the embed session JWT verifier and the
admin panel.

- ``partners`` — SaaS companies embedding ``@auphere/embed``.
- ``api_keys`` — secret keys, SHA-256 stored, shown-once, rotation with
  grace window, instant fail-closed revocation.
- ``partner_tenants`` — THE isolation boundary. Maps the partner's own
  client id (``external_client_ref``) to our tenant. A widget session
  can only be minted through this mapping under the authenticated
  partner's id — never from browser input.
- ``embed_audit_log`` — append-only (SELECT+INSERT grants only).

Also adds the ``provisioning`` value to ``tenant_status``: partner
client provisioning creates tenants just-in-time, before any WhatsApp
channel exists. PG ≥ 12 allows ALTER TYPE ... ADD VALUE inside the
migration transaction as long as the new value isn't used in the same
transaction (it isn't — first use is at runtime).

Grants to ``nexus_app`` (the RLS-enforced role every scoped request
switches to): SELECT on the three platform tables — the embed JWT
verifier re-checks key liveness and the partner↔tenant mapping inside
tenant-scoped transactions — and SELECT+INSERT on the audit log.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID

from alembic import op

revision: str = "0047_partners_platform"
down_revision: str | Sequence[str] | None = "0046_amigable_cobro_writes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE tenant_status ADD VALUE IF NOT EXISTS 'provisioning'")

    op.create_table(
        "partners",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("broadcast_recipient_cap", sa.Integer, nullable=False, server_default="250"),
        sa.Column("rate_limit_mint_per_min", sa.Integer, nullable=False, server_default="60"),
        sa.Column("rate_limit_embed_per_min", sa.Integer, nullable=False, server_default="600"),
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
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_partners_status"),
    )

    op.create_table(
        "api_keys",
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
        sa.Column("type", sa.String(10), nullable=False, server_default="live"),
        sa.Column("prefix_snippet", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "scopes",
            ARRAY(sa.String(40)),
            nullable=False,
            server_default=sa.text("ARRAY['provision','widget_sessions']::varchar[]"),
        ),
        sa.Column(
            "allowed_origins",
            ARRAY(sa.String(255)),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", INET, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("type IN ('live', 'test')", name="ck_api_keys_type"),
    )
    op.create_index("ix_api_keys_partner_revoked", "api_keys", ["partner_id", "revoked_at"])

    op.create_table(
        "partner_tenants",
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("external_client_ref", sa.String(255), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("client_name", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("partner_id", "tenant_id", name="uq_partner_tenants_partner_tenant"),
    )

    op.create_table(
        "embed_audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("api_key_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip", INET, nullable=True),
        sa.Column("origin", sa.String(255), nullable=True),
        sa.Column("jti", sa.String(40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_embed_audit_partner_created", "embed_audit_log", ["partner_id", "created_at"]
    )
    op.create_index(
        "ix_embed_audit_tenant_created", "embed_audit_log", ["tenant_id", "created_at"]
    )

    # nexus_app (RLS-enforced role) needs read access for the fail-closed
    # re-checks inside tenant-scoped transactions, and INSERT on the audit
    # log. Deliberately NO UPDATE/DELETE on embed_audit_log (append-only)
    # and NO write access to the key/mapping tables (admin surface only,
    # which runs as the table owner).
    op.execute("GRANT SELECT ON partners, api_keys, partner_tenants TO nexus_app")
    op.execute("GRANT SELECT, INSERT ON embed_audit_log TO nexus_app")
    op.execute("GRANT USAGE ON SEQUENCE embed_audit_log_id_seq TO nexus_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON embed_audit_log FROM nexus_app")
    op.execute("REVOKE ALL ON partners, api_keys, partner_tenants FROM nexus_app")
    op.drop_table("embed_audit_log")
    op.drop_table("partner_tenants")
    op.drop_table("api_keys")
    op.drop_table("partners")
    # 'provisioning' stays in tenant_status: PG can't drop enum values and
    # recreating the type would rewrite every tenant row for no gain.
