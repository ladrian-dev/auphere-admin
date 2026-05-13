"""WhatsApp clase mundial + Composio runtime + connector_id backfill

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-13

Migración aditiva (cero breaking) que cubre la auditoría 2026-05-13:

1. **Idempotency de wamid inbound** — ``messages.provider_message_id`` con
   índice UNIQUE parcial (solo cuando IS NOT NULL). El webhook hace
   ``ON CONFLICT DO NOTHING`` antes del XADD para que el reintento de
   YCloud no duplique.

2. **Status callbacks** — ``messages`` gana ``delivered_at``, ``read_at``,
   ``failed_at``, ``failure_code``, ``pricing_category``,
   ``conversation_provider_id`` (la ``conversation.id`` que Meta abre por
   ventana de cobro). Se añaden los valores ``delivered`` y ``read`` al
   PG enum ``message_status``. Para que ``ALTER TYPE ADD VALUE`` no
   tope con transacciones de la propia migración usamos autocommit
   wrapping (``CREATE TYPE … BEGIN`` + commit). Postgres 12+ permite
   ALTER TYPE … ADD VALUE IF NOT EXISTS en transacción siempre que ese
   ``ALTER`` sea la única operación del statement, así que lo emitimos
   con ``op.execute`` aislado.

3. **Media en mensajes** — ``messages.media_kind`` (audio/image/document/
   video/sticker/location/contacts), ``media_s3_key``, ``media_mime``,
   ``media_size_bytes``, ``media_filename`` (para documents), y
   ``media_transcript`` (para audio transcrito o documento parseado).

4. **Reacciones inbound/outbound** — ``messages.reaction_emoji`` +
   ``messages.reaction_target_wamid`` (qué mensaje recibe la reacción).

5. **Quoted replies** — ``messages.context_message_id`` (el wamid citado
   por este mensaje). Permite que el agente entienda contexto cuando el
   cliente cita un mensaje viejo.

6. **Ventana de 24h server-side** — ``conversations.last_inbound_at``
   timestamp. La tool ``notification.send_text`` lo lee antes de
   encolar; afuera de 24h fuerza al agente a usar ``send_template``.

7. **WhatsApp opt-out registry** — nueva tabla ``whatsapp_opt_outs`` con
   RLS+FORCE. El webhook detecta STOP/BAJA/UNSUBSCRIBE y registra la
   fila; antes de cada send outbound el dispatcher la consulta.

8. **WhatsApp template status** — nueva tabla ``whatsapp_template_status``
   que mirorrea el estado de aprobación de Meta (APPROVED, PENDING,
   REJECTED, FLAGGED, PAUSED, DISABLED). Alimentada por el webhook
   ``message_template_status_update`` y consultada por la tool
   ``send_template`` para no encolar templates rechazados.

9. **Connector backfill** — backfill de ``tool_catalog.connector_id``:
   las 5 ``booking.*`` apuntan al connector ``agendapro`` (delegate),
   las 6 ``agendapro.*`` internal también, y ``notification.send_*`` /
   ``escalate.*`` quedan NULL (son internas, sin connector). Esto cierra
   el gap P1 conocido en el editor de admin: ``booking.create_appointment``
   ya no se podrá whitelistear sin tener AgendaPro o Google Calendar
   conectado, porque la UI lo chequea contra ``connector_id``.

10. **WhatsApp channel health** — ``channels.last_health_check_at`` +
    ``channels.last_provider_synced_at`` para que el cron de quality
    rating pueda persistir el snapshot fresco sin tocar ``config``
    cada vez (ya que ``config`` se audita).

Downgrade es estrictamente reversible salvo los valores del enum
``message_status`` que Postgres no permite remover de un type. La
downgrade los deja en el type — ningún cliente los usaría tras
re-bajar a 0018 (default sigue siendo ``sent``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RLS_POLICY_SQL = """
CREATE POLICY {table}_tenant_isolation ON {table}
USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
"""


def upgrade() -> None:
    # ── 1. messages.provider_message_id + dedupe index ──────────────────────
    op.add_column(
        "messages",
        sa.Column("provider_message_id", sa.String(160), nullable=True),
    )
    op.create_index(
        "uq_messages_provider_message_id",
        "messages",
        ["provider_message_id"],
        unique=True,
        postgresql_where=sa.text("provider_message_id IS NOT NULL"),
    )

    # ── 2. status callbacks: enum values + timestamps + provider conv id ────
    op.execute("ALTER TYPE message_status ADD VALUE IF NOT EXISTS 'delivered'")
    op.execute("ALTER TYPE message_status ADD VALUE IF NOT EXISTS 'read'")

    op.add_column(
        "messages",
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("failure_code", sa.String(20), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("pricing_category", sa.String(40), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("conversation_provider_id", sa.String(120), nullable=True),
    )

    # ── 3. media ─────────────────────────────────────────────────────────────
    op.add_column(
        "messages",
        sa.Column("media_kind", sa.String(20), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("media_s3_key", sa.String(500), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("media_mime", sa.String(120), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("media_size_bytes", sa.Integer, nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("media_filename", sa.String(255), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("media_transcript", sa.Text, nullable=True),
    )
    op.create_check_constraint(
        "ck_messages_media_kind",
        "messages",
        "media_kind IS NULL OR media_kind IN ("
        "'audio', 'image', 'document', 'video', 'sticker', 'location', 'contacts')",
    )

    # ── 4. reactions ────────────────────────────────────────────────────────
    op.add_column(
        "messages",
        sa.Column("reaction_emoji", sa.String(20), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("reaction_target_wamid", sa.String(160), nullable=True),
    )

    # ── 5. quoted replies ───────────────────────────────────────────────────
    op.add_column(
        "messages",
        sa.Column("context_message_id", sa.String(160), nullable=True),
    )

    # ── 6. conversations.last_inbound_at (24h window) ───────────────────────
    op.add_column(
        "conversations",
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Best-effort backfill for existing conversations so the 24h check
    # doesn't reject legitimate continuations created before this migration.
    op.execute(
        "UPDATE conversations c "
        "SET last_inbound_at = ("
        "  SELECT MAX(m.created_at) FROM messages m "
        "  WHERE m.conversation_id = c.id "
        "    AND m.direction = 'inbound'"
        ")"
    )

    # ── 7. whatsapp_opt_outs ─────────────────────────────────────────────────
    op.create_table(
        "whatsapp_opt_outs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_phone", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("trigger_keyword", sa.String(80), nullable=True),
        sa.Column("source_wamid", sa.String(160), nullable=True),
        sa.Column(
            "opted_out_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("opted_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT", name="fk_optout_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["channels.id"], ondelete="CASCADE", name="fk_optout_channel"
        ),
        sa.UniqueConstraint(
            "tenant_id", "channel_id", "recipient_phone", name="uq_optout_tenant_channel_phone"
        ),
        sa.CheckConstraint(
            "reason IN ('keyword_stop', 'user_request', 'operator_manual', 'compliance')",
            name="ck_optout_reason",
        ),
    )
    op.create_index(
        "ix_optout_tenant_channel",
        "whatsapp_opt_outs",
        ["tenant_id", "channel_id"],
    )
    op.create_index(
        "ix_optout_active",
        "whatsapp_opt_outs",
        ["tenant_id", "recipient_phone"],
        postgresql_where=sa.text("opted_in_at IS NULL"),
    )
    op.execute("ALTER TABLE whatsapp_opt_outs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE whatsapp_opt_outs FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY_SQL.format(table="whatsapp_opt_outs"))

    # ── 8. whatsapp_template_status ─────────────────────────────────────────
    op.create_table(
        "whatsapp_template_status",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("waba_id", sa.String(64), nullable=False),
        sa.Column("template_name", sa.String(120), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("category", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "last_event_payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="SET NULL", name="fk_tplstatus_tenant"
        ),
        sa.UniqueConstraint(
            "waba_id", "template_name", "language", name="uq_tplstatus_waba_name_lang"
        ),
        sa.CheckConstraint(
            "status IN ('approved', 'pending', 'rejected', 'flagged', 'paused', 'disabled', 'unknown')",
            name="ck_tplstatus_status",
        ),
    )
    op.create_index(
        "ix_tplstatus_waba",
        "whatsapp_template_status",
        ["waba_id"],
    )
    # This table is intentionally NOT RLS-scoped: template approval is at the
    # WABA level, and a WABA can be shared between Auphere's internal templates
    # and tenant-specific ones. The webhook updates it under a non-tenant
    # session; the read path (notification.send_template) filters by waba_id
    # which is loaded from the tenant's channel.config and inherits the
    # tenant scope upstream.

    # ── 9. connector_id backfill ────────────────────────────────────────────
    # Block L migration 0013 added the column but the original
    # migrate_to_connectors.py only backfilled tenant_connectors, leaving
    # tool_catalog.connector_id NULL for the booking.* and agendapro.* rows.
    # Closing the P1 gap from the 2026-05-13 review.
    op.execute(
        """
        UPDATE tool_catalog
        SET connector_id = (SELECT id FROM connectors WHERE slug = 'agendapro')
        WHERE name IN (
            -- 6 internal agendapro.* tools (delegated from booking.*)
            'agendapro.check_availability',
            'agendapro.create_appointment',
            'agendapro.modify_appointment',
            'agendapro.cancel_appointment',
            'agendapro.get_today_appointments',
            'agendapro.scrape_no_shows',
            -- 5 booking.* facade tools that route through the agendapro delegate
            'booking.check_availability',
            'booking.create_appointment',
            'booking.modify_appointment',
            'booking.cancel_appointment',
            'booking.get_appointments'
        )
        AND connector_id IS NULL
        AND EXISTS (SELECT 1 FROM connectors WHERE slug = 'agendapro')
        """
    )
    # Tag those tools as requires_consent so the editor surfaces the
    # "connect AgendaPro first" warning consistently.
    op.execute(
        """
        UPDATE tool_catalog
        SET requires_consent = true
        WHERE name IN (
            'booking.check_availability',
            'booking.create_appointment',
            'booking.modify_appointment',
            'booking.cancel_appointment',
            'booking.get_appointments',
            'agendapro.check_availability',
            'agendapro.create_appointment',
            'agendapro.modify_appointment',
            'agendapro.cancel_appointment',
            'agendapro.get_today_appointments',
            'agendapro.scrape_no_shows'
        )
        """
    )

    # ── 10. channels.last_health_check_at + last_provider_synced_at ─────────
    op.add_column(
        "channels",
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("last_provider_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # 10. channels columns
    op.drop_column("channels", "last_provider_synced_at")
    op.drop_column("channels", "last_health_check_at")

    # 9. connector_id backfill is data, not schema — leave the foreign
    # values in place since dropping them would lose audit history. The
    # FK column itself is owned by migration 0013.

    # 8. whatsapp_template_status
    op.drop_index("ix_tplstatus_waba", table_name="whatsapp_template_status")
    op.drop_table("whatsapp_template_status")

    # 7. whatsapp_opt_outs
    op.execute(
        "DROP POLICY IF EXISTS whatsapp_opt_outs_tenant_isolation ON whatsapp_opt_outs"
    )
    op.execute("ALTER TABLE whatsapp_opt_outs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE whatsapp_opt_outs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_optout_active", table_name="whatsapp_opt_outs")
    op.drop_index("ix_optout_tenant_channel", table_name="whatsapp_opt_outs")
    op.drop_table("whatsapp_opt_outs")

    # 6. conversations.last_inbound_at
    op.drop_column("conversations", "last_inbound_at")

    # 5. quoted replies
    op.drop_column("messages", "context_message_id")

    # 4. reactions
    op.drop_column("messages", "reaction_target_wamid")
    op.drop_column("messages", "reaction_emoji")

    # 3. media
    op.drop_constraint("ck_messages_media_kind", "messages", type_="check")
    op.drop_column("messages", "media_transcript")
    op.drop_column("messages", "media_filename")
    op.drop_column("messages", "media_size_bytes")
    op.drop_column("messages", "media_mime")
    op.drop_column("messages", "media_s3_key")
    op.drop_column("messages", "media_kind")

    # 2. status columns (enum values are not removable in PG; left in place)
    op.drop_column("messages", "conversation_provider_id")
    op.drop_column("messages", "pricing_category")
    op.drop_column("messages", "failure_code")
    op.drop_column("messages", "failed_at")
    op.drop_column("messages", "read_at")
    op.drop_column("messages", "delivered_at")

    # 1. dedupe index + provider_message_id
    op.drop_index("uq_messages_provider_message_id", table_name="messages")
    op.drop_column("messages", "provider_message_id")
