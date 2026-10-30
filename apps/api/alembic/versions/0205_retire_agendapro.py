"""Spec 048: AgendaPro se va del todo y ``booking.*`` queda retirada.

Revision ID: 0205_retire_agendapro
Revises: 0204_console_v2_for_all

Ningún cliente usa AgendaPro (owner, 2026-10-29). Antes de tocar nada, la
migración **lo comprueba**: si un cliente tiene la URL pública de AgendaPro
puesta, una conexión de AgendaPro que no esté desconectada o sus credenciales
guardadas, falla, nombra a esos clientes y no cambia nada. Borrar en silencio la
configuración de un cliente rompería su agente; el operador la quita antes, a
sabiendas, y se vuelve a desplegar.

Sin nadie que lo use:

1. borra los ``tenant_connectors`` del conector (FK RESTRICT; precedente 0014)
   y el conector, para que ``release.sh`` —que siembra y nunca poda— no tenga
   nada que mantener (su YAML se fue en el mismo cambio);
2. borra las filas ``agendapro.*`` de ``tool_catalog``, también
   ``agendapro.get_today_appointments`` y ``agendapro.scrape_no_shows``, que la
   0021 olvidó (y antes sus excepciones por cliente, FK RESTRICT);
3. borra ``tenants.agendapro_public_url`` y ``appointments.public_booking_status``
   con su índice parcial y su restricción (0022);
4. cancela los ``scheduled_jobs`` pendientes de ``no_show_scrape`` y
   ``async_booking``: sus crons ya no existen. Los valores del enum se quedan
   (quitarlos exige rehacer el tipo, y no aporta nada);
5. marca ``booking.*`` como retiradas con el estado que ya existe para eso,
   ``deprecated`` (``plan.md`` §Decisiones): el constructor, el copiloto, la
   consola y el panel no la ofrecen, ``AgentConfigService`` la sigue aceptando
   en una versión que ya la tiene y el runtime la sigue ejecutando hasta el
   borrado final (requisito 5). Suelta también el ``connector_id`` que la 0019
   pudo dejarle apuntando a AgendaPro en una base de larga vida;
6. siembra la frase de auditoría de «Pasar a Reservas» (``reservations.passed``).

Corre con ``row_security = off``: con el rol de migraciones (que salta la RLS)
no cambia nada, y con uno que no la saltara la comprobación fallaría en voz alta
en lugar de no ver a nadie y seguir.

El ``downgrade`` vuelve a crear las dos columnas (vacías) y devuelve
``booking.*`` a ``active``; no recrea el conector, ni las filas del catálogo, ni
los trabajos cancelados.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0205_retire_agendapro"
down_revision: str | Sequence[str] | None = "0204_console_v2_for_all"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOKING: tuple[str, ...] = (
    "booking.check_availability",
    "booking.create_appointment",
    "booking.modify_appointment",
    "booking.cancel_appointment",
    "booking.get_appointments",
)

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "reservations.passed",
        "clients",
        "info",
        "Auphere pasó a {client} a Reservas.",
        "Auphere moved {client} to Reservations.",
    ),
)

#: Quién tiene AgendaPro configurado: la URL pública, una conexión que no esté
#: desconectada o unas credenciales guardadas.
_USERS = sa.text(
    """
    SELECT t.name, t.slug
    FROM tenants t
    WHERE NULLIF(btrim(t.agendapro_public_url), '') IS NOT NULL
       OR EXISTS (
            SELECT 1
            FROM tenant_connectors tc
            JOIN connectors c ON c.id = tc.connector_id
            WHERE c.slug = 'agendapro'
              AND tc.tenant_id = t.id
              AND tc.status <> 'disconnected'
       )
       OR EXISTS (
            SELECT 1 FROM tenant_credentials cr
            WHERE cr.tenant_id = t.id AND cr.integration = 'agendapro'
       )
    ORDER BY t.name, t.slug
    """
)


class AgendaProStillInUse(RuntimeError):
    """Some client still has AgendaPro configured: nothing was changed."""


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("SET LOCAL row_security = off"))

    users = bind.execute(_USERS).all()
    if users:
        names = ", ".join(f"{name} ({slug})" for name, slug in users)
        raise AgendaProStillInUse(
            "0205_retire_agendapro: estos clientes tienen AgendaPro configurado "
            f"(URL pública, conexión o credenciales): {names}. Quítalo de cada uno "
            "antes de desplegar; la migración no ha cambiado nada."
        )

    # 1. El conector y lo que cuelga de él.
    bind.execute(
        sa.text(
            "DELETE FROM tenant_connectors WHERE connector_id IN "
            "(SELECT id FROM connectors WHERE slug = 'agendapro')"
        )
    )
    # 5 (antes que el conector, para decirlo explícito): booking.* retiradas.
    bind.execute(
        sa.text(
            "UPDATE tool_catalog SET status = 'deprecated', connector_id = NULL, "
            "updated_at = now() WHERE name = ANY(:names)"
        ),
        {"names": list(BOOKING)},
    )
    bind.execute(sa.text("DELETE FROM connectors WHERE slug = 'agendapro'"))

    # 2. Las filas agendapro.* del catálogo.
    bind.execute(
        sa.text("DELETE FROM tenant_connector_tool_overrides WHERE tool_name LIKE 'agendapro%'")
    )
    bind.execute(sa.text("DELETE FROM tool_catalog WHERE name LIKE 'agendapro%'"))

    # 3. Las dos columnas.
    op.drop_column("tenants", "agendapro_public_url")
    op.drop_index("ix_appointments_public_pending", table_name="appointments")
    op.drop_constraint("ck_appointments_public_booking_status", "appointments", type_="check")
    op.drop_column("appointments", "public_booking_status")

    # 4. Los trabajos que ya no tienen quién los haga. ``kind::text``: en una
    # base nueva Alembic corre todas las migraciones en una transacción, y un
    # valor de enum añadido en ella (0022) no se puede usar como literal hasta
    # que se confirma.
    bind.execute(
        sa.text(
            "UPDATE scheduled_jobs SET status = 'cancelled', updated_at = now(), "
            "last_error = 'spec 048: AgendaPro retirado' "
            "WHERE status = 'pending' AND kind::text IN ('no_show_scrape', 'async_booking')"
        )
    )

    # 6. La frase de auditoría del paso a Reservas.
    for action, category, severity, summary_es, summary_en in VOCABULARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT
                    CAST(:action AS VARCHAR(80)),
                    CAST(:category AS VARCHAR(40)),
                    CAST(:severity AS VARCHAR(10)),
                    CAST(:summary_es AS TEXT),
                    CAST(:summary_en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary
                    WHERE action = CAST(:action AS VARCHAR(80))
                )
                """
            ),
            {
                "action": action,
                "category": category,
                "severity": severity,
                "summary_es": summary_es,
                "summary_en": summary_en,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"),
        {"a": "reservations.passed"},
    )
    bind.execute(
        sa.text("UPDATE tool_catalog SET status = 'active' WHERE name = ANY(:names)"),
        {"names": list(BOOKING)},
    )
    op.add_column("tenants", sa.Column("agendapro_public_url", sa.Text(), nullable=True))
    op.add_column("appointments", sa.Column("public_booking_status", sa.String(20), nullable=True))
    op.create_check_constraint(
        "ck_appointments_public_booking_status",
        "appointments",
        "public_booking_status IS NULL OR public_booking_status IN ("
        "'pending', 'in_progress', 'confirmed', 'failed', 'manual_escalation')",
    )
    op.create_index(
        "ix_appointments_public_pending",
        "appointments",
        ["tenant_id", "created_at"],
        postgresql_where=sa.text("public_booking_status IN ('pending', 'in_progress')"),
    )
