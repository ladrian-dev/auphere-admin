"""Reservas — cada profesional conecta su calendario (spec 043, requisito 12).

Hasta aquí había una cuenta de Google por negocio y cada persona elegía un calendario
de esa cuenta. Cada profesional tiene su cuenta y sus horas, así que la conexión pasa a
ser suya, en la misma fila:

- ``connection_id`` y ``connection_user_id``: su cuenta en el proveedor, con una
  identidad propia (``tenant_<slug>_staff_<id>``). No salen por la API;
- ``connection_status``: ``pending`` (se pidió y no ha terminado), ``connected``,
  ``needs_reauth`` y ``disconnecting`` (se soltó y falta quitar sus eventos);
- ``status_since``: desde cuándo está así. Un enlace sin terminar caduca;
- ``account_label``: qué cuenta quedó conectada, para que se vea si no era la suya;
- ``previous_connection_id`` y ``previous_user_id``: la conexión que funcionaba mientras se
  autoriza otra. Se suelta cuando la nueva ya está: es la única que llega a sus eventos;
- ``calendar_id`` puede faltar: conectado y sin calendario elegido.

**Un calendario, un profesional** (R12.4): índice único parcial, además de la
comprobación de la API, porque dos peticiones a la vez pasarían las dos.

Las filas que ya había se quedan en permiso perdido: su conexión era la del negocio. La
pantalla pide volver a conectar y conservan su calendario.

``reservation_busy.source`` ya existía y ahora tiene dos valores: ``google``, el calendario de
la persona; ``business``, el Google del negocio, que se sigue leyendo para no volver a dar una
hora que ya estaba dada, hasta que cada persona conecte el suyo (R12.13).

Revision ID: 0228_staff_calendar_connections
Revises: 0227_notice_handled
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0228_staff_calendar_connections"
down_revision: str | Sequence[str] | None = "0227_notice_handled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = "('pending', 'connected', 'needs_reauth', 'disconnecting')"

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "reservations.calendar_connect_started",
        "clients",
        "info",
        "{actor} pidió conectar el calendario de Google de {staff} en {client}.",
        "{actor} asked to connect the Google calendar of {staff} at {client}.",
    ),
    (
        "reservations.calendar_changed",
        "clients",
        "info",
        "{actor} cambió el calendario de Google de {staff} en {client}.",
        "{actor} changed the Google calendar of {staff} at {client}.",
    ),
    (
        "reservations.calendar_disconnected",
        "clients",
        "warning",
        "{actor} desconectó el calendario de Google de {staff} en {client}.",
        "{actor} disconnected the Google calendar of {staff} at {client}.",
    ),
    (
        "reservations.pass_failed",
        "clients",
        "warning",
        "Auphere no pudo pasar a {client} a Reservas; sus agentes siguen como estaban.",
        "Auphere could not move {client} to Reservations; its agents stay as they were.",
    ),
)


def upgrade() -> None:
    # Las filas de todos los clientes, como la 0205: la tabla tiene RLS forzado.
    op.get_bind().execute(sa.text("SET LOCAL row_security = off"))
    op.execute("ALTER TABLE reservation_staff_calendars ALTER COLUMN calendar_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE reservation_staff_calendars "
        "ADD COLUMN connection_id varchar(255), "
        "ADD COLUMN connection_user_id varchar(255), "
        # El valor por defecto de la columna rellena las filas que había, sin pasar por RLS.
        "ADD COLUMN connection_status varchar(16) NOT NULL DEFAULT 'needs_reauth', "
        "ADD COLUMN status_since timestamptz NOT NULL DEFAULT now(), "
        "ADD COLUMN account_label varchar(255), "
        "ADD COLUMN previous_connection_id varchar(255), "
        "ADD COLUMN previous_user_id varchar(255)"
    )
    op.execute(
        "ALTER TABLE reservation_staff_calendars ALTER COLUMN connection_status SET DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE reservation_staff_calendars "
        "ADD CONSTRAINT ck_staff_calendars_connection_status "
        f"CHECK (connection_status IN {_STATES})"
    )
    # Dos personas con el mismo calendario son calendarios mezclados: la segunda se queda
    # sin él y lo elige de nuevo.
    op.execute(
        "UPDATE reservation_staff_calendars AS c SET calendar_id = NULL, calendar_name = NULL "
        "FROM (SELECT tenant_id, staff_id, row_number() OVER ("
        "  PARTITION BY tenant_id, calendar_id ORDER BY created_at, staff_id) AS n "
        "  FROM reservation_staff_calendars WHERE calendar_id IS NOT NULL) AS d "
        "WHERE c.tenant_id = d.tenant_id AND c.staff_id = d.staff_id AND d.n > 1"
    )
    op.execute(
        "ALTER TABLE reservation_busy "
        "ADD CONSTRAINT ck_reservation_busy_source CHECK (source IN ('google', 'business'))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_staff_calendars_calendar "
        "ON reservation_staff_calendars (tenant_id, calendar_id) "
        "WHERE calendar_id IS NOT NULL AND connection_status <> 'disconnecting'"
    )
    # Una persona archivada ya no hace ningún servicio (R14.5): si no, su ficha no se puede guardar.
    op.execute(
        "DELETE FROM reservation_service_staff AS s USING reservation_staff AS m "
        "WHERE s.tenant_id = m.tenant_id AND s.staff_id = m.id AND m.archived_at IS NOT NULL"
    )
    bind = op.get_bind()
    for action, category, severity, es, en in VOCABULARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT CAST(:a AS VARCHAR(80)), CAST(:c AS VARCHAR(40)),
                       CAST(:s AS VARCHAR(10)), CAST(:es AS TEXT), CAST(:en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary WHERE action = CAST(:a AS VARCHAR(80))
                )
                """
            ),
            {"a": action, "c": category, "s": severity, "es": es, "en": en},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("SET LOCAL row_security = off"))
    for action, *_ in VOCABULARY:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": action}
        )
    op.execute("DROP INDEX uq_staff_calendars_calendar")
    op.execute("DELETE FROM reservation_busy WHERE source = 'business'")
    op.execute("ALTER TABLE reservation_busy DROP CONSTRAINT ck_reservation_busy_source")
    op.execute(
        "ALTER TABLE reservation_staff_calendars "
        "DROP CONSTRAINT ck_staff_calendars_connection_status"
    )
    # Sin calendario no había fila: lo que no llegó a elegir uno se va con la conexión.
    op.execute("DELETE FROM reservation_staff_calendars WHERE calendar_id IS NULL")
    op.execute(
        "ALTER TABLE reservation_staff_calendars "
        "DROP COLUMN connection_id, "
        "DROP COLUMN connection_user_id, "
        "DROP COLUMN connection_status, "
        "DROP COLUMN status_since, "
        "DROP COLUMN account_label, "
        "DROP COLUMN previous_connection_id, "
        "DROP COLUMN previous_user_id"
    )
    op.execute("ALTER TABLE reservation_staff_calendars ALTER COLUMN calendar_id SET NOT NULL")
