"""Horarios, sedes, servicios y la compilación por revisión — spec 047, T055 (ola 2).

La segunda tanda de la ficha (``data-model.md`` §1 a §3):

- ``business_locations``: las sedes, con horario propio opcional.
- ``business_schedules`` + ``business_shifts``: **un** horario por negocio y uno
  por sede (``UNIQUE NULLS NOT DISTINCT``), por bloques o día por día. Las horas
  son minutos desde la medianoche del día que abre: un turno nocturno cierra
  después de 1.440 (research D15). Como mucho 6 turnos por día: lo valida el
  servicio.
- ``business_special_dates`` + ``business_special_shifts``: cierres o un horario
  distinto, de un día o de un rango, con nombre.
- ``business_faqs``.
- ``reservation_services`` (spec 043) gana lo que la ficha necesita: descripción,
  servicios no reservables (sin duración) y el tipo de precio. **Se conservan los
  nombres de 0172** (``duration_minutes``, ``price_minor``, ``currency``): los lee
  todo Reservas. La duración pasa a ir de 5 a 480 minutos, en pasos de 5.
- ``agent_services`` y ``agents.serves_all_services``: quién ofrece cada servicio
  (requisito 11.4, garantía 9).
- ``agent_version_compilations``: la historia de las compilaciones (research D4).
  El runtime sigue leyendo ``system_prompt_rendered``.

Todas por cliente, con RLS FORCE y FK compuestas.

Revision ID: 0183_business_hours_services
Revises: 0182_router_profiles_v1
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0183_business_hours_services"
down_revision: str | Sequence[str] | None = "0182_router_profiles_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

_SHIFT_CHECKS = (
    "open_min BETWEEN 0 AND 1439",
    "close_min BETWEEN 1 AND 2880",
    "close_min > open_min AND close_min - open_min <= 1440",
)

STATEMENTS = (
    """
    CREATE TABLE business_locations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name varchar(80) NOT NULL,
        address varchar(300),
        phone_e164 varchar(20),
        position integer NOT NULL DEFAULT 0,
        archived_at timestamptz,
        archived_by varchar(160),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_business_locations_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_business_locations_name CHECK (char_length(name) BETWEEN 1 AND 80),
        CONSTRAINT ck_business_locations_phone CHECK (
            phone_e164 IS NULL OR phone_e164 ~ '^\\+[1-9][0-9]{6,14}$'
        )
    )
    """,
    """
    CREATE TABLE business_schedules (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        location_id uuid,
        layout varchar(8) NOT NULL DEFAULT 'blocks',
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_business_schedules_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_business_schedules_owner UNIQUE NULLS NOT DISTINCT (tenant_id, location_id),
        CONSTRAINT ck_business_schedules_layout CHECK (layout IN ('blocks', 'daily')),
        CONSTRAINT fk_business_schedules_location FOREIGN KEY (tenant_id, location_id)
            REFERENCES business_locations (tenant_id, id) ON DELETE CASCADE
    )
    """,
    f"""
    CREATE TABLE business_shifts (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        schedule_id uuid NOT NULL,
        weekday smallint NOT NULL,
        open_min smallint NOT NULL,
        close_min smallint NOT NULL,
        CONSTRAINT uq_business_shifts_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_business_shifts_weekday CHECK (weekday BETWEEN 0 AND 6),
        CONSTRAINT ck_business_shifts_open CHECK ({_SHIFT_CHECKS[0]}),
        CONSTRAINT ck_business_shifts_close CHECK ({_SHIFT_CHECKS[1]}),
        CONSTRAINT ck_business_shifts_span CHECK ({_SHIFT_CHECKS[2]}),
        CONSTRAINT fk_business_shifts_schedule FOREIGN KEY (tenant_id, schedule_id)
            REFERENCES business_schedules (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_business_shifts_schedule ON business_shifts (tenant_id, schedule_id, weekday)",
    """
    CREATE TABLE business_special_dates (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        location_id uuid,
        name varchar(80) NOT NULL,
        date_from date NOT NULL,
        date_to date NOT NULL,
        closed boolean NOT NULL DEFAULT true,
        archived_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_business_special_dates_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_business_special_dates_range CHECK (date_to >= date_from),
        CONSTRAINT fk_business_special_dates_location FOREIGN KEY (tenant_id, location_id)
            REFERENCES business_locations (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_business_special_dates_range ON business_special_dates "
    "(tenant_id, date_from, date_to) WHERE archived_at IS NULL",
    f"""
    CREATE TABLE business_special_shifts (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        special_date_id uuid NOT NULL,
        open_min smallint NOT NULL,
        close_min smallint NOT NULL,
        CONSTRAINT uq_business_special_shifts_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_business_special_shifts_open CHECK ({_SHIFT_CHECKS[0]}),
        CONSTRAINT ck_business_special_shifts_close CHECK ({_SHIFT_CHECKS[1]}),
        CONSTRAINT ck_business_special_shifts_span CHECK ({_SHIFT_CHECKS[2]}),
        CONSTRAINT fk_business_special_shifts_date FOREIGN KEY (tenant_id, special_date_id)
            REFERENCES business_special_dates (tenant_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE business_faqs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        q varchar(300) NOT NULL,
        a varchar(2000) NOT NULL,
        suggested boolean NOT NULL DEFAULT false,
        position integer NOT NULL DEFAULT 0,
        archived_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_business_faqs_tenant_id UNIQUE (tenant_id, id)
    )
    """,
    """
    CREATE TABLE agent_services (
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid NOT NULL,
        service_id uuid NOT NULL,
        PRIMARY KEY (tenant_id, agent_id, service_id),
        CONSTRAINT fk_agent_services_agent FOREIGN KEY (tenant_id, agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_agent_services_service FOREIGN KEY (tenant_id, service_id)
            REFERENCES reservation_services (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_agent_services_service ON agent_services (tenant_id, service_id)",
    """
    CREATE TABLE agent_version_compilations (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_config_id uuid NOT NULL,
        business_rev bigint NOT NULL,
        knowledge_rev bigint NOT NULL DEFAULT 0,
        tools_hash char(64) NOT NULL,
        family_variant varchar(40),
        prompt text NOT NULL,
        sha256 char(64) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_version_compilations_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT fk_agent_version_compilations_version FOREIGN KEY (tenant_id, agent_config_id)
            REFERENCES agent_configs (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE UNIQUE INDEX uq_agent_version_compilations_key ON agent_version_compilations "
    "(tenant_id, agent_config_id, business_rev, knowledge_rev, (coalesce(family_variant, '')))",
)

TABLES = (
    "business_locations",
    "business_schedules",
    "business_shifts",
    "business_special_dates",
    "business_special_shifts",
    "business_faqs",
    "agent_services",
    "agent_version_compilations",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING {_POLICY} WITH CHECK {_POLICY}"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")

    op.execute("ALTER TABLE agents ADD COLUMN serves_all_services boolean NOT NULL DEFAULT true")

    op.execute("ALTER TABLE reservation_services ADD COLUMN description varchar(1000)")
    op.execute("ALTER TABLE reservation_services ADD COLUMN bookable boolean NOT NULL DEFAULT true")
    op.execute(
        "ALTER TABLE reservation_services ADD COLUMN price_kind varchar(8) NOT NULL DEFAULT 'none'"
    )
    op.execute(
        "UPDATE reservation_services SET price_kind = 'amount' WHERE price_minor IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE reservation_services ADD CONSTRAINT ck_reservation_services_price_kind "
        "CHECK (price_kind IN ('none', 'free', 'amount') "
        "AND (price_kind <> 'amount' OR price_minor IS NOT NULL))"
    )
    op.execute("ALTER TABLE reservation_services DROP CONSTRAINT ck_reservation_services_duration")
    op.execute("ALTER TABLE reservation_services ALTER COLUMN duration_minutes DROP NOT NULL")
    op.execute(
        "ALTER TABLE reservation_services ADD CONSTRAINT ck_reservation_services_duration "
        "CHECK ((bookable AND duration_minutes IS NOT NULL "
        "AND duration_minutes BETWEEN 5 AND 480 AND duration_minutes % 5 = 0) "
        "OR (NOT bookable AND duration_minutes IS NULL))"
    )


def downgrade() -> None:
    # A service that is not bookable has no duration, which 0172 cannot hold:
    # it goes back as an archived 15-minute service, so past bookings keep it.
    op.execute(
        "UPDATE reservation_services SET duration_minutes = 15, "
        "archived_at = coalesce(archived_at, now()) WHERE NOT bookable"
    )
    op.execute(
        "UPDATE reservation_services SET duration_minutes = "
        "greatest(15, least(480, (duration_minutes / 15) * 15)) "
        "WHERE duration_minutes % 15 <> 0 OR duration_minutes < 15"
    )
    op.execute(
        "ALTER TABLE reservation_services DROP CONSTRAINT IF EXISTS ck_reservation_services_duration"
    )
    op.execute("ALTER TABLE reservation_services ALTER COLUMN duration_minutes SET NOT NULL")
    op.execute(
        "ALTER TABLE reservation_services ADD CONSTRAINT ck_reservation_services_duration "
        "CHECK (duration_minutes >= 15 AND duration_minutes <= 480 "
        "AND (duration_minutes::integer % 15) = 0)"
    )
    op.execute(
        "ALTER TABLE reservation_services DROP CONSTRAINT IF EXISTS ck_reservation_services_price_kind"
    )
    op.execute("ALTER TABLE reservation_services DROP COLUMN IF EXISTS price_kind")
    op.execute("ALTER TABLE reservation_services DROP COLUMN IF EXISTS bookable")
    op.execute("ALTER TABLE reservation_services DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS serves_all_services")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
