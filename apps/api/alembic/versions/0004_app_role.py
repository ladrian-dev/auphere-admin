"""create nexus_app role for RLS-subject runtime queries

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-08

The `nexus` user that runs migrations is a Postgres superuser, which bypasses
RLS unconditionally. Production and tests must execute application queries
under a non-super role so RLS policies apply.

We create a NOLOGIN role `nexus_app` and grant it the privileges it needs.
Application code issues `SET LOCAL ROLE nexus_app` (alongside `set_config`
for `app.tenant_id`) on every transaction.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_app') THEN
                CREATE ROLE nexus_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    # Allow the connecting user (nexus) to assume this role via SET ROLE.
    op.execute("GRANT nexus_app TO nexus")
    op.execute("GRANT USAGE ON SCHEMA public TO nexus_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nexus_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nexus_app")
    # Future tables created by later migrations also get the grant.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nexus_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO nexus_app"
    )
    # The webhook resolver function is SECURITY DEFINER → runs as the function
    # owner (nexus). Make sure nexus_app can call it.
    op.execute("GRANT EXECUTE ON FUNCTION resolve_channel_tenant(text, text) TO nexus_app")


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM nexus_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM nexus_app"
    )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM nexus_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM nexus_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM nexus_app")
    op.execute("REVOKE nexus_app FROM nexus")
    op.execute("DROP ROLE IF EXISTS nexus_app")
