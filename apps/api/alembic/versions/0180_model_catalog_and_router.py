"""El catálogo de modelos y el router — spec 047, T139 (ola 6, historia 12).

``model_profiles`` sigue siendo una fila por despliegue (ADR-036) y gana lo que
el router y la activación necesitan (``contracts/router-and-catalog.md`` §2):

- identidad: ``route`` y ``family`` (el juez tiene que ser de otra familia);
- residencia y retención: ``residency`` (``eu``, ``us`` o ``global``),
  ``zero_retention`` y ``retention_how``;
- licencia y contrato: ``license_id``, ``license_url``, ``license_read_at``,
  ``contract_dpa`` y ``subprocessor_listed``;
- ciclo de vida: los estados del catálogo y ``retire_after``. ``deprecated`` se
  conserva porque el código de hoy lo lee; pasa a ``retiring`` cuando el router
  sea el único lector;
- ``capabilities`` y ``quota``;
- ``offer_label``: la oferta fija de hoy en la consola (Sol, Terra y Luna, la
  constante ``RESPOND_MODELS``) pasa a datos.

Tablas nuevas:

- de plataforma, sin datos de clientes: ``model_prices`` (con vigencia),
  ``router_taxonomy`` (v1, las 15 tareas), ``router_profiles`` y
  ``model_task_certifications``;
- por cliente, con RLS FORCE y FK compuestas: ``agent_model_certifications`` y
  ``router_anomalies``.

Las filas de hoy quedan como están: Anthropic y OpenAI directos, que ya son
subprocesadores con contrato, con residencia ``global`` y sin retención cero
declarada (nadie la ha comprobado). Sus precios de hoy pasan a ``model_prices``
con vigencia desde la fecha de su fila.

Revision ID: 0180_model_catalog_and_router
Revises: 0179_business_profile
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0180_model_catalog_and_router"
down_revision: str | Sequence[str] | None = "0179_business_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

STATUSES = ("draft", "certifying", "active", "retiring", "retired", "unavailable", "deprecated")
_OLD_STATUSES = ("active", "deprecated")
RESIDENCIES = ("eu", "us", "global")
PROFILES = ("auto", "economy", "balanced", "max", "platform")
ANOMALY_KINDS = ("reserve_model", "no_model", "cooldown", "missing_task")
PAID_BY = ("partner", "auphere")

#: ``contracts/router-and-catalog.md`` §1. A new task is a new version.
TAXONOMY_V1: tuple[dict[str, object], ...] = (
    {"code": "classify", "conversation": False, "needs": ["strict_structured_outputs"]},
    {"code": "extract", "conversation": False, "needs": ["strict_structured_outputs"]},
    {"code": "answer", "conversation": True, "needs": ["context_window"]},
    {"code": "tool_turn", "conversation": True, "needs": ["tools"]},
    {"code": "escalate", "conversation": False, "needs": ["reasoning_control"]},
    {"code": "summarize", "conversation": False, "needs": []},
    {"code": "translate", "conversation": False, "needs": []},
    {"code": "vision", "conversation": False, "needs": ["vision"]},
    {"code": "transcribe", "conversation": False, "needs": ["audio"]},
    {"code": "embed", "conversation": False, "needs": ["embeddings"]},
    {"code": "rerank", "conversation": False, "needs": ["rerank"]},
    {"code": "moderate", "conversation": False, "needs": []},
    {"code": "judge", "conversation": False, "needs": ["structured_outputs", "other_family"]},
    {"code": "build", "conversation": False, "needs": ["strict_structured_outputs"]},
    {"code": "read_source", "conversation": False, "needs": ["structured_outputs"]},
)

#: The fixed offer of today (``core/respond_catalog.RESPOND_MODELS``).
OFFER = {
    "openai/gpt-5.6-sol": "Sol",
    "openai/gpt-5.6-terra": "Terra",
    "openai/gpt-5.6-luna": "Luna",
}
FAMILIES = {"anthropic": "anthropic-claude", "openai": "openai-gpt"}


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _status_check(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE model_profiles DROP CONSTRAINT IF EXISTS model_profiles_status_check")
    op.execute(
        "ALTER TABLE model_profiles ADD CONSTRAINT model_profiles_status_check "
        f"CHECK (status IN ({_in(values)}))"
    )


_COLUMNS = (
    ("route", "text"),
    ("family", "varchar(40)"),
    ("residency", "varchar(8) NOT NULL DEFAULT 'global'"),
    ("zero_retention", "boolean NOT NULL DEFAULT false"),
    ("retention_how", "varchar(60)"),
    ("license_id", "varchar(80)"),
    ("license_url", "text"),
    ("license_read_at", "timestamptz"),
    ("contract_dpa", "boolean NOT NULL DEFAULT false"),
    ("subprocessor_listed", "boolean NOT NULL DEFAULT false"),
    ("retire_after", "timestamptz"),
    ("capabilities", "jsonb NOT NULL DEFAULT '{}'::jsonb"),
    ("quota", "jsonb NOT NULL DEFAULT '{}'::jsonb"),
    ("offer_label", "varchar(40)"),
)

PLATFORM_TABLES = (
    """
    CREATE TABLE model_prices (
        deployment_id uuid NOT NULL REFERENCES model_profiles(id) ON DELETE CASCADE,
        valid_from date NOT NULL,
        unit varchar(24) NOT NULL DEFAULT 'per_million_tokens',
        input numeric(12,6),
        cache_read numeric(12,6),
        cache_write numeric(12,6),
        output numeric(12,6),
        audio_minute numeric(12,6),
        image numeric(12,6),
        surcharge jsonb,
        source_url text,
        currency char(3) NOT NULL DEFAULT 'USD',
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (deployment_id, valid_from)
    )
    """,
    """
    CREATE TABLE router_taxonomy (
        version integer PRIMARY KEY,
        tasks jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_router_taxonomy_version CHECK (version >= 1)
    )
    """,
    f"""
    CREATE TABLE router_profiles (
        profile varchar(16) NOT NULL,
        version integer NOT NULL,
        policy jsonb NOT NULL,
        published_by varchar(160) NOT NULL,
        reason text,
        published_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (profile, version),
        CONSTRAINT ck_router_profiles_profile CHECK (profile IN ({_in(PROFILES)})),
        CONSTRAINT ck_router_profiles_version CHECK (version >= 1)
    )
    """,
    """
    CREATE TABLE model_task_certifications (
        deployment_id uuid NOT NULL REFERENCES model_profiles(id) ON DELETE CASCADE,
        task varchar(32) NOT NULL,
        battery_version integer NOT NULL,
        scores jsonb NOT NULL,
        quality numeric(5,4) NOT NULL,
        passed boolean NOT NULL,
        certified_at timestamptz NOT NULL DEFAULT now(),
        invalidated_at timestamptz,
        PRIMARY KEY (deployment_id, task, battery_version),
        CONSTRAINT ck_model_task_cert_quality CHECK (quality BETWEEN 0 AND 1)
    )
    """,
)

TENANT_TABLES = (
    f"""
    CREATE TABLE agent_model_certifications (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        agent_id uuid NOT NULL,
        deployment_id uuid NOT NULL REFERENCES model_profiles(id) ON DELETE CASCADE,
        agent_config_id uuid NOT NULL,
        suite_revision integer NOT NULL,
        result jsonb NOT NULL,
        passed boolean NOT NULL,
        paid_by varchar(16) NOT NULL,
        certified_at timestamptz NOT NULL DEFAULT now(),
        invalidated_at timestamptz,
        CONSTRAINT uq_agent_model_cert_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_agent_model_cert_paid_by CHECK (paid_by IN ({_in(PAID_BY)})),
        CONSTRAINT fk_agent_model_cert_agent FOREIGN KEY (tenant_id, agent_id)
            REFERENCES agents (tenant_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_agent_model_cert_version FOREIGN KEY (tenant_id, agent_config_id)
            REFERENCES agent_configs (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_agent_model_cert_live ON agent_model_certifications "
    "(tenant_id, agent_id, deployment_id) WHERE invalidated_at IS NULL",
    f"""
    CREATE TABLE router_anomalies (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        task varchar(32) NOT NULL,
        kind varchar(16) NOT NULL,
        decision_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_router_anomalies_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_router_anomalies_kind CHECK (kind IN ({_in(ANOMALY_KINDS)}))
    )
    """,
    "CREATE INDEX ix_router_anomalies_recent ON router_anomalies (tenant_id, created_at DESC)",
)

_TENANT_NAMES = ("agent_model_certifications", "router_anomalies")
_PLATFORM_NAMES = (
    "model_prices",
    "router_taxonomy",
    "router_profiles",
    "model_task_certifications",
)


def upgrade() -> None:
    for name, ddl in _COLUMNS:
        op.execute(f"ALTER TABLE model_profiles ADD COLUMN {name} {ddl}")
    op.execute(
        "ALTER TABLE model_profiles ADD CONSTRAINT ck_model_profiles_residency "
        f"CHECK (residency IN ({_in(RESIDENCIES)}))"
    )
    _status_check(STATUSES)

    conn = op.get_bind()
    for provider, family in FAMILIES.items():
        conn.execute(
            sa.text(
                "UPDATE model_profiles SET family = :f, route = model_id, "
                "contract_dpa = true, subprocessor_listed = true WHERE provider = :p"
            ),
            {"f": family, "p": provider},
        )
    for model_id, label in OFFER.items():
        conn.execute(
            sa.text("UPDATE model_profiles SET offer_label = :l WHERE model_id = :m"),
            {"l": label, "m": model_id},
        )

    for ddl in PLATFORM_TABLES:
        op.execute(ddl)
    for name in _PLATFORM_NAMES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO nexus_app")

    # Today's prices, valid from the day their row was written.
    op.execute(
        """
        INSERT INTO model_prices (deployment_id, valid_from, input, cache_read, cache_write,
                                  output, audio_minute)
        SELECT id, created_at::date, price_input_per_mtok, price_cache_read_per_mtok,
               price_cache_write_per_mtok, price_output_per_mtok, price_per_minute
        FROM model_profiles
        """
    )
    conn.execute(
        sa.text("INSERT INTO router_taxonomy (version, tasks) VALUES (1, CAST(:t AS jsonb))"),
        {"t": json.dumps(list(TAXONOMY_V1))},
    )

    for ddl in TENANT_TABLES:
        op.execute(ddl)
    for table in _TENANT_NAMES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"USING {_POLICY} WITH CHECK {_POLICY}"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def downgrade() -> None:
    for table in reversed(_TENANT_NAMES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for table in reversed(_PLATFORM_NAMES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    # Anything the catalogue states that today's code does not know folds back.
    op.execute(
        "UPDATE model_profiles SET status = 'deprecated' "
        f"WHERE status NOT IN ({_in(_OLD_STATUSES)})"
    )
    _status_check(_OLD_STATUSES)
    op.execute("ALTER TABLE model_profiles DROP CONSTRAINT IF EXISTS ck_model_profiles_residency")
    for name, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE model_profiles DROP COLUMN IF EXISTS {name}")
