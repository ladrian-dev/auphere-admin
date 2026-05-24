"""audit_log RLS — permit platform-level rows (tenant_id IS NULL)

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-24

Migration 0039 made ``audit_log.tenant_id`` nullable so platform-level
actions (Auphere channel CRUD, global skill publish, feature flags)
could be audited without faking a tenant uuid. But the RLS policy
from migration 0002 still says ``tenant_id = current_setting(...)``,
which in Postgres evaluates ``NULL = NULL`` as ``NULL`` (not TRUE)
under WITH CHECK — every platform INSERT was rejected.

This migration drops the original ``audit_log_tenant_isolation``
policy and re-creates it with branches for the two legitimate modes:

- ``app.tenant_id`` IS SET → per-tenant filter, unchanged behaviour
  (tenant queries see only their own rows; platform NULL rows hidden).
- ``app.tenant_id`` IS UNSET (or empty) → "platform" mode, only
  ``tenant_id IS NULL`` rows are visible/insertable.

The other 9 RLS-protected tables stay as-is — only ``audit_log``
gained nullable tenant_id semantics.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0040"
down_revision: str | Sequence[str] | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_POLICY = """
CREATE POLICY audit_log_tenant_isolation ON audit_log
USING (
    -- Per-tenant mode: app.tenant_id is set + matches.
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    OR
    -- Platform mode: app.tenant_id is unset AND row is NULL-tenant.
    (
        (current_setting('app.tenant_id', true) IS NULL
         OR current_setting('app.tenant_id', true) = '')
        AND tenant_id IS NULL
    )
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
    OR
    (
        (current_setting('app.tenant_id', true) IS NULL
         OR current_setting('app.tenant_id', true) = '')
        AND tenant_id IS NULL
    )
)
"""

_OLD_POLICY = """
CREATE POLICY audit_log_tenant_isolation ON audit_log
USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
"""


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_tenant_isolation ON audit_log")
    op.execute(_NEW_POLICY)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_tenant_isolation ON audit_log")
    op.execute(_OLD_POLICY)
