"""Clics de anuncio, medición por número y cola de eventos de conversión — spec 076.

- ``customer_ad_referrals``: un clic de anuncio o de publicación de un contacto
  (el ``referral`` del mensaje de WhatsApp). El ``ctwa_clid`` se borra a los 90
  días (cron del worker); el resto del origen se conserva.
- ``channel_ad_measurement``: si un número envía sus resultados a Meta, quién lo
  activó y el conjunto de datos de Meta vinculado. Vive aparte de las
  credenciales para que una reconexión no lo borre.
- ``ad_conversion_events``: la cola de eventos que el despachador de ``egress``
  envía a la API de conversiones. **No guarda el teléfono**, ni en claro ni
  cifrado: se lee y se cifra al enviar.

Las tres llevan RLS forzada por tenant, FK a ``tenants`` con borrado en cascada y
FK compuestas ``(tenant_id, x_id)`` hacia las tablas de tenant.

Y la frase de auditoría de ``console.channel.ad_measurement``.

Revision ID: 0241_ad_conversions
Revises: 0240_respond_bindings_to_agents
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0241_ad_conversions"
down_revision: str | Sequence[str] | None = "0240_respond_bindings_to_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"

_TABLES = ("customer_ad_referrals", "channel_ad_measurement", "ad_conversion_events")

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "console.channel.ad_measurement",
        "channels",
        "info",
        "{actor} cambió la medición de resultados de anuncios de un número de {client}.",
        "{actor} changed ad results measurement for a number of {client}.",
    ),
)


def _secure(table: str) -> None:
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} USING {_POLICY} WITH CHECK {_POLICY}"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE customer_ad_referrals (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            customer_id uuid NOT NULL,
            conversation_id uuid NULL,
            channel_id uuid NOT NULL,
            provider_message_id varchar(512) NOT NULL,
            source_type varchar(8) NOT NULL,
            source_id varchar(64) NULL,
            source_url varchar(512) NULL,
            headline varchar(200) NULL,
            ad_text varchar(500) NULL,
            media_type varchar(16) NULL,
            ctwa_clid varchar(256) NULL,
            ref varchar(128) NULL,
            clicked_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_customer_ad_referrals_message
                UNIQUE (tenant_id, provider_message_id),
            CONSTRAINT uq_customer_ad_referrals_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT ck_customer_ad_referrals_source_type
                CHECK (source_type IN ('ad', 'post')),
            CONSTRAINT fk_customer_ad_referrals_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_customer_ad_referrals_customer
                FOREIGN KEY (tenant_id, customer_id)
                REFERENCES customers (tenant_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_customer_ad_referrals_conversation
                FOREIGN KEY (tenant_id, conversation_id)
                REFERENCES conversations (tenant_id, id) ON DELETE SET NULL (conversation_id),
            CONSTRAINT fk_customer_ad_referrals_channel
                FOREIGN KEY (tenant_id, channel_id)
                REFERENCES channels (tenant_id, id) ON DELETE CASCADE
        )
        """
    )
    op.create_index(
        "ix_customer_ad_referrals_last_click",
        "customer_ad_referrals",
        ["tenant_id", "customer_id", "channel_id", sa.text("clicked_at DESC")],
    )
    op.create_index(
        "ix_customer_ad_referrals_clicked_at", "customer_ad_referrals", ["tenant_id", "clicked_at"]
    )
    _secure("customer_ad_referrals")

    op.execute(
        """
        CREATE TABLE channel_ad_measurement (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            channel_id uuid NOT NULL,
            enabled boolean NOT NULL DEFAULT false,
            meta_dataset_id varchar(64) NULL,
            enabled_by varchar(255) NULL,
            enabled_at timestamptz NULL,
            disabled_by varchar(255) NULL,
            disabled_at timestamptz NULL,
            last_error_code varchar(40) NULL,
            last_error_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_channel_ad_measurement_channel UNIQUE (tenant_id, channel_id),
            CONSTRAINT fk_channel_ad_measurement_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_channel_ad_measurement_channel
                FOREIGN KEY (tenant_id, channel_id)
                REFERENCES channels (tenant_id, id) ON DELETE CASCADE
        )
        """
    )
    _secure("channel_ad_measurement")

    op.execute(
        """
        CREATE TABLE ad_conversion_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            channel_id uuid NOT NULL,
            customer_id uuid NOT NULL,
            referral_id uuid NULL,
            cancels_event_id uuid NULL,
            source_kind varchar(16) NOT NULL,
            source_id varchar(64) NOT NULL,
            event_name varchar(24) NOT NULL,
            event_id varchar(128) NOT NULL,
            event_time timestamptz NOT NULL,
            value_minor bigint NULL,
            currency varchar(3) NULL,
            status varchar(12) NOT NULL DEFAULT 'pending',
            attempts integer NOT NULL DEFAULT 0,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            lease_until timestamptz NULL,
            sent_at timestamptz NULL,
            last_error_code varchar(40) NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_ad_conversion_events_event_id UNIQUE (tenant_id, event_id),
            CONSTRAINT uq_ad_conversion_events_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT ck_ad_conversion_events_source_kind
                CHECK (source_kind IN ('reservation', 'woo_order')),
            CONSTRAINT ck_ad_conversion_events_event_name
                CHECK (event_name IN ('Purchase', 'LeadSubmitted', 'OrderCreated', 'OrderCanceled')),
            CONSTRAINT ck_ad_conversion_events_status
                CHECK (status IN ('pending', 'sent', 'failed', 'discarded')),
            CONSTRAINT fk_ad_conversion_events_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_ad_conversion_events_channel
                FOREIGN KEY (tenant_id, channel_id)
                REFERENCES channels (tenant_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_ad_conversion_events_customer
                FOREIGN KEY (tenant_id, customer_id)
                REFERENCES customers (tenant_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_ad_conversion_events_referral
                FOREIGN KEY (tenant_id, referral_id)
                REFERENCES customer_ad_referrals (tenant_id, id) ON DELETE SET NULL (referral_id),
            CONSTRAINT fk_ad_conversion_events_cancels
                FOREIGN KEY (tenant_id, cancels_event_id)
                REFERENCES ad_conversion_events (tenant_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_ad_conversion_events_due ON ad_conversion_events "
        "(tenant_id, status, next_attempt_at) WHERE status = 'pending'"
    )
    op.create_index(
        "ix_ad_conversion_events_sent",
        "ad_conversion_events",
        ["tenant_id", "channel_id", "sent_at"],
    )
    _secure("ad_conversion_events")

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
    for action, *_ in VOCABULARY:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": action}
        )
    for table in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
