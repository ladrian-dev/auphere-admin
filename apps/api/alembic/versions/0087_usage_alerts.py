"""CP-24 · tope mensual y alertas de consumo por partner (carril D).

Tres columnas en ``partners``:

- ``usage_cap_messages_month`` (integer, NULL) — tope de **mensajes de
  canal** (``usage_records.meter = 'channel.message'``,
  ``source = 'channel'``) por mes natural UTC, sumando todos los clientes
  del partner. NULL = sin tope: la consola no enseña porcentaje ni avisa.
  Es la unidad que el partner ve en su página de consumo (C9: unidades,
  nunca coste). **En v1 el tope solo AVISA — no corta el servicio**: al
  cruzar el 80 % y el 100 % se crea una ``console_notifications``
  (``usage.threshold`` / ``usage.cap_reached``, dedupe por partner+umbral+
  mes) y se envía un correo a ``usage_alert_recipients``. Cortar mensajes
  a los clientes finales de un partner por un tope comercial es una
  decisión de contrato, no de plataforma, y queda para la fase de Stripe.
- ``usage_alert_recipients`` (jsonb, lista de correos, ``[]``) — a quién
  se escribe. Vacía = solo notificación in-app.
- ``usage_alerts_enabled`` (boolean, true) — interruptor del partner.

La evaluación vive en ``services/usage_alerts.py`` y la disparan un cron
del worker cada 15 min y, en caliente, ``GET /console/home``.

Revision ID: 0087_usage_alerts
Revises: 0086_console_notifications
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0087_usage_alerts"
down_revision: str | Sequence[str] | None = "0086_console_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE partners
            ADD COLUMN usage_cap_messages_month integer NULL,
            ADD COLUMN usage_alert_recipients jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN usage_alerts_enabled boolean NOT NULL DEFAULT true
        """
    )
    op.execute(
        "ALTER TABLE partners ADD CONSTRAINT ck_partners_usage_cap_messages_month "
        "CHECK (usage_cap_messages_month IS NULL OR usage_cap_messages_month >= 0)"
    )
    op.execute(
        "ALTER TABLE partners ADD CONSTRAINT ck_partners_usage_alert_recipients_array "
        "CHECK (jsonb_typeof(usage_alert_recipients) = 'array')"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_usage_alert_recipients_array"
    )
    op.execute(
        "ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_usage_cap_messages_month"
    )
    op.execute(
        "ALTER TABLE partners "
        "DROP COLUMN IF EXISTS usage_alerts_enabled, "
        "DROP COLUMN IF EXISTS usage_alert_recipients, "
        "DROP COLUMN IF EXISTS usage_cap_messages_month"
    )
