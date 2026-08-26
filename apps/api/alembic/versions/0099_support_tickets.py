"""F4 — tickets + ticket_events (FORCE RLS app.partner_id).

Persist from the existing POST /console/support/tickets. Admin list is
unscoped (table owner, same as GET /admin/partners). Partner session
sees only its own rows.

Revision ID: 0099_support_tickets
Revises: 0098_partner_model_allowlist
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0099_support_tickets"
down_revision: str | Sequence[str] | None = "0098_partner_model_allowlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TICKETS = "tickets"
_EVENTS = "ticket_events"
_TABLES: tuple[str, ...] = (_TICKETS, _EVENTS)
_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "ticket.open",
        "support",
        "info",
        "{actor} abrió el ticket {ticket} ({category} · {topic})",
        "{actor} opened ticket {ticket} ({category} · {topic})",
    ),
    (
        "ticket.status",
        "support",
        "info",
        "{actor} pasó el ticket {ticket} de {from_status} a {to_status}",
        "{actor} moved ticket {ticket} from {from_status} to {to_status}",
    ),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tickets (
            id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            partner_id   uuid        NOT NULL
                             REFERENCES partners(id) ON DELETE CASCADE,
            ticket_ref   text        NOT NULL,
            category     text        NOT NULL,
            topic        text        NOT NULL,
            sla          text        NOT NULL,
            status       text        NOT NULL DEFAULT 'open',
            client_ref   text        NULL,
            need         text        NOT NULL,
            checked      jsonb       NOT NULL DEFAULT '[]'::jsonb,
            alternative  text        NULL,
            bridge       boolean     NOT NULL DEFAULT false,
            opened_by    text        NOT NULL,
            opened_at    timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_tickets_ticket_ref UNIQUE (ticket_ref),
            CONSTRAINT ck_tickets_category CHECK (category IN ('help', 'capability')),
            CONSTRAINT ck_tickets_status CHECK (status IN ('open', 'pending', 'closed'))
        )
        """
    )
    op.execute("CREATE INDEX ix_tickets_partner_opened ON tickets (partner_id, opened_at DESC)")
    op.execute("CREATE INDEX ix_tickets_status ON tickets (status)")

    op.execute(
        """
        CREATE TABLE ticket_events (
            id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id    uuid        NOT NULL
                             REFERENCES tickets(id) ON DELETE CASCADE,
            partner_id   uuid        NOT NULL
                             REFERENCES partners(id) ON DELETE CASCADE,
            kind         text        NOT NULL,
            from_status  text        NULL,
            to_status    text        NOT NULL,
            actor        text        NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_ticket_events_kind CHECK (kind IN ('open', 'status')),
            CONSTRAINT ck_ticket_events_to_status
                CHECK (to_status IN ('open', 'pending', 'closed')),
            CONSTRAINT ck_ticket_events_from_status
                CHECK (from_status IS NULL OR from_status IN ('open', 'pending', 'closed'))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_ticket_events_ticket_created "
        "ON ticket_events (ticket_id, created_at DESC)"
    )
    op.execute("CREATE INDEX ix_ticket_events_partner ON ticket_events (partner_id)")

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_partner_isolation ON {table}
            USING (partner_id = {_PARTNER})
            WITH CHECK (partner_id = {_PARTNER})
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")

    for action, category, severity, es, en in VOCABULARY:
        es_q = es.replace("'", "''")
        en_q = en.replace("'", "''")
        op.execute(
            "INSERT INTO console_audit_vocabulary "
            "(action, category, severity, summary_es, summary_en) "
            f"VALUES ('{action}', '{category}', '{severity}', '{es_q}', '{en_q}') "
            "ON CONFLICT (action) DO UPDATE SET category = EXCLUDED.category, "
            "severity = EXCLUDED.severity, summary_es = EXCLUDED.summary_es, "
            "summary_en = EXCLUDED.summary_en, updated_at = now()"
        )


def downgrade() -> None:
    for action, *_rest in VOCABULARY:
        op.execute(f"DELETE FROM console_audit_vocabulary WHERE action = '{action}'")
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_partner_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS ticket_events")
    op.execute("DROP TABLE IF EXISTS tickets")
