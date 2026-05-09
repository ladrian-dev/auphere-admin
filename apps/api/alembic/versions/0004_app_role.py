"""create nexus_app role for RLS-subject runtime queries

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-08

The connecting user that runs migrations is a Postgres superuser, which
bypasses RLS unconditionally. Production and tests must execute
application queries under a non-super role so RLS policies apply.

We create a NOLOGIN role `nexus_app` and grant it the privileges it
needs. Application code issues `SET LOCAL ROLE nexus_app` (alongside
`set_config` for `app.tenant_id`) on every transaction.

Note on the connecting username: dev local uses `nexus` (docker-compose
seeds it); Railway managed Postgres uses `postgres`; future managed
providers may use yet another. We resolve the connecting user
dynamically via `current_user` so the migration works on any host.
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
    # Allow the connecting user (whatever it is — dev `nexus`, Railway
    # `postgres`, …) to assume this role via SET ROLE. The DO + format()
    # wraps `current_user` so the GRANT statement, which requires a
    # static identifier, picks up the runtime value. Idempotent: granting
    # the same role to the same user is a no-op.
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT nexus_app TO %I', current_user);
        END
        $$;
        """
    )
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
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE nexus_app FROM %I', current_user);
        END
        $$;
        """
    )
    op.execute("DROP ROLE IF EXISTS nexus_app")
