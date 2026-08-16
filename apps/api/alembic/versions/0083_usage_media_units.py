"""CP-23 · unidades de multimedia medidas Y valoradas (carril D, PLAN-CONSOLE-V1).

Hechos antes de esta migración: un mensaje con adjunto contaba como un
``channel.message`` más los ``llm.*`` del multimodal; **no había medidor
de media**. El partner no podía ver cuántas imágenes, notas de voz o
documentos procesaron sus clientes, y Auphere no podía ponerles precio.

Qué cambia:

1. **Precios por medidor sin modelo** — tabla ``meter_prices``. El catálogo
   ``model_profiles`` (0072) valora por *modelo* (tokens/minuto), y un
   adjunto no tiene modelo: es una unidad. Aquí vive el precio unitario de
   los medidores ``media.*`` (y de cualquier medidor futuro por unidad). El
   consumidor de metering (``apps/worker/.../metering/pricing.py``) lo lee
   con el mismo TTL que ``model_profiles`` y valora ``cost_usd`` al
   insertar. Es precio en base de datos y no en código por el mismo motivo
   que 0072: cambiar una tarifa no debe exigir un despliegue.

   Los precios sembrados son **PROVISIONALES** (columna ``note`` lo dice):
   el plan pide "medidas y valoradas" y una fila con ``cost_usd`` NULL
   sale de todos los paneles de margen sin avisar. Se ajustan con un
   UPDATE. ``media.audio_seconds`` va a 0: el coste real de transcribir
   ya se valora en ``voice.minutes`` (0076); esa fila existe para poder
   facturar/limitar por segundos, no para sumar coste dos veces.

2. **``usage_records.source`` legible por ``nexus_reporting``.** La 0078
   dio al rol de solo lectura permisos por columna sobre ``usage_records``
   ANTES de que existiera ``source`` (0079). La consola de partners lee el
   consumo del mes de todos los clientes de un partner en una sola consulta
   bajo ese rol (``tenant_id = ANY(...)`` en vez de N transacciones RLS) y
   necesita separar el tráfico de canal (facturable) de las pruebas QA.
   Solo la columna; ninguna otra ampliación del rol.

Revision ID: 0083_usage_media_units
Revises: 0082_qa_budget_cap
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0083_usage_media_units"
down_revision: str | Sequence[str] | None = "0082_qa_budget_cap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPORTING_ROLE = "nexus_reporting"

# (meter, price_per_unit USD, note). PROVISIONAL — see module docstring.
_SEED: tuple[tuple[str, str, str], ...] = (
    (
        "media.image",
        "0.00200000",
        "provisional 2026-08: S3 + fetch overhead; vision tokens billed as llm.*",
    ),
    ("media.sticker", "0.00100000", "provisional 2026-08: same path as image, smaller payload"),
    (
        "media.audio",
        "0.00200000",
        "provisional 2026-08: S3 + fetch; transcription billed as voice.minutes",
    ),
    (
        "media.audio_seconds",
        "0.00000000",
        "0 on purpose: cost already in voice.minutes; unit kept for caps/billing",
    ),
    ("media.document", "0.00300000", "provisional 2026-08: S3 + PDF text extraction"),
    (
        "media.video",
        "0.00500000",
        "provisional 2026-08: S3 (up to 16 MB) + audio-track transcription",
    ),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE meter_prices (
            meter           text PRIMARY KEY,
            price_per_unit  numeric(14, 8) NOT NULL CHECK (price_per_unit >= 0),
            currency        char(3) NOT NULL DEFAULT 'USD',
            note            text NULL,
            updated_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE meter_prices IS 'Unit price (our cost) of meters that have no model — media.* (0083). Platform catalog, no RLS.'"
    )
    for meter, price, note in _SEED:
        op.execute(
            "INSERT INTO meter_prices (meter, price_per_unit, note) "
            f"VALUES ('{meter}', {price}, '{note}') ON CONFLICT (meter) DO NOTHING"
        )
    op.execute(f"GRANT SELECT (source) ON usage_records TO {REPORTING_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT (source) ON usage_records FROM {REPORTING_ROLE}")
    op.execute("DROP TABLE IF EXISTS meter_prices")
