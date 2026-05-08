"""row level security on every tenant-scoped table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08

Implements guarantee #1 of architecture/agent-isolation.md.

For every tenant-scoped table we:
  1. Enable RLS.
  2. Force RLS even for the table owner (so app role hits the policy).
  3. Add a policy that allows access only when current_setting('app.tenant_id')
     matches the row's tenant_id.

The policy is permissive (the default) so it grants access when the predicate is
true. The setting is read with `current_setting('app.tenant_id', true)` so a
missing setting evaluates the policy to NULL → row excluded. That fails closed:
queries without `SET LOCAL app.tenant_id = '<uuid>'` see zero rows.

Tables NOT covered: tenants (the root mapping itself), tool_catalog, kg_schemas
(both global). Admin endpoints that scan tenants are gated by NEXUS_ADMIN_TOKEN.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCOPED_TABLES: tuple[str, ...] = (
    "agent_configs",
    "channels",
    "tenant_credentials",
    "kg_nodes",
    "kg_edges",
    "customers",
    "conversations",
    "messages",
    "usage_events",
    "audit_log",
)


def upgrade() -> None:
    for table in SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )

    # Webhook resolver bypass — see core/tenant_resolver.py.
    # SECURITY DEFINER + `SET row_security = off` lets this single function read
    # `channels` across tenants without weakening the policy. The function takes
    # only (provider, identifier) and returns just the tenant_id, so it cannot
    # leak data beyond what the resolver needs.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION resolve_channel_tenant(
            p_provider text,
            p_identifier text
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET row_security = off
        AS $$
        DECLARE
            v_tid uuid;
        BEGIN
            SELECT tenant_id INTO v_tid
            FROM channels
            WHERE provider = p_provider
              AND provider_identifier = p_identifier
              AND status = 'active'
            LIMIT 1;
            RETURN v_tid;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_channel_tenant(text, text)")
    for table in SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
