"""El ensayo y la activación de la consola nueva — spec 047, T179 y T180 (requisitos
55.2, 55.4 y 55.5; ``data-model.md`` §10).

``migration_reports``: lo que dio cada ensayo y cada activación de un partner. Por
agente, si su prompt compilado sigue siendo idéntico byte a byte y si su modelo
sigue fijado (``eval_diff``); por número, la audiencia efectiva antes y después
(``audience_diff``). Un ensayo con diferencias bloquea la activación.

Revision ID: 0201_console_v2_reports
Revises: 0200_reception
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0201_console_v2_reports"
down_revision: str | Sequence[str] | None = "0200_reception"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE migration_reports (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            partner_id uuid NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
            kind varchar(16) NOT NULL CHECK (kind IN ('dry_run', 'activation')),
            status varchar(16) NOT NULL CHECK (status IN ('clean', 'diff')),
            eval_diff jsonb NOT NULL DEFAULT '[]'::jsonb,
            audience_diff jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_by varchar(160) NOT NULL,
            reason varchar(300),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_migration_reports_partner ON migration_reports (partner_id, created_at DESC)"
    )
    op.execute("ALTER TABLE migration_reports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE migration_reports FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY migration_reports_partner_isolation ON migration_reports "
        f"USING (partner_id = {_PARTNER}) WITH CHECK (partner_id = {_PARTNER})"
    )
    op.execute("GRANT SELECT, INSERT ON migration_reports TO nexus_app")
    # Los avisos del agente y de sus números llegan al teléfono (T170), encendidos
    # también en los teléfonos que ya estaban dados de alta.
    _push_kinds(_KINDS_AFTER, _DEFAULT_AFTER)
    op.execute(
        "UPDATE client_phones SET notice_kinds = notice_kinds || ARRAY['agents.state']::varchar[] "
        "WHERE NOT notice_kinds @> ARRAY['agents.state']::varchar[]"
    )
    # La restricción soberana (T172) se lee en la Auditoría del partner.
    op.execute(
        "INSERT INTO console_audit_vocabulary (action, category, severity, summary_es, summary_en) "
        "VALUES ('client.sovereign_set', 'admin', 'info', "
        "'Auphere cambió la restricción soberana de {client}.', "
        "'Auphere changed the sovereign restriction of {client}.'), "
        # Las correcciones de comportamiento que decide el partner (52.3).
        "('correction.accepted', 'improvement', 'info', "
        "'{actor} aceptó una corrección de {client} para un agente.', "
        "'{actor} accepted a correction from {client} for an agent.'), "
        "('correction.rejected', 'improvement', 'info', "
        "'{actor} descartó una corrección de {client}.', "
        "'{actor} discarded a correction from {client}.') "
        "ON CONFLICT (action) DO NOTHING"
    )


_KINDS_BEFORE = (
    "inbox.waiting",
    "inbox.message_for_you",
    "client.balance",
    "reservas.agent_change",
    "reservas.cancelled_today",
    "reservas.waitlist_accepted",
)
#: Spec 047 (events.md §3.1): el interruptor «Agentes y números» del teléfono.
_KINDS_AFTER = (*_KINDS_BEFORE, "agents.state")
_DEFAULT_BEFORE = (
    "inbox.waiting",
    "inbox.message_for_you",
    "client.balance",
    "reservas.agent_change",
    "reservas.cancelled_today",
)
_DEFAULT_AFTER = (*_DEFAULT_BEFORE, "agents.state")


def _kinds(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _push_kinds(kinds: tuple[str, ...], default: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE client_phones DROP CONSTRAINT IF EXISTS ck_client_phones_notice_kinds")
    op.execute(
        "ALTER TABLE client_phones ADD CONSTRAINT ck_client_phones_notice_kinds "
        f"CHECK (notice_kinds <@ ARRAY[{_kinds(kinds)}]::varchar[])"
    )
    op.execute(
        "ALTER TABLE client_push_events DROP CONSTRAINT IF EXISTS ck_client_push_events_kind"
    )
    op.execute(
        "ALTER TABLE client_push_events ADD CONSTRAINT ck_client_push_events_kind "
        f"CHECK (kind IN ({_kinds(kinds)}))"
    )
    op.execute(
        "ALTER TABLE client_phones ALTER COLUMN notice_kinds SET DEFAULT "
        f"ARRAY[{_kinds(default)}]::varchar[]"
    )


def downgrade() -> None:
    op.execute("DELETE FROM client_push_events WHERE kind = 'agents.state'")
    op.execute("UPDATE client_phones SET notice_kinds = array_remove(notice_kinds, 'agents.state')")
    _push_kinds(_KINDS_BEFORE, _DEFAULT_BEFORE)
    op.execute(
        "DELETE FROM console_audit_vocabulary WHERE action IN "
        "('client.sovereign_set', 'correction.accepted', 'correction.rejected')"
    )
    op.execute("DROP TABLE IF EXISTS migration_reports CASCADE")
