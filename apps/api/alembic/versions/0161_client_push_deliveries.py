"""client_push_deliveries — un aviso a un teléfono (spec 031, data-model §0161).

La crea el worker al repartir un evento, con los destinatarios calculados **en
ese momento**: cuentan las revocaciones y los interruptores de ese instante
(R7.2, R11.2). Un evento, un aviso por teléfono. Sin contenido.

Revision ID: 0161_client_push_deliveries
Revises: 0160_client_push_events
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0161_client_push_deliveries"
down_revision: str | Sequence[str] | None = "0160_client_push_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"
_SKIP = (
    "'module_missing', 'no_longer_true', 'no_push_token', 'kind_disabled', "
    "'phone_revoked', 'token_owned_elsewhere'"
)


def upgrade() -> None:
    op.create_table(
        "client_push_deliveries",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("phone_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("skip_reason", sa.String(24), nullable=True),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'skipped')",
            name="ck_client_push_deliveries_status",
        ),
        sa.CheckConstraint(
            f"skip_reason IS NULL OR skip_reason IN ({_SKIP})",
            name="ck_client_push_deliveries_skip_reason",
        ),
        sa.UniqueConstraint(
            "tenant_id", "event_id", "phone_id", name="uq_client_push_deliveries_event_phone"
        ),
    )
    op.execute(
        "ALTER TABLE client_push_deliveries ADD CONSTRAINT fk_client_push_deliveries_event "
        "FOREIGN KEY (tenant_id, event_id) REFERENCES client_push_events (tenant_id, id) "
        "ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE client_push_deliveries ADD CONSTRAINT fk_client_push_deliveries_phone "
        "FOREIGN KEY (tenant_id, phone_id) REFERENCES client_phones (tenant_id, id) "
        "ON DELETE CASCADE"
    )
    op.create_index("ix_client_push_deliveries_phone", "client_push_deliveries", ["phone_id"])
    op.execute("GRANT SELECT, INSERT, UPDATE ON client_push_deliveries TO nexus_app")
    op.execute("ALTER TABLE client_push_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE client_push_deliveries FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY client_push_deliveries_tenant_isolation ON client_push_deliveries "
        + _POLICY
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS client_push_deliveries_tenant_isolation ON client_push_deliveries"
    )
    op.execute("REVOKE ALL ON client_push_deliveries FROM nexus_app")
    op.drop_table("client_push_deliveries")
