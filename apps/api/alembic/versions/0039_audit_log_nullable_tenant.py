"""audit_log.tenant_id nullable — support platform-level audit entries

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-24

Platform-level mutations (creating an Auphere backchannel number,
publishing a global skill, toggling a feature flag) belong in the
audit trail but have no tenant to scope to. Before this migration,
``audit_log.tenant_id`` was NOT NULL via :class:`TenantScopedMixin`,
which forced platform-level writers to either fake a tenant uuid or
skip audit entirely. Both are wrong.

Change: drop NOT NULL on ``audit_log.tenant_id``. RLS stays as-is
(``tenant_id = current_setting('app.tenant_id')``), which returns
FALSE for NULL rows — per-tenant queries will not see platform rows.
A future "platform audit" surface reads with a direct (unscoped)
session, same pattern as ``owner_phone_index``.

The index on ``tenant_id`` keeps working — Postgres BTREE handles NULL
entries fine (default policy: NULLs LAST on ASC ordering).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | Sequence[str] | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "audit_log",
        "tenant_id",
        nullable=True,
    )


def downgrade() -> None:
    # Best-effort: NULL rows would need to be cleaned up first.
    # Leaving them blocks the downgrade — that's intentional because
    # losing platform audit data is worse than blocking a rollback.
    op.execute(
        "DELETE FROM audit_log WHERE tenant_id IS NULL"
    )
    op.alter_column(
        "audit_log",
        "tenant_id",
        nullable=False,
    )
