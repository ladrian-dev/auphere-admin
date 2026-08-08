"""pg_notify on pending outbound messages (WP-12 / D11 — closes V4).

The egress dispatcher used to open a transaction per ACTIVE tenant every
500 ms — O(tenants) database load that grew with the customer count, not
with traffic. This trigger emits ``pg_notify('nexus_outbound', tenant_id)``
on every freshly inserted pending outbound row, so the dispatcher only
touches tenants that actually have work. A 30 s safety sweep in the
dispatcher covers notifications lost across reconnects, and rows re-queued
via UPDATE (retries) — which by design do not fire this INSERT trigger.

Revision ID: 0062_outbound_notify_trigger
Revises: 0061_tenant_tier
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0062_outbound_notify_trigger"
down_revision: str | Sequence[str] | None = "0061_tenant_tier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHANNEL = "nexus_outbound"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_outbound_pending() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('nexus_outbound', NEW.tenant_id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_notify_outbound_pending
        AFTER INSERT ON messages
        FOR EACH ROW
        WHEN (NEW.status = 'pending' AND NEW.direction = 'outbound')
        EXECUTE FUNCTION notify_outbound_pending();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_notify_outbound_pending ON messages")
    op.execute("DROP FUNCTION IF EXISTS notify_outbound_pending()")
