"""bloque E — agendapro browser MCP backing schema

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-09

Block E entrega el primer subprocess MCP server (Stagehand + Browserbase
Contexts, Node). Esta migración prepara el modelo de datos que usa:

1. ``scheduled_job_kind`` enum gana dos valores nuevos: ``health_check``
   (cron semanal del context Browserbase) y ``no_show_scrape`` (cron 22:00
   tenant TZ que ejecuta ``agendapro.scrape_no_shows``). Bloque H wirea el
   dispatcher real; Bloque E persiste los rows que el dispatcher consumirá.

2. ``tenant_credentials`` gana dos columnas:
   - ``needs_reauth`` (bool, default false): el health check lo flippea a
     true si el re-login automático falla, lo cual también dispara
     ``escalate.escalate_to_human`` para que el operador re-bootstrapee.
     ``booking.create_appointment`` revisa este flag antes de delegar a
     ``agendapro.*`` — si está true, cae al camino local Bloque D.
   - ``last_health_check_at`` (timestamptz, nullable): última vez que el
     context se verificó. El operator panel lo muestra; el cron lo updatea.

3. ``tool_status`` enum gana ``'internal'``. Las 6 tools ``agendapro.*``
   se seedean en Bloque E con este status. Significa: NO se incluyen en
   ``MCPRegistry.dispatch`` (LLM-facing), NO se whitelistean en
   ``agent_config.tools``. Solo invocables vía
   ``MCPRegistry.dispatch_internal`` desde dentro de los servers Bloque D
   (booking-server, principalmente). Defense in depth contra que un
   operador (o el LLM, alucinando un nombre) las alcance.

Screenshots de acciones mutativas se guardan en ``audit_log.after_json``
con keys ``screenshot_url``, ``screenshot_failed``, ``screenshot_error`` —
sin columna nueva. Bloque G (operator panel) las renderiza desde ahí.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── enum extensions ──────────────────────────────────────────────────
    # ``ALTER TYPE ... ADD VALUE`` se debe COMMITear ANTES de poder usarse
    # en otra statement. Si la migración 0009 (que inserta rows con
    # ``status='internal'``) corre en la misma transacción, Postgres tira
    # ``UnsafeNewEnumValueUsageError``. ``autocommit_block`` rompe la
    # transacción de la migración para que los ADD VALUE queden COMMITed
    # antes de que 0009 corra.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE scheduled_job_kind ADD VALUE IF NOT EXISTS 'health_check'")
        op.execute("ALTER TYPE scheduled_job_kind ADD VALUE IF NOT EXISTS 'no_show_scrape'")
        op.execute("ALTER TYPE tool_status ADD VALUE IF NOT EXISTS 'internal'")

    # ── tenant_credentials: needs_reauth + last_health_check_at ──────────
    op.add_column(
        "tenant_credentials",
        sa.Column(
            "needs_reauth",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "tenant_credentials",
        sa.Column(
            "last_health_check_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Index parcial: las consultas críticas son
    # "tenant X tiene integration='agendapro' usable?" — queremos que la
    # branch de booking.* haga un single index lookup.
    op.create_index(
        "ix_tenant_credentials_integration_active",
        "tenant_credentials",
        ["tenant_id", "integration"],
        unique=False,
        postgresql_where=sa.text("needs_reauth = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_credentials_integration_active",
        table_name="tenant_credentials",
    )
    op.drop_column("tenant_credentials", "last_health_check_at")
    op.drop_column("tenant_credentials", "needs_reauth")
    # Postgres no soporta DROP VALUE en enums sin recrear el tipo entero.
    # Se deja la extensión del enum sin reverso — los valores quedan
    # colgando pero no causan daño (no hay rows que los referencien tras
    # el downgrade ya que no se usan en esta migración).
