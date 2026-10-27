"""Ningún mensaje se pierde y el turno es fiable — spec 047, T031 (ola 1).

- ``conversations.waiting_reason``: por qué una conversación espera a una
  persona, de la lista cerrada de ``contracts/events.md`` §2. Cada puerta del
  turno (sin saldo, pausa, canal con problemas…) **guarda primero** el mensaje y
  escribe aquí su código (requisitos 2.2 y 2.3).
- ``conversations.last_turn_at`` y ``takeover_until`` (el eco de coexistencia,
  ola 4, deja la conversación a una persona durante 2 h).
- ``messages.origin`` (quién lo escribió) y ``messages.turn_id``: un mensaje
  entrante queda sin turno hasta que un turno lo toma; la agrupación de 3 s
  (requisito 1.1) toma todos los que no tienen turno.
- ``turn_effects``: una acción con efecto (reservar, cobrar, enviar…) ocurre
  como mucho una vez por turno aunque el turno se reintente (requisito 1.3).
- ``meta_reconciliation_runs``: lo entregado por Meta frente a lo guardado, por
  canal y día (requisito 2.6).
- ``channels`` gana ``UNIQUE (tenant_id, id)`` para que las tablas nuevas le
  apunten con FK compuesta (la comprobación de una FK no pasa por la RLS).
- ``resolve_channel_tenant`` reconoce los canales en pausa y con problemas: su
  mensaje se guarda y va a la Bandeja con su motivo en lugar de perderse. Los
  envíos salientes siguen solo con canales activos (``channel_routing``).

Revision ID: 0176_inbound_reasons_and_turns
Revises: 0175_fabrica_base
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0176_inbound_reasons_and_turns"
down_revision: str | Sequence[str] | None = "0175_fabrica_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

WAITING_REASONS = (
    "no_balance",
    "agent_cap",
    "paused_agent",
    "paused_channel",
    "paused_client",
    "archived_client",
    "channel_problem",
    "agent_unpublished",
    "out_of_audience",
    "no_model",
    "provider_failure",
    "turn_limit",
    "escalated",
    "human_takeover",
    "reception_loop",
)
MESSAGE_ORIGINS = (
    "customer",
    "agent",
    "business_person",
    "business_app_echo",
    "history_import",
    "system",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


_RESOLVER = """
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
          AND status IN ({statuses})
        LIMIT 1;
        RETURN v_tid;
    END;
    $$;
"""

TABLES = ("turn_effects", "meta_reconciliation_runs")


def upgrade() -> None:
    op.execute("ALTER TABLE channels ADD CONSTRAINT uq_channels_tenant_id UNIQUE (tenant_id, id)")

    op.execute("ALTER TABLE conversations ADD COLUMN waiting_reason varchar(32)")
    op.execute(
        "ALTER TABLE conversations ADD CONSTRAINT ck_conversations_waiting_reason "
        f"CHECK (waiting_reason IS NULL OR waiting_reason IN ({_in(WAITING_REASONS)}))"
    )
    op.execute("ALTER TABLE conversations ADD COLUMN last_turn_at timestamptz")
    op.execute("ALTER TABLE conversations ADD COLUMN takeover_until timestamptz")

    # ``messages`` is partitioned: ADD COLUMN and the partial index reach every
    # partition. No default and no rewrite: existing rows keep NULL.
    op.execute("ALTER TABLE messages ADD COLUMN origin varchar(24)")
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_origin "
        f"CHECK (origin IS NULL OR origin IN ({_in(MESSAGE_ORIGINS)}))"
    )
    op.execute("ALTER TABLE messages ADD COLUMN turn_id uuid")
    # What a turn takes: the inbound messages of its conversation with no turn.
    op.execute(
        "CREATE INDEX ix_messages_untaken ON messages (tenant_id, conversation_id, created_at) "
        "WHERE turn_id IS NULL AND direction = 'inbound'"
    )

    op.execute(
        """
        CREATE TABLE turn_effects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            turn_id uuid NOT NULL,
            effect varchar(40) NOT NULL,
            idempotency_key varchar(200) NOT NULL,
            result jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_turn_effects_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_turn_effects_key UNIQUE (tenant_id, idempotency_key)
        )
        """
    )
    op.execute("CREATE INDEX ix_turn_effects_turn ON turn_effects (tenant_id, turn_id)")
    op.execute(
        """
        CREATE TABLE meta_reconciliation_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            channel_id uuid NOT NULL,
            date date NOT NULL,
            meta_count integer NOT NULL,
            stored_count integer NOT NULL,
            diff integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_meta_reconciliation_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT uq_meta_reconciliation_day UNIQUE (tenant_id, channel_id, date),
            CONSTRAINT ck_meta_reconciliation_counts CHECK (meta_count >= 0 AND stored_count >= 0),
            CONSTRAINT fk_meta_reconciliation_channel FOREIGN KEY (tenant_id, channel_id)
                REFERENCES channels (tenant_id, id) ON DELETE CASCADE
        )
        """
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING {_POLICY} WITH CHECK {_POLICY}"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")

    op.execute(_RESOLVER.format(statuses="'active', 'paused', 'degraded'"))


def downgrade() -> None:
    op.execute(_RESOLVER.format(statuses="'active'"))
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_messages_untaken")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS turn_id")
    op.execute("ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_origin")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS origin")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS takeover_until")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS last_turn_at")
    op.execute(
        "ALTER TABLE conversations DROP CONSTRAINT IF EXISTS ck_conversations_waiting_reason"
    )
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS waiting_reason")
    op.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS uq_channels_tenant_id")
