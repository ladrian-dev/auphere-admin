"""agent_memories — persistent memory for the Anthropic Memory tool.

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-23

Fase B of [[claude-platform-integration]] — backend for the Anthropic
Memory tool (``memory_20250818``). Two tables land here:

- ``agent_memories`` — current state of every memory file. Scoped by
  ``tenant_id`` (RLS) and optionally by ``customer_id``. Rows with
  ``customer_id IS NULL`` are tenant-wide memories (operator-curated
  policies, known issues).
- ``agent_memory_versions`` — append-only audit copy fed by a trigger.
  Every INSERT / UPDATE / DELETE on ``agent_memories`` writes one row
  here with ``operation`` set accordingly. A cron in the worker drains
  rows older than 30 days (``memory_versions_retention``).

Isolation invariants this migration enforces:
  1. RLS by ``tenant_id`` on both tables — same pattern as 0002.
  2. ``FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE``
     so tenant hard-delete reaps all memory rows + their version history
     (consistent with 0030).
  3. ``FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE
     CASCADE`` so deleting a customer drops their memories.
  4. ``CHECK (path LIKE '/memories/%')`` defence-in-depth — even if
     the path validator in the worker is somehow bypassed, the DB
     refuses paths outside ``/memories/``.
  5. UNIQUE ``(tenant_id, COALESCE(customer_id::text, '_tenant'), path)``
     so a given (tenant, customer, path) maps to at most one row — the
     Memory tool semantics ("create" fails on existing path).

Why a separate versions table rather than soft-delete + history columns:
  - The Memory tool's ``str_replace`` / ``insert`` mutate ``content`` in
    place — without an external audit trail there is no way to recover
    earlier states. The versions table is read-only from app code; the
    trigger is the sole writer.

Path schema (visible to the LLM, not enforced in DB beyond the prefix):
  /memories/customer/{customer_id}/...   ← per-customer memory
  /memories/customer/me/...              ← alias the LLM may write; the
                                            worker resolves "me" to the
                                            current turn's customer_id
                                            BEFORE the SQL runs.
  /memories/tenant/...                   ← tenant-wide memory
                                            (customer_id IS NULL)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRIGGER_FN = "agent_memories_audit_trigger_fn"
_TRIGGER_NAME = "agent_memories_audit_trigger"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid

    # ── current-state table ────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE agent_memories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL
                REFERENCES tenants(id) ON DELETE CASCADE,
            customer_id UUID NULL
                REFERENCES customers(id) ON DELETE CASCADE,
            path TEXT NOT NULL
                CHECK (path LIKE '/memories/%'),
            content TEXT NOT NULL,
            size_bytes INTEGER GENERATED ALWAYS AS (octet_length(content)) STORED,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_accessed_at TIMESTAMPTZ NULL
        )
        """
    )
    # UNIQUE on (tenant, customer-or-_tenant-marker, path) so SQL upserts
    # behave the way the Memory tool semantics demand. The COALESCE is the
    # only way Postgres treats two NULLs as "the same" in a unique key —
    # otherwise two tenant-wide memories at the same path would be allowed.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_agent_memories_tenant_customer_path
        ON agent_memories (tenant_id, COALESCE(customer_id::text, '_tenant'), path)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_agent_memories_tenant_customer
        ON agent_memories (tenant_id, customer_id)
        """
    )

    # ── audit / versions table ─────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE agent_memory_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            memory_id UUID NULL,
            tenant_id UUID NOT NULL
                REFERENCES tenants(id) ON DELETE CASCADE,
            customer_id UUID NULL,
            path TEXT NOT NULL,
            content TEXT NULL,
            operation TEXT NOT NULL
                CHECK (operation IN ('insert', 'update', 'delete')),
            versioned_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Lookups are "show me the history of this memory" — index by
    # (tenant, memory_id, versioned_at DESC).
    op.execute(
        """
        CREATE INDEX idx_agent_memory_versions_tenant_memory
        ON agent_memory_versions (tenant_id, memory_id, versioned_at DESC)
        """
    )
    # Retention drain query scans by versioned_at, so a btree on it.
    op.execute(
        """
        CREATE INDEX idx_agent_memory_versions_versioned_at
        ON agent_memory_versions (versioned_at)
        """
    )

    # ── audit trigger ─────────────────────────────────────────────────
    #
    # The trigger writes to ``agent_memory_versions`` directly — no app
    # code involved. ``SECURITY DEFINER`` is NOT used: the trigger runs
    # with the calling session's privileges, which means the same RLS
    # context already gating ``agent_memories`` gates the writes here too
    # (the row carries the same ``tenant_id``). That keeps the audit
    # trail tenant-isolated end-to-end without a privilege-escalation
    # bypass.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_TRIGGER_FN}()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF (TG_OP = 'INSERT') THEN
                INSERT INTO agent_memory_versions (
                    memory_id, tenant_id, customer_id, path, content, operation
                ) VALUES (
                    NEW.id, NEW.tenant_id, NEW.customer_id, NEW.path,
                    NEW.content, 'insert'
                );
                RETURN NEW;
            ELSIF (TG_OP = 'UPDATE') THEN
                INSERT INTO agent_memory_versions (
                    memory_id, tenant_id, customer_id, path, content, operation
                ) VALUES (
                    NEW.id, NEW.tenant_id, NEW.customer_id, NEW.path,
                    NEW.content, 'update'
                );
                RETURN NEW;
            ELSIF (TG_OP = 'DELETE') THEN
                INSERT INTO agent_memory_versions (
                    memory_id, tenant_id, customer_id, path, content, operation
                ) VALUES (
                    OLD.id, OLD.tenant_id, OLD.customer_id, OLD.path,
                    OLD.content, 'delete'
                );
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        AFTER INSERT OR UPDATE OR DELETE ON agent_memories
        FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FN}()
        """
    )

    # ── RLS on both tables ─────────────────────────────────────────────
    # Same policy shape as migration 0002 — fail-closed when
    # ``app.tenant_id`` is unset (NULL setting → predicate is NULL → row
    # excluded).
    for table in ("agent_memories", "agent_memory_versions"):
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


def downgrade() -> None:
    # Drop in reverse order to satisfy FK + trigger dependencies.
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON agent_memories")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FN}()")
    op.execute("DROP TABLE IF EXISTS agent_memory_versions")
    op.execute("DROP TABLE IF EXISTS agent_memories")
