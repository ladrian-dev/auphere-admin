"""La ficha del negocio — spec 047, T046 (ola 2, historias 3 y 4).

La ficha vive en tablas por cliente; el ClientSpec es su vista tipada (research
D3). Esta migración trae lo del alta y la lectura de la web; las sedes, los
horarios, las fechas especiales, los servicios y las preguntas frecuentes llegan
con la T055.

- ``business_profiles`` (1:1 con el cliente): nicho, información (dato no
  confiable, §III), web, país, zona, moneda de los precios, «Solo UE»,
  restricción soberana, políticas y ``content_rev``, que sube con **cualquier**
  cambio de la ficha y entra en la clave de compilación del agente.
- ``business_sections``: la revisión de cada sección para ``If-Match`` y su
  estado (requisito 8.5). Dos personas editando secciones distintas no chocan.
- ``business_field_provenance``: de dónde viene cada dato hoy (requisito 13).
- ``business_changes``: el historial y el deshacer.
- ``business_suggestions``: lo leído que no se aplicó solo (requisito 5.8).
- ``business_links``: la web y las redes del negocio.

Todas por cliente, con RLS FORCE. Los clientes en ``provisioning`` pasan a
``active`` en la migración de datos del track del alta, no aquí: ese cambio
toca el runtime y se comprueba aparte.

Revision ID: 0179_business_profile
Revises: 0178_single_draft
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0179_business_profile"
down_revision: str | Sequence[str] | None = "0178_single_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

SECTIONS = (
    "basics",
    "locations",
    "hours",
    "special_dates",
    "services",
    "policies",
    "faqs",
    "sources",
    "links",
)
SECTION_STATES = ("complete", "read_pending", "pending", "optional")
SOURCES = (
    "person",
    "web",
    "document",
    "social",
    "migrated",
    "builder",
    "inbox_correction",
    "import",
)
ORIGINS = ("console", "lite_web", "app", "admin", "api", "system")
ACTOR_KINDS = ("partner_member", "client_user", "operator", "system", "builder")
REVIEWS = ("pending", "confirmed")
CHANGE_KINDS = (
    "edit",
    "read_applied",
    "builder_applied",
    "correction",
    "migration",
    "import",
    "undo",
)
DECISIONS = ("accepted", "edited", "discarded")
NETWORKS = ("web", "instagram", "facebook", "tiktok", "linkedin", "youtube", "x", "threads")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


STATEMENTS = (
    """
    CREATE TABLE business_profiles (
        tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
        niche varchar(80) NOT NULL,
        info text,
        website text,
        country char(2),
        timezone varchar(64) NOT NULL,
        price_currency char(3),
        eu_only boolean NOT NULL DEFAULT false,
        sovereign boolean NOT NULL DEFAULT false,
        policies jsonb NOT NULL DEFAULT '{}'::jsonb,
        content_rev bigint NOT NULL DEFAULT 1,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_business_profiles_niche CHECK (char_length(niche) BETWEEN 2 AND 80),
        CONSTRAINT ck_business_profiles_info CHECK (info IS NULL OR char_length(info) <= 2000),
        CONSTRAINT ck_business_profiles_country CHECK (country IS NULL OR country ~ '^[A-Z]{2}$'),
        CONSTRAINT ck_business_profiles_currency CHECK (
            price_currency IS NULL OR price_currency ~ '^[A-Z]{3}$'
        ),
        CONSTRAINT ck_business_profiles_rev CHECK (content_rev >= 1)
    )
    """,
    f"""
    CREATE TABLE business_sections (
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        section varchar(16) NOT NULL,
        revision integer NOT NULL DEFAULT 0,
        state varchar(16) NOT NULL DEFAULT 'pending',
        updated_at timestamptz NOT NULL DEFAULT now(),
        updated_by_kind varchar(16),
        updated_by_id varchar(160),
        updated_origin varchar(16),
        PRIMARY KEY (tenant_id, section),
        CONSTRAINT ck_business_sections_section CHECK (section IN ({_in(SECTIONS)})),
        CONSTRAINT ck_business_sections_state CHECK (state IN ({_in(SECTION_STATES)})),
        CONSTRAINT ck_business_sections_by CHECK (
            updated_by_kind IS NULL OR updated_by_kind IN ({_in(ACTOR_KINDS)})
        ),
        CONSTRAINT ck_business_sections_origin CHECK (
            updated_origin IS NULL OR updated_origin IN ({_in(ORIGINS)})
        ),
        CONSTRAINT ck_business_sections_revision CHECK (revision >= 0)
    )
    """,
    f"""
    CREATE TABLE business_field_provenance (
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        pointer varchar(300) NOT NULL,
        source varchar(20) NOT NULL,
        actor_kind varchar(16),
        actor_id varchar(160),
        origin varchar(16) NOT NULL,
        source_url text,
        translated_from varchar(16),
        review varchar(16) NOT NULL DEFAULT 'confirmed',
        at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, pointer),
        CONSTRAINT ck_business_provenance_source CHECK (source IN ({_in(SOURCES)})),
        CONSTRAINT ck_business_provenance_actor CHECK (
            actor_kind IS NULL OR actor_kind IN ({_in(ACTOR_KINDS)})
        ),
        CONSTRAINT ck_business_provenance_origin CHECK (origin IN ({_in(ORIGINS)})),
        CONSTRAINT ck_business_provenance_review CHECK (review IN ({_in(REVIEWS)}))
    )
    """,
    f"""
    CREATE TABLE business_changes (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        section varchar(16) NOT NULL,
        kind varchar(20) NOT NULL,
        before jsonb,
        after jsonb,
        actor_kind varchar(16),
        actor_id varchar(160),
        origin varchar(16) NOT NULL,
        at timestamptz NOT NULL DEFAULT now(),
        undone_at timestamptz,
        undone_by varchar(160),
        undo_of uuid,
        CONSTRAINT uq_business_changes_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_business_changes_section CHECK (section IN ({_in(SECTIONS)})),
        CONSTRAINT ck_business_changes_kind CHECK (kind IN ({_in(CHANGE_KINDS)})),
        CONSTRAINT ck_business_changes_actor CHECK (
            actor_kind IS NULL OR actor_kind IN ({_in(ACTOR_KINDS)})
        ),
        CONSTRAINT ck_business_changes_origin CHECK (origin IN ({_in(ORIGINS)})),
        CONSTRAINT fk_business_changes_undo_of FOREIGN KEY (tenant_id, undo_of)
            REFERENCES business_changes (tenant_id, id) ON DELETE SET NULL (undo_of)
    )
    """,
    "CREATE INDEX ix_business_changes_section ON business_changes (tenant_id, section, at DESC)",
    f"""
    CREATE TABLE business_suggestions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        pointer varchar(300) NOT NULL,
        proposed_value jsonb NOT NULL,
        current_value jsonb,
        source varchar(20) NOT NULL,
        source_url text,
        translated_from varchar(16),
        created_at timestamptz NOT NULL DEFAULT now(),
        decided_at timestamptz,
        decided_by varchar(160),
        decision varchar(16),
        CONSTRAINT uq_business_suggestions_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_business_suggestions_source CHECK (source IN ({_in(SOURCES)})),
        CONSTRAINT ck_business_suggestions_decision CHECK (
            (decision IS NULL) = (decided_at IS NULL)
            AND (decision IS NULL OR decision IN ({_in(DECISIONS)}))
        )
    )
    """,
    "CREATE INDEX ix_business_suggestions_open ON business_suggestions (tenant_id, created_at) "
    "WHERE decision IS NULL",
    f"""
    CREATE TABLE business_links (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        network varchar(16) NOT NULL,
        url text,
        handle varchar(120),
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_business_links_tenant_id UNIQUE (tenant_id, id),
        CONSTRAINT ck_business_links_network CHECK (network IN ({_in(NETWORKS)})),
        CONSTRAINT ck_business_links_target CHECK (url IS NOT NULL OR handle IS NOT NULL)
    )
    """,
    "CREATE UNIQUE INDEX uq_business_links_target ON business_links "
    "(tenant_id, network, (coalesce(handle, url)))",
)

TABLES = (
    "business_profiles",
    "business_sections",
    "business_field_provenance",
    "business_changes",
    "business_suggestions",
    "business_links",
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


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
