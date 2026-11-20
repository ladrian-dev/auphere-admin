"""Spec 065 (T045; requisitos 5.5, 5.8, 13.1): el carril de escritura en caché y el modelo por
defecto de Auphere.

- ``model_profiles.quota_weight_cache_write``: el peso del cuarto carril, sacado de la tarifa
  de escritura con el multiplicador de venta vigente (``platform_settings.sale_multiplier``),
  como los otros tres (0120). Cero en los modelos por tokens sin tarifa de escritura; nulo
  en los que no se cobran por tokens (Whisper, por minutos).
- GPT-5.6 cobra la escritura en caché a 1,25 veces la entrada (documentación de OpenAI) y se
  repercute (Luis, 2026-11-19; research.md §D14): sus tres filas ganan la tarifa y una fila
  de precio nueva que **copia las demás tarifas en vigor**, porque el precio vigente es la
  fila de ``valid_from`` más reciente y una fila solo con escritura dejaría la entrada y la
  salida en blanco.
- ``platform_settings.agent_respond_default``: el modelo de los agentes sin elección. Arranca
  en Sol, el modelo con el que respondían ayer (CE-005).

Revision ID: 0239_cache_write_lane_default
Revises: 0238_respond_offer_claude_55
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0239_cache_write_lane_default"
down_revision: str | Sequence[str] | None = "0238_respond_offer_claude_55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPENAI_CACHE_SOURCE = "https://developers.openai.com/api/docs/guides/prompt-caching"

#: GPT-5.6: tarifa de escritura = 1,25 veces la de entrada.
GPT56_WRITE: dict[str, str] = {
    "openai/gpt-5.6-sol": "5.000000",
    "openai/gpt-5.6-terra": "2.500000",
    "openai/gpt-5.6-luna": "0.250000",
}

DEFAULT_KEY = "agent_respond_default"
DEFAULT_MODEL = "openai/gpt-5.6-sol"

_MULTIPLIER = (
    "COALESCE((SELECT (value #>> '{}')::numeric FROM platform_settings "
    "WHERE key = 'sale_multiplier'), 2.2)"
)


def upgrade() -> None:
    op.add_column(
        "model_profiles",
        sa.Column("quota_weight_cache_write", sa.Numeric(12, 6), nullable=True),
    )
    bind = op.get_bind()
    for model_id, write in GPT56_WRITE.items():
        bind.execute(
            sa.text(
                "UPDATE model_profiles SET price_cache_write_per_mtok = CAST(:w AS numeric) "
                "WHERE model_id = :m"
            ),
            {"w": write, "m": model_id},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO model_prices (
                    deployment_id, valid_from, unit, input, cache_read, cache_write, output,
                    audio_minute, image, surcharge, source_url, currency
                )
                SELECT p.deployment_id, CURRENT_DATE, p.unit, p.input, p.cache_read,
                       CAST(:w AS numeric), p.output, p.audio_minute, p.image, p.surcharge,
                       :source, p.currency
                  FROM model_prices p
                  JOIN model_profiles m ON m.id = p.deployment_id
                 WHERE m.model_id = :m
                   AND p.valid_from <= CURRENT_DATE
                 ORDER BY p.valid_from DESC
                 LIMIT 1
                ON CONFLICT (deployment_id, valid_from)
                DO UPDATE SET cache_write = EXCLUDED.cache_write
                """
            ),
            {"w": write, "m": model_id, "source": OPENAI_CACHE_SOURCE},
        )
    op.execute(
        f"""
        UPDATE model_profiles
           SET quota_weight_cache_write = CASE
                 WHEN price_cache_write_per_mtok IS NOT NULL
                   THEN round(price_cache_write_per_mtok * {_MULTIPLIER} / 10, 6)
                 WHEN quota_weight_input IS NOT NULL THEN 0
                 ELSE NULL
               END
        """
    )
    bind.execute(
        sa.text(
            "INSERT INTO platform_settings (key, value, updated_by) "
            "VALUES (:k, to_jsonb(CAST(:v AS text)), 'migration:0239') "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"k": DEFAULT_KEY, "v": DEFAULT_MODEL},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM platform_settings WHERE key = :k"), {"k": DEFAULT_KEY})
    bind.execute(
        sa.text(
            "DELETE FROM model_prices WHERE source_url = :source AND deployment_id IN "
            "(SELECT id FROM model_profiles WHERE model_id = ANY(:ids))"
        ),
        {"source": OPENAI_CACHE_SOURCE, "ids": list(GPT56_WRITE)},
    )
    bind.execute(
        sa.text(
            "UPDATE model_profiles SET price_cache_write_per_mtok = NULL WHERE model_id = ANY(:ids)"
        ),
        {"ids": list(GPT56_WRITE)},
    )
    op.drop_column("model_profiles", "quota_weight_cache_write")
