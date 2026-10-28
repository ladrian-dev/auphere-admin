"""Cada canal con su configuración — spec 047, T108 (requisitos 30.11, 31, 32 y 33;
``data-model.md`` §5).

- ``channels`` gana ``problem_reason`` (el motivo de «Con problemas»),
  ``audience_mode`` (``unset``, ``team_only``, ``everyone``), ``config_revision``
  (``If-Match``), ``coexistence`` y la pausa con su autor.
- ``channel_audience_numbers``: los números de prueba («Solo mi equipo») y las
  excepciones («A todos»).
- ``channel_escalation_recipients``: a quién avisa un escalado, por WhatsApp,
  correo o la Bandeja; como mucho 10 por canal.
- ``channel_config_changes``: el historial, con deshacer de 10 minutos.
- ``channel_signup_links`` (los enlaces del dueño) gana el agente, el modo
  ``whatsapp_login`` y como mucho un pendiente por agente.
- ``whatsapp_login_beta_countries`` (plataforma): dónde está activada la beta; un
  CHECK rechaza la UE y el EEE.
- ``conversations`` gana ``handled_by_agent_id`` y ``reception_hops`` (P3).

Revision ID: 0191_channel_config
Revises: 0190_agent_lifecycle
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0191_channel_config"
down_revision: str | Sequence[str] | None = "0190_agent_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
#: La UE y el EEE: la beta «WhatsApp login» no vale para números de aquí (D12).
EU_EEA = (
    "AT",
    "BE",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "FR",
    "DE",
    "GR",
    "HU",
    "IE",
    "IT",
    "LV",
    "LT",
    "LU",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",
    "IS",
    "LI",
    "NO",
    # Territorios de la UE con código propio: las regiones ultraperiféricas
    # francesas, San Martín y Åland.
    "GF",
    "GP",
    "MQ",
    "RE",
    "YT",
    "MF",
    "AX",
)


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _channel_fk(table: str) -> str:
    return (
        f"CONSTRAINT fk_{table}_channel FOREIGN KEY (tenant_id, channel_id) "
        "REFERENCES channels (tenant_id, id) ON DELETE CASCADE"
    )


STATEMENTS = (
    """
    ALTER TABLE channels
        ADD COLUMN problem_reason varchar(24),
        ADD COLUMN audience_mode varchar(12) NOT NULL DEFAULT 'unset',
        ADD COLUMN config_revision integer NOT NULL DEFAULT 0,
        ADD COLUMN coexistence boolean NOT NULL DEFAULT false,
        ADD COLUMN paused_by_kind varchar(16),
        ADD COLUMN paused_by_id varchar(160),
        ADD COLUMN paused_origin varchar(16),
        ADD COLUMN paused_at timestamptz,
        ADD CONSTRAINT ck_channels_problem_reason CHECK (
            problem_reason IS NULL
            OR problem_reason IN ('quality', 'auth_expired', 'coexistence_inactive', 'meta_error')
        ),
        ADD CONSTRAINT ck_channels_audience_mode CHECK (
            audience_mode IN ('unset', 'team_only', 'everyone')
        )
    """,
    f"""
    CREATE TABLE channel_audience_numbers (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        channel_id uuid NOT NULL,
        kind varchar(12) NOT NULL,
        phone_e164 varchar(20) NOT NULL,
        label varchar(60),
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_channel_audience_numbers_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT uq_channel_audience_numbers_number UNIQUE (tenant_id, channel_id, kind, phone_e164),
        CONSTRAINT ck_channel_audience_numbers_kind CHECK (kind IN ('test', 'exception')),
        CONSTRAINT ck_channel_audience_numbers_phone CHECK (phone_e164 ~ '^\\+[1-9][0-9]{{6,14}}$'),
        {_channel_fk("channel_audience_numbers")}
    )
    """,
    f"""
    CREATE TABLE channel_escalation_recipients (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        channel_id uuid NOT NULL,
        name varchar(80) NOT NULL,
        via varchar(12) NOT NULL,
        phone_e164 varchar(20),
        email varchar(320),
        client_user_id varchar(160),
        position smallint NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_channel_escalation_recipients_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_channel_escalation_recipients_via CHECK (via IN ('whatsapp', 'email', 'inbox')),
        CONSTRAINT ck_channel_escalation_recipients_target CHECK (
            (via = 'whatsapp' AND phone_e164 IS NOT NULL)
            OR (via = 'email' AND email IS NOT NULL)
            OR via = 'inbox'
        ),
        {_channel_fk("channel_escalation_recipients")}
    )
    """,
    f"""
    CREATE TABLE channel_config_changes (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        channel_id uuid NOT NULL,
        before jsonb,
        after jsonb NOT NULL,
        actor varchar(160) NOT NULL,
        origin varchar(16) NOT NULL,
        at timestamptz NOT NULL DEFAULT now(),
        undo_until timestamptz,
        undone_at timestamptz,
        CONSTRAINT uq_channel_config_changes_tenant_id UNIQUE (tenant_id, id),
        {_channel_fk("channel_config_changes")}
    )
    """,
    "CREATE INDEX ix_channel_config_changes_channel ON channel_config_changes (tenant_id, channel_id, at DESC)",
    """
    ALTER TABLE channel_signup_links
        ADD COLUMN agent_id uuid,
        DROP CONSTRAINT ck_channel_signup_links_mode,
        ADD CONSTRAINT ck_channel_signup_links_mode CHECK (
            mode IN ('coexistence', 'cloud_api', 'whatsapp_login')
        ),
        ADD CONSTRAINT fk_channel_signup_links_agent FOREIGN KEY (tenant_id, agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE CASCADE
    """,
    "CREATE UNIQUE INDEX uq_channel_signup_links_one_pending ON channel_signup_links (tenant_id, agent_id) "
    "WHERE consumed_at IS NULL AND revoked_at IS NULL AND agent_id IS NOT NULL",
    f"""
    CREATE TABLE whatsapp_login_beta_countries (
        country char(2) PRIMARY KEY,
        enabled_at timestamptz NOT NULL DEFAULT now(),
        enabled_by varchar(160) NOT NULL,
        CONSTRAINT ck_whatsapp_login_beta_not_eu CHECK (country NOT IN ({_in(EU_EEA)})),
        CONSTRAINT ck_whatsapp_login_beta_country CHECK (country ~ '^[A-Z]{{2}}$')
    )
    """,
    """
    ALTER TABLE conversations
        ADD COLUMN handled_by_agent_id uuid,
        ADD COLUMN reception_hops smallint NOT NULL DEFAULT 0,
        ADD CONSTRAINT fk_conversations_handled_by_agent FOREIGN KEY (tenant_id, handled_by_agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE SET NULL (handled_by_agent_id)
    """,
)
TENANT_TABLES = (
    "channel_audience_numbers",
    "channel_escalation_recipients",
    "channel_config_changes",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} USING {_POLICY} WITH CHECK {_POLICY}"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_login_beta_countries TO nexus_app")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE conversations DROP CONSTRAINT IF EXISTS fk_conversations_handled_by_agent, "
        "DROP COLUMN IF EXISTS reception_hops, DROP COLUMN IF EXISTS handled_by_agent_id"
    )
    op.execute("DROP TABLE IF EXISTS whatsapp_login_beta_countries")
    op.execute("DROP INDEX IF EXISTS uq_channel_signup_links_one_pending")
    op.execute(
        "ALTER TABLE channel_signup_links DROP CONSTRAINT IF EXISTS fk_channel_signup_links_agent, "
        "DROP COLUMN IF EXISTS agent_id, DROP CONSTRAINT IF EXISTS ck_channel_signup_links_mode, "
        "ADD CONSTRAINT ck_channel_signup_links_mode CHECK (mode IN ('coexistence', 'cloud_api'))"
    )
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute(
        """
        ALTER TABLE channels
            DROP CONSTRAINT IF EXISTS ck_channels_audience_mode,
            DROP CONSTRAINT IF EXISTS ck_channels_problem_reason,
            DROP COLUMN IF EXISTS paused_at,
            DROP COLUMN IF EXISTS paused_origin,
            DROP COLUMN IF EXISTS paused_by_id,
            DROP COLUMN IF EXISTS paused_by_kind,
            DROP COLUMN IF EXISTS coexistence,
            DROP COLUMN IF EXISTS config_revision,
            DROP COLUMN IF EXISTS audience_mode,
            DROP COLUMN IF EXISTS problem_reason
        """
    )
