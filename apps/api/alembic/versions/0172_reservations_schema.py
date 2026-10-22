"""Reservas — spec 043: el modelo de datos.

Once tablas por cliente (``data-model.md``), todas con ``tenant_id`` →
``tenants`` en cascada, RLS ``ENABLE`` + ``FORCE`` con ``WITH CHECK``, y **toda
referencia entre tablas de cliente con clave foránea compuesta**
``(tenant_id, x_id)``: la comprobación de una FK no pasa por la RLS.

Para poder referirlas así, ``customers`` y ``conversations`` ganan
``UNIQUE (tenant_id, id)`` (``agents`` ya lo tiene desde la 0155).

Además:

- ``client_access.modules`` admite ``reservas``;
- los avisos del teléfono admiten los tres tipos de Reservas, y los teléfonos
  que ya existen ganan los dos que nacen encendidos (el de la lista de espera
  nace apagado). Sin el módulo no les llega nada: lo decide la fan-out.

``downgrade`` lo deshace entero (la prueba de reversibilidad lo exige).

Revision ID: 0172_reservations_schema
Revises: 0171_inbox_attended
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0172_reservations_schema"
down_revision: str | Sequence[str] | None = "0171_inbox_attended"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

TABLES = (
    "reservation_settings",
    "reservation_staff",
    "reservation_services",
    "reservation_service_staff",
    "reservations",
    "reservation_events",
    "reservation_blocks",
    "reservation_waitlist",
    "reservation_offers",
    "reservation_offer_candidates",
    "reservation_outbox",
)
#: El historial no se edita ni se borra desde la aplicación.
APPEND_ONLY = {"reservation_events"}
#: Relaciones, no registros de negocio: se pueden quitar.
DELETABLE = {"reservation_service_staff"}

_MODULES_BEFORE = "'panel', 'inbox', 'usage'"
_MODULES_AFTER = "'panel', 'inbox', 'usage', 'reservas'"
_KINDS_BEFORE = "'client.balance', 'inbox.message_for_you', 'inbox.waiting'"
_KINDS_AFTER = (
    _KINDS_BEFORE
    + ", 'reservas.agent_change', 'reservas.cancelled_today', 'reservas.waitlist_accepted'"
)

DDL = """
CREATE TABLE reservation_settings (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    mode varchar(16) NOT NULL CONSTRAINT ck_reservation_settings_mode
        CHECK (mode IN ('services', 'capacity')),
    capacity_kind varchar(16) CONSTRAINT ck_reservation_settings_kind
        CHECK (capacity_kind IS NULL
               OR capacity_kind IN ('restaurant', 'bar', 'classes', 'tours', 'rooms', 'spa')),
    slot_step_minutes smallint NOT NULL DEFAULT 30,
    waitlist_enabled boolean NOT NULL DEFAULT true,
    waitlist_lead_minutes integer NOT NULL DEFAULT 120,
    agent_min_notice_minutes integer NOT NULL DEFAULT 60,
    agent_max_days_ahead integer NOT NULL DEFAULT 60,
    reminder_enabled boolean NOT NULL DEFAULT true,
    confirm_enabled boolean NOT NULL DEFAULT true,
    confirm_when varchar(16) NOT NULL DEFAULT '24h' CONSTRAINT ck_reservation_settings_confirm_when
        CHECK (confirm_when IN ('24h', 'same_day_12', '3h')),
    release_unconfirmed boolean NOT NULL DEFAULT false,
    seats integer,
    stay_minutes integer,
    max_party integer,
    walkin_hold integer,
    schedule jsonb,
    version integer NOT NULL DEFAULT 1,
    updated_by varchar(160),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reservation_staff (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name varchar(120) NOT NULL,
    email varchar(254),
    hours jsonb,
    position integer NOT NULL DEFAULT 0,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_reservation_staff_tenant_id UNIQUE (tenant_id, id)
);
CREATE INDEX ix_reservation_staff_tenant_id ON reservation_staff (tenant_id);

CREATE TABLE reservation_services (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name varchar(120) NOT NULL,
    duration_minutes smallint NOT NULL CONSTRAINT ck_reservation_services_duration
        CHECK (duration_minutes BETWEEN 15 AND 480 AND duration_minutes % 15 = 0),
    price_minor bigint CONSTRAINT ck_reservation_services_price
        CHECK (price_minor IS NULL OR price_minor >= 0),
    currency varchar(3) NOT NULL DEFAULT 'CLP',
    all_staff boolean NOT NULL DEFAULT true,
    position integer NOT NULL DEFAULT 0,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_reservation_services_tenant_id UNIQUE (tenant_id, id)
);
CREATE INDEX ix_reservation_services_tenant_id ON reservation_services (tenant_id);

CREATE TABLE reservation_service_staff (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    service_id uuid NOT NULL,
    staff_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, service_id, staff_id),
    CONSTRAINT fk_rss_service FOREIGN KEY (tenant_id, service_id)
        REFERENCES reservation_services (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_rss_staff FOREIGN KEY (tenant_id, staff_id)
        REFERENCES reservation_staff (tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    mode varchar(16) NOT NULL CONSTRAINT ck_reservations_mode
        CHECK (mode IN ('services', 'capacity')),
    status varchar(16) NOT NULL CONSTRAINT ck_reservations_status
        CHECK (status IN ('pending', 'confirmed', 'arrived', 'done', 'noshow', 'cancelled')),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    party_size smallint NOT NULL DEFAULT 1 CONSTRAINT ck_reservations_party CHECK (party_size >= 1),
    staff_id uuid,
    service_id uuid,
    service_name varchar(120),
    price_minor bigint,
    currency varchar(3),
    customer_id uuid,
    conversation_id uuid,
    agent_id uuid,
    contact_name varchar(120),
    contact_phone varchar(32),
    origin varchar(16) NOT NULL CONSTRAINT ck_reservations_origin
        CHECK (origin IN ('agent', 'person', 'waitlist', 'walkin')),
    channel varchar(16) NOT NULL CONSTRAINT ck_reservations_channel
        CHECK (channel IN ('whatsapp', 'phone', 'in_person')),
    created_by_kind varchar(16) NOT NULL CONSTRAINT ck_reservations_created_by
        CHECK (created_by_kind IN ('agent', 'person', 'system', 'customer')),
    created_by_name varchar(120),
    note varchar(500),
    wants_earlier boolean NOT NULL DEFAULT false,
    any_staff boolean NOT NULL DEFAULT false,
    arrived_at timestamptz,
    cancelled_at timestamptz,
    cancelled_by varchar(16) CONSTRAINT ck_reservations_cancelled_by
        CHECK (cancelled_by IS NULL OR cancelled_by IN ('customer', 'business', 'system')),
    cancel_cause varchar(32),
    confirmation_requested_at timestamptz,
    idempotency_key varchar(120),
    external_event_id varchar(255),
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_reservations_span CHECK (ends_at > starts_at),
    CONSTRAINT ck_reservations_services_refs
        CHECK (mode <> 'services' OR (staff_id IS NOT NULL AND service_id IS NOT NULL)),
    CONSTRAINT uq_reservations_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_reservations_idempotency UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT fk_reservations_staff FOREIGN KEY (tenant_id, staff_id)
        REFERENCES reservation_staff (tenant_id, id),
    CONSTRAINT fk_reservations_service FOREIGN KEY (tenant_id, service_id)
        REFERENCES reservation_services (tenant_id, id),
    CONSTRAINT fk_reservations_customer FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id) ON DELETE SET NULL (customer_id),
    CONSTRAINT fk_reservations_conversation FOREIGN KEY (tenant_id, conversation_id)
        REFERENCES conversations (tenant_id, id) ON DELETE SET NULL (conversation_id),
    CONSTRAINT fk_reservations_agent FOREIGN KEY (tenant_id, agent_id)
        REFERENCES agents (tenant_id, id) ON DELETE SET NULL (agent_id)
);
CREATE INDEX ix_reservations_tenant_id ON reservations (tenant_id);
CREATE INDEX ix_reservations_tenant_starts ON reservations (tenant_id, starts_at);
CREATE INDEX ix_reservations_staff_live ON reservations (tenant_id, staff_id, starts_at)
    WHERE status IN ('pending', 'confirmed');
CREATE INDEX ix_reservations_customer ON reservations (tenant_id, customer_id, starts_at);

CREATE TABLE reservation_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    reservation_id uuid NOT NULL,
    kind varchar(32) NOT NULL CONSTRAINT ck_reservation_events_kind CHECK (kind IN (
        'created', 'confirmed', 'confirmation_requested', 'reminder_sent', 'replied_yes',
        'replied_no', 'moved', 'cancelled', 'arrived', 'noshow', 'undone', 'done',
        'waitlist_joined', 'waitlist_accepted', 'notified', 'notify_failed', 'released')),
    actor_kind varchar(16) NOT NULL CONSTRAINT ck_reservation_events_actor
        CHECK (actor_kind IN ('agent', 'person', 'system', 'customer')),
    actor_name varchar(120),
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_reservation_events_reservation FOREIGN KEY (tenant_id, reservation_id)
        REFERENCES reservations (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_reservation_events_tenant_id ON reservation_events (tenant_id);
CREATE INDEX ix_reservation_events_reservation
    ON reservation_events (tenant_id, reservation_id, created_at);

CREATE TABLE reservation_blocks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    day date NOT NULL,
    from_time time NOT NULL,
    until_time time NOT NULL,
    label varchar(120) NOT NULL,
    created_by_name varchar(120),
    removed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_reservation_blocks_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT ck_reservation_blocks_span CHECK (until_time >= from_time),
    CONSTRAINT ck_reservation_blocks_label CHECK (length(label) BETWEEN 1 AND 120)
);
CREATE INDEX ix_reservation_blocks_tenant_id ON reservation_blocks (tenant_id);
CREATE INDEX ix_reservation_blocks_day ON reservation_blocks (tenant_id, day);

CREATE TABLE reservation_waitlist (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    mode varchar(16) NOT NULL CONSTRAINT ck_reservation_waitlist_mode
        CHECK (mode IN ('services', 'capacity')),
    status varchar(16) NOT NULL DEFAULT 'waiting' CONSTRAINT ck_reservation_waitlist_status
        CHECK (status IN ('waiting', 'offered', 'accepted', 'removed', 'expired')),
    customer_id uuid,
    contact_name varchar(120),
    contact_phone varchar(32),
    party_size smallint NOT NULL DEFAULT 1,
    desired_day date,
    desired_time time,
    desired_until date,
    service_id uuid,
    staff_id uuid,
    reservation_id uuid,
    joined_by_kind varchar(16) NOT NULL CONSTRAINT ck_reservation_waitlist_joined
        CHECK (joined_by_kind IN ('agent', 'person', 'in_person')),
    joined_by_name varchar(120),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_reservation_waitlist_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_reservation_waitlist_customer FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id) ON DELETE SET NULL (customer_id),
    CONSTRAINT fk_reservation_waitlist_service FOREIGN KEY (tenant_id, service_id)
        REFERENCES reservation_services (tenant_id, id),
    CONSTRAINT fk_reservation_waitlist_staff FOREIGN KEY (tenant_id, staff_id)
        REFERENCES reservation_staff (tenant_id, id),
    CONSTRAINT fk_reservation_waitlist_reservation FOREIGN KEY (tenant_id, reservation_id)
        REFERENCES reservations (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_reservation_waitlist_tenant_id ON reservation_waitlist (tenant_id);

CREATE TABLE reservation_offers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    mode varchar(16) NOT NULL CONSTRAINT ck_reservation_offers_mode
        CHECK (mode IN ('services', 'capacity')),
    status varchar(16) NOT NULL DEFAULT 'running' CONSTRAINT ck_reservation_offers_status
        CHECK (status IN ('running', 'filled', 'empty', 'stopped')),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    staff_id uuid,
    service_id uuid,
    seats smallint,
    source_reservation_id uuid,
    cancelled_by_name varchar(120),
    window_minutes smallint NOT NULL,
    max_candidates smallint NOT NULL,
    filled_reservation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    CONSTRAINT uq_reservation_offers_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_reservation_offers_staff FOREIGN KEY (tenant_id, staff_id)
        REFERENCES reservation_staff (tenant_id, id),
    CONSTRAINT fk_reservation_offers_service FOREIGN KEY (tenant_id, service_id)
        REFERENCES reservation_services (tenant_id, id),
    CONSTRAINT fk_reservation_offers_source FOREIGN KEY (tenant_id, source_reservation_id)
        REFERENCES reservations (tenant_id, id) ON DELETE SET NULL (source_reservation_id),
    CONSTRAINT fk_reservation_offers_filled FOREIGN KEY (tenant_id, filled_reservation_id)
        REFERENCES reservations (tenant_id, id) ON DELETE SET NULL (filled_reservation_id)
);
CREATE INDEX ix_reservation_offers_tenant_id ON reservation_offers (tenant_id);
CREATE UNIQUE INDEX uq_reservation_offers_running ON reservation_offers
    (tenant_id, starts_at, COALESCE(staff_id, '00000000-0000-0000-0000-000000000000'::uuid))
    WHERE status = 'running';

CREATE TABLE reservation_offer_candidates (
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    offer_id uuid NOT NULL,
    waitlist_id uuid NOT NULL,
    position smallint NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'queued' CONSTRAINT ck_reservation_candidates_status
        CHECK (status IN ('queued', 'waiting', 'noreply', 'accepted', 'late_taken', 'late_won',
                          'skipped', 'stopped')),
    sent_at timestamptz,
    deadline_at timestamptz,
    answered_at timestamptz,
    PRIMARY KEY (offer_id, waitlist_id),
    CONSTRAINT fk_reservation_candidates_offer FOREIGN KEY (tenant_id, offer_id)
        REFERENCES reservation_offers (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_reservation_candidates_entry FOREIGN KEY (tenant_id, waitlist_id)
        REFERENCES reservation_waitlist (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_reservation_offer_candidates_tenant_id ON reservation_offer_candidates (tenant_id);

CREATE TABLE reservation_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    reservation_id uuid,
    offer_id uuid,
    waitlist_id uuid,
    kind varchar(24) NOT NULL CONSTRAINT ck_reservation_outbox_kind CHECK (kind IN (
        'confirmation', 'ask_confirmation', 'reminder', 'moved', 'cancelled', 'offer',
        'offer_won', 'offer_lost')),
    dedupe_key varchar(160) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'pending' CONSTRAINT ck_reservation_outbox_status
        CHECK (status IN ('pending', 'sent', 'failed', 'skipped')),
    skip_reason varchar(40),
    attempts smallint NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    message_id uuid,
    last_error varchar(300),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_reservation_outbox_dedupe UNIQUE (tenant_id, dedupe_key),
    CONSTRAINT fk_reservation_outbox_reservation FOREIGN KEY (tenant_id, reservation_id)
        REFERENCES reservations (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_reservation_outbox_offer FOREIGN KEY (tenant_id, offer_id)
        REFERENCES reservation_offers (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_reservation_outbox_entry FOREIGN KEY (tenant_id, waitlist_id)
        REFERENCES reservation_waitlist (tenant_id, id) ON DELETE CASCADE
);
CREATE INDEX ix_reservation_outbox_tenant_id ON reservation_outbox (tenant_id);
CREATE INDEX ix_reservation_outbox_due ON reservation_outbox (tenant_id, next_attempt_at)
    WHERE status = 'pending';
"""


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} USING {_POLICY} WITH CHECK {_POLICY}"
    )
    if table in APPEND_ONLY:
        grants = "SELECT, INSERT"
    elif table in DELETABLE:
        grants = "SELECT, INSERT, UPDATE, DELETE"
    else:
        grants = "SELECT, INSERT, UPDATE"
    op.execute(f"REVOKE ALL ON {table} FROM nexus_app")
    op.execute(f"GRANT {grants} ON {table} TO nexus_app")


def _check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    op.create_unique_constraint("uq_customers_tenant_id_id", "customers", ["tenant_id", "id"])
    op.create_unique_constraint(
        "uq_conversations_tenant_id_id", "conversations", ["tenant_id", "id"]
    )
    # asyncpg ejecuta una sentencia por llamada.
    for statement in (part.strip() for part in DDL.split(";")):
        if statement:
            op.execute(statement)
    for table in TABLES:
        _rls(table)

    _check(
        "client_access",
        "ck_client_access_modules",
        f"modules <@ ARRAY[{_MODULES_AFTER}]::varchar[]",
    )
    _check(
        "client_phones",
        "ck_client_phones_notice_kinds",
        f"notice_kinds <@ ARRAY[{_KINDS_AFTER}]::varchar[]",
    )
    _check("client_push_events", "ck_client_push_events_kind", f"kind IN ({_KINDS_AFTER})")
    op.execute("ALTER TABLE client_push_events ADD COLUMN reservation_id uuid")
    op.execute(
        "ALTER TABLE client_phones ALTER COLUMN notice_kinds SET DEFAULT "
        "ARRAY['inbox.waiting','inbox.message_for_you','client.balance',"
        "'reservas.agent_change','reservas.cancelled_today']::varchar[]"
    )
    op.execute(
        "UPDATE client_phones SET notice_kinds = notice_kinds "
        "|| ARRAY['reservas.agent_change','reservas.cancelled_today']::varchar[] "
        "WHERE NOT notice_kinds @> ARRAY['reservas.agent_change']::varchar[]"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE client_phones SET notice_kinds = ARRAY(SELECT k FROM unnest(notice_kinds) AS k "
        "WHERE k NOT LIKE 'reservas.%')"
    )
    op.execute("DELETE FROM client_push_events WHERE kind LIKE 'reservas.%'")
    op.execute("ALTER TABLE client_push_events DROP COLUMN IF EXISTS reservation_id")
    op.execute(
        "ALTER TABLE client_phones ALTER COLUMN notice_kinds SET DEFAULT "
        "ARRAY['inbox.waiting','inbox.message_for_you','client.balance']::varchar[]"
    )
    _check("client_push_events", "ck_client_push_events_kind", f"kind IN ({_KINDS_BEFORE})")
    _check(
        "client_phones",
        "ck_client_phones_notice_kinds",
        f"notice_kinds <@ ARRAY[{_KINDS_BEFORE}]::varchar[]",
    )
    op.execute("UPDATE client_access SET modules = array_remove(modules, 'reservas')")
    _check(
        "client_access",
        "ck_client_access_modules",
        f"modules <@ ARRAY[{_MODULES_BEFORE}]::varchar[]",
    )
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.drop_constraint("uq_conversations_tenant_id_id", "conversations", type_="unique")
    op.drop_constraint("uq_customers_tenant_id_id", "customers", type_="unique")
