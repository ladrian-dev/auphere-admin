"""messages → monthly RANGE partitions (WP-13, plataforma v2 Fase 1).

Closes half of V3: ``messages`` is the highest-write table and its indexes
degrade monotonically as it grows. Partitioning by month keeps every index
small, makes retention a ``DROP PARTITION`` (instant, no vacuum debt) and is
exactly the kind of surgery that is trivial NOW — the table is small — and a
maintenance window in six months.

Procedure (single transaction — Alembic wraps the migration):
1. create ``messages_new`` with the same columns (LIKE), partitioned by
   RANGE (created_at), monthly partitions from the oldest row through
   next month, plus a DEFAULT partition as a safety net;
2. recreate constraints/indexes with the partition key folded in
   (see trade-offs below), RLS (ENABLE + FORCE + tenant policy), grants,
   and the 0062 pg_notify trigger (row triggers propagate to partitions);
3. copy rows, swap names, drop the old table.

**Documented trade-offs** (Postgres requires the partition key in every
unique constraint):
- PK becomes ``(id, created_at)``. ORM lookups by ``id`` still use the
  btree prefix; identity semantics unchanged.
- ``uq_messages_provider_message_id`` becomes ``(provider_message_id,
  created_at)`` — the DURABLE dedupe weakens to per-timestamp. The Redis
  dedupe layer (TTL 600 s > both providers' retry budgets) remains the
  real gate; the residual window is a provider redriving the same message
  id beyond its own retry budget AND after the Redis TTL, which both
  providers document as not happening.
- ``uq_messages_tenant_idempotency`` becomes ``(tenant_id,
  idempotency_key, created_at)`` — the API's replay path SELECT-checks
  before inserting (services/direct_messages.py), so the index is a race
  net, not the primary mechanism.
- The FK ``broadcast_recipients.message_id → messages(id)`` is DROPPED
  (a FK cannot reference a non-unique column set). The column and its
  semantics stay; messages are never deleted today, and the GDPR delete
  work (WP-29) must clean ``broadcast_recipients`` explicitly.

Revision ID: 0063_messages_partitioned
Revises: 0062_outbound_notify_trigger
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op

revision: str = "0063_messages_partitioned"
down_revision: str | Sequence[str] | None = "0062_outbound_notify_trigger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _month_bounds(year: int, month: int) -> tuple[str, str, str]:
    start = datetime(year, month, 1, tzinfo=UTC)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    end = datetime(ny, nm, 1, tzinfo=UTC)
    return (
        f"messages_y{year:04d}m{month:02d}",
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
    )


def upgrade() -> None:
    bind = op.get_bind()

    # 1 · partitioned parent, same column definitions.
    op.execute(
        """
        CREATE TABLE messages_new (
            LIKE messages INCLUDING DEFAULTS INCLUDING GENERATED
        ) PARTITION BY RANGE (created_at)
        """
    )
    op.execute("ALTER TABLE messages_new ADD PRIMARY KEY (id, created_at)")

    # 2 · monthly partitions covering existing data → next month, + DEFAULT.
    row = bind.exec_driver_sql(
        "SELECT min(created_at), now() + interval '1 month' FROM messages"
    ).first()
    oldest = row[0] or row[1]
    horizon = row[1]
    year, month = oldest.year, oldest.month
    while (year, month) <= (horizon.year, horizon.month):
        name, start, end = _month_bounds(year, month)
        op.execute(
            f"CREATE TABLE {name} PARTITION OF messages_new "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    op.execute("CREATE TABLE messages_default PARTITION OF messages_new DEFAULT")

    # 3 · indexes (partitioned — propagate to every partition).
    op.execute("CREATE INDEX ix_messages_new_tenant_id ON messages_new (tenant_id)")
    op.execute(
        "CREATE INDEX ix_messages_new_conversation_id ON messages_new (conversation_id)"
    )
    op.execute("CREATE INDEX ix_messages_new_trace_id ON messages_new (trace_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_messages_new_provider_message_id "
        "ON messages_new (provider_message_id, created_at) "
        "WHERE provider_message_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_messages_new_tenant_idempotency "
        "ON messages_new (tenant_id, idempotency_key, created_at) "
        "WHERE idempotency_key IS NOT NULL"
    )

    # 4 · RLS + grants, same posture as the old table.
    op.execute("ALTER TABLE messages_new ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE messages_new FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY messages_tenant_isolation ON messages_new
        USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON messages_new TO nexus_app")

    # 5 · copy + swap. The copy is why this runs NOW: small table, one txn.
    op.execute("INSERT INTO messages_new SELECT * FROM messages")
    op.execute("ALTER TABLE messages RENAME TO messages_old")
    op.execute("ALTER TABLE messages_new RENAME TO messages")

    # 6 · re-point the 0062 trigger at the new parent (it died with the old
    # table's name in step 5's swap — without this, egress notifications
    # silently stop). Row triggers on a partitioned parent apply to all
    # partitions, current and future.
    op.execute(
        """
        CREATE TRIGGER trg_notify_outbound_pending
        AFTER INSERT ON messages
        FOR EACH ROW
        WHEN (NEW.status = 'pending' AND NEW.direction = 'outbound')
        EXECUTE FUNCTION notify_outbound_pending()
        """
    )

    # 7 · drop the FK that cannot exist against a partitioned target, then
    # the old table.
    op.execute(
        "ALTER TABLE broadcast_recipients "
        "DROP CONSTRAINT IF EXISTS broadcast_recipients_message_id_fkey"
    )
    op.execute("DROP TABLE messages_old")

    # 8 · rename indexes to their canonical names now that the table owns them.
    op.execute("ALTER INDEX ix_messages_new_tenant_id RENAME TO ix_messages_tenant_id")
    op.execute(
        "ALTER INDEX ix_messages_new_conversation_id RENAME TO ix_messages_conversation_id"
    )
    op.execute("ALTER INDEX ix_messages_new_trace_id RENAME TO ix_messages_trace_id")
    op.execute(
        "ALTER INDEX uq_messages_new_provider_message_id "
        "RENAME TO uq_messages_provider_message_id"
    )
    op.execute(
        "ALTER INDEX uq_messages_new_tenant_idempotency "
        "RENAME TO uq_messages_tenant_idempotency"
    )


def downgrade() -> None:
    # Reverse surgery: plain table again, original indexes/FK/trigger back.
    op.execute(
        """
        CREATE TABLE messages_plain (
            LIKE messages INCLUDING DEFAULTS INCLUDING GENERATED
        )
        """
    )
    op.execute("ALTER TABLE messages_plain ADD PRIMARY KEY (id)")
    op.execute("INSERT INTO messages_plain SELECT * FROM messages")
    op.execute("DROP TABLE messages")  # drops all partitions with it
    op.execute("ALTER TABLE messages_plain RENAME TO messages")

    op.execute("CREATE INDEX ix_messages_tenant_id ON messages (tenant_id)")
    op.execute("CREATE INDEX ix_messages_conversation_id ON messages (conversation_id)")
    op.execute("CREATE INDEX ix_messages_trace_id ON messages (trace_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_messages_provider_message_id ON messages "
        "(provider_message_id) WHERE provider_message_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_messages_tenant_idempotency ON messages "
        "(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
    op.execute("ALTER TABLE messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE messages FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY messages_tenant_isolation ON messages
        USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON messages TO nexus_app")
    op.execute(
        """
        CREATE TRIGGER trg_notify_outbound_pending
        AFTER INSERT ON messages
        FOR EACH ROW
        WHEN (NEW.status = 'pending' AND NEW.direction = 'outbound')
        EXECUTE FUNCTION notify_outbound_pending()
        """
    )
    op.execute(
        """
        ALTER TABLE broadcast_recipients
        ADD CONSTRAINT broadcast_recipients_message_id_fkey
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
        """
    )
