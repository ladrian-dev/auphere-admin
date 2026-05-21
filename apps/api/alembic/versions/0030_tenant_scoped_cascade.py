"""Tenant-scoped tables: add missing ON DELETE CASCADE FK to ``tenants``.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-21

Background
----------
``TenantScopedMixin`` declared ``tenant_id`` as a plain UUID column with no
foreign key to ``tenants(id)``. RLS was the only authority. The
``delete_tenant`` endpoint explicitly cleaned up the two RESTRICT-FK
children (``tenant_connectors``, ``tenant_connector_tool_overrides``) and
relied on the rest cascading via FK — but the FKs never existed, so every
tenant hard-delete left orphan rows behind. The 2026-05-21 prod
investigation found 8 orphan ``agent_configs`` + 28 orphan ``audit_log``
rows from 6 tenants deleted between 2026-05-13 and 2026-05-20.

The endpoint docstring already anticipated this fix:
    "A migration to flip the FKs to CASCADE is the durable fix; this
     endpoint cleanup is the resilient one."

This migration is that durable fix.

What it does
------------
For each tenant-scoped table that has a ``tenant_id`` column but no FK to
``tenants(id)``, this migration:

  1. Deletes any existing orphan rows (``tenant_id`` not in ``tenants.id``).
     Idempotent — clean DBs delete zero rows. Required before adding the
     FK or the constraint creation would itself fail on the orphans.
  2. Adds ``FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE
     CASCADE``. Wrapped in a DO block that catches ``duplicate_object``
     so re-running the migration is safe.

Tables NOT touched (intentional design, kept as-is):
  - ``tenant_connectors`` / ``tenant_connector_tool_overrides``: Block L
    chose ``ON DELETE RESTRICT`` so an operator can't accidentally wipe
    live OAuth grants. The endpoint handles those explicitly.
  - ``whatsapp_opt_outs``: same RESTRICT story (do not auto-delete opt-out
    consent records).
  - ``whatsapp_template_status``: ``ON DELETE SET NULL`` — template
    definitions outlive the tenant for shared review.
  - All ``qa.*`` tables, ``eval_*``, ``owner_*`` already cascade.

Side-cleanup: drops 4 duplicate ``public.checkpoint*`` tables left over
from an early ``AsyncPostgresSaver.setup()`` call before migration 0029
moved them to the ``langgraph`` schema. They've been empty for the
lifetime of prod; the canonical copies live in ``langgraph.*``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables with ``tenant_id`` but no FK to ``tenants(id)`` as of 0029.
# Verified against prod 2026-05-21 via:
#   SELECT ... FROM information_schema.columns LEFT JOIN pg_constraint ...
TARGETS: tuple[str, ...] = (
    "agent_configs",
    "appointments",
    "audit_log",
    "channels",
    "conversations",
    "customers",
    "daily_cost_snapshots",
    "isolation_events",
    "kg_edges",
    "kg_nodes",
    "messages",
    "operator_notifications",
    "queue_entries",
    "scheduled_jobs",
    "tenant_credentials",
    "usage_events",
)


def upgrade() -> None:
    for table in TARGETS:
        # Step 1: clear orphans so the FK can be added.
        op.execute(f"DELETE FROM {table} WHERE tenant_id NOT IN (SELECT id FROM tenants)")
        # Step 2: add FK if not already present.
        op.execute(
            f"""
            DO $$
            BEGIN
              ALTER TABLE {table}
                ADD CONSTRAINT {table}_tenant_id_fkey
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
            EXCEPTION
              WHEN duplicate_object THEN NULL;
            END
            $$;
            """
        )

    # Side-cleanup: drop duplicate public.checkpoint* tables. The canonical
    # copies live in langgraph.* per migration 0029. No data lost — these
    # have been empty in prod and AsyncPostgresSaver only writes to the
    # langgraph schema since the search_path fix.
    op.execute("DROP TABLE IF EXISTS public.checkpoint_writes")
    op.execute("DROP TABLE IF EXISTS public.checkpoint_blobs")
    op.execute("DROP TABLE IF EXISTS public.checkpoints")
    op.execute("DROP TABLE IF EXISTS public.checkpoint_migrations")
    op.execute("DROP TABLE IF EXISTS public.checkpoint_delete_queue")


def downgrade() -> None:
    for table in TARGETS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_tenant_id_fkey")
    # We don't recreate public.checkpoint* on downgrade — the LangGraph
    # saver will recreate them in the langgraph schema on next startup
    # if needed, and the public copies were never the source of truth.
