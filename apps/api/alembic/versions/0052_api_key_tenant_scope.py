"""api_keys.tenant_id — direct-client keys for the outbound message API

Revision ID: 0052_api_key_tenant_scope
Revises: 0050_partner_provisioning
Create Date: 2026-07-20

Note the parent: ``0050_partner_provisioning`` is the tip of the chain
despite its number — it was rebased onto 0051 to collapse two heads
(commit 795a222). Numeric order is not chain order here.

Until now every API key belonged to a *partner* and resolved its tenant
indirectly, via ``partner_tenants`` + an ``external_client_ref`` supplied
per request. That fits an integrator embedding the widget for many of
its own clients.

It does not fit a direct client — a business that owns one tenant and
wants to POST its own messages from n8n/Zapier/cron. Forcing it through
the partner model would mean inventing a fake partner and making the
caller echo back a client ref it does not have.

So: ``tenant_id`` nullable. Populated → the key IS that tenant and
resolves without a request body field. NULL → the existing partner
behaviour, byte-for-byte unchanged. Purely additive; no backfill, no
change to any key in flight.

The CHECK constraint is the load-bearing part. A tenant-scoped key must
never carry ``provision`` — that scope mints new tenants under a
partner, which is meaningless (and a privilege escalation) for a key
that is supposed to be confined to exactly one tenant. Enforced in the
database because application-layer validation is one refactor away from
being bypassed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0052_api_key_tenant_scope"
down_revision: str | Sequence[str] | None = "0050_partner_provisioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # Auth resolves the key by hash, then reads tenant_id off the row —
    # this index serves the *admin* direction ("which keys does this
    # tenant have?") on the tenant detail page.
    op.create_index(
        "ix_api_keys_tenant_revoked",
        "api_keys",
        ["tenant_id", "revoked_at"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )

    # A key confined to one tenant cannot also provision new ones.
    op.create_check_constraint(
        "ck_api_keys_tenant_scope_no_provision",
        "api_keys",
        "tenant_id IS NULL OR NOT ('provision' = ANY(scopes))",
    )


def downgrade() -> None:
    op.drop_constraint("ck_api_keys_tenant_scope_no_provision", "api_keys", type_="check")
    op.drop_index("ix_api_keys_tenant_revoked", table_name="api_keys")
    op.drop_column("api_keys", "tenant_id")
