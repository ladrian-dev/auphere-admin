"""Reservas P3 — el Google Calendar de cada persona del equipo (spec 043, Historia 7).

Independiente del resto de la 043: sin esta migración, Reservas funciona igual
y simplemente no hay «ocupado» externo ni choques.

- ``reservation_staff_calendars``: qué calendario de la cuenta de Google que el
  cliente conectó (proveedor de consentimientos, spec 023) es de cada persona.
- ``reservation_busy``: los intervalos «ocupado» leídos de ese calendario.
  **Solo inicio y fin**: ni título, ni asistentes, ni descripción. Hacia fuera
  sale «Ocupado», y hacia dentro no entra más de lo necesario.

Las dos, por cliente con RLS FORCE y clave foránea compuesta a la persona.

Revision ID: 0174_reservation_calendars
Revises: 0173_reservations_tools
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0174_reservation_calendars"
down_revision: str | Sequence[str] | None = "0173_reservations_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

STATEMENTS = (
    """
    CREATE TABLE reservation_staff_calendars (
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        staff_id uuid NOT NULL,
        calendar_id varchar(255) NOT NULL,
        calendar_name varchar(255),
        last_sync_at timestamptz,
        last_error varchar(200),
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, staff_id),
        CONSTRAINT fk_staff_calendars_staff FOREIGN KEY (tenant_id, staff_id)
            REFERENCES reservation_staff (tenant_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE reservation_busy (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        staff_id uuid NOT NULL,
        starts_at timestamptz NOT NULL,
        ends_at timestamptz NOT NULL,
        source varchar(16) NOT NULL DEFAULT 'google',
        synced_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_reservation_busy_span CHECK (ends_at > starts_at),
        CONSTRAINT fk_reservation_busy_staff FOREIGN KEY (tenant_id, staff_id)
            REFERENCES reservation_staff (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_reservation_busy_staff ON reservation_busy (tenant_id, staff_id, starts_at)",
)

TABLES = ("reservation_staff_calendars", "reservation_busy")


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


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
