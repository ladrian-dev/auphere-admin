"""Tarifas de OpenAI en ``model_profiles`` (arrastre de Fase 2, WP-19).

La 0072 sembró ``openai/gpt-4o`` y ``openai/whisper-1`` con precio NULL a
propósito — "no hay fuente verificable" era la razón escrita. Ya la hay:
la tabla oficial de precios de la API (developers.openai.com/api/docs/
pricing, consultada 2026-08-11) da $2,50 / $1,25 / $10,00 por millón para
gpt-4o (entrada / entrada cacheada / salida) y $0,006 por minuto para la
transcripción con Whisper.

Tres decisiones que conviene no re-litigar:

- **``price_cache_write_per_mtok`` de gpt-4o se queda en NULL.** OpenAI
  no cobra por escribir en caché — el descuento es automático y no hay
  concepto facturable de escritura. Poner 0 aquí diría "medido, gratis",
  que es cierto, pero el emisor **nunca produce** ``llm.cache_write`` para
  OpenAI (LiteLLM solo reporta ``cache_creation_input_tokens`` en
  Anthropic), así que la tarifa no se leería jamás. NULL deja el hueco
  visible si algún día ese medidor empieza a llegar.
- **Whisper se valora por minuto, no por token.** Cae en el medidor
  ``voice.minutes`` que ``pricing.py`` ya conocía y que hasta ahora no
  emitía nadie; el emisor entra en el mismo cambio que esta migración.
- **``max_context`` de whisper sigue en NULL** porque no aplica: su
  límite es de 25 MB de archivo, no de contexto. Inventar un número
  comparable con el de un LLM sería peor que no tenerlo.

El reprecio final es el mismo UPDATE idempotente de la 0072 y solo toca
``cost_usd IS NULL``: en un entorno donde no haya consumo de OpenAI no
cambia una fila, y en uno donde lo haya lo valora sin reprocesar nada.

Revision ID: 0076_openai_model_prices
Revises: 0075_budget_policies
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0076_openai_model_prices"
down_revision: str | Sequence[str] | None = "0075_budget_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mismo criterio que la 0072: precio en base, no en código. Esto es la
# carga inicial de dos filas, no un sitio donde consultar la tarifa.
_PRICES = [
    {
        "model_id": "openai/gpt-4o",
        "price_input_per_mtok": "2.500000",
        "price_output_per_mtok": "10.000000",
        "price_cache_read_per_mtok": "1.250000",
        "price_per_minute": None,
    },
    {
        "model_id": "openai/whisper-1",
        "price_input_per_mtok": None,
        "price_output_per_mtok": None,
        "price_cache_read_per_mtok": None,
        "price_per_minute": "0.006000",
    },
]

# Copiado verbatim de la 0072 a propósito: una migración es un hecho
# histórico y no puede cambiar de resultado porque alguien edite un
# módulo compartido seis meses después.
_PRICE_EXPR = """
    CASE u.meter
        WHEN 'llm.input_tokens'  THEN u.quantity / 1000000 * p.price_input_per_mtok
        WHEN 'llm.output_tokens' THEN u.quantity / 1000000 * p.price_output_per_mtok
        WHEN 'llm.cache_read'    THEN u.quantity / 1000000 * p.price_cache_read_per_mtok
        WHEN 'llm.cache_write'   THEN u.quantity / 1000000 * p.price_cache_write_per_mtok
        WHEN 'voice.minutes'     THEN u.quantity * p.price_per_minute
    END
"""

_MODELS = tuple(row["model_id"] for row in _PRICES)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE model_profiles
               SET price_input_per_mtok      = CAST(:price_input_per_mtok      AS numeric),
                   price_output_per_mtok     = CAST(:price_output_per_mtok     AS numeric),
                   price_cache_read_per_mtok = CAST(:price_cache_read_per_mtok AS numeric),
                   price_per_minute          = CAST(:price_per_minute          AS numeric),
                   updated_at = now()
             WHERE model_id = :model_id
            """
        ),
        _PRICES,
    )

    # Reprecio de lo ya medido sin precio. FORCE RLS aplica también al
    # dueño de la tabla, así que sin apagarlo el UPDATE no vería ninguna
    # fila; la ventana vive dentro de esta transacción y bajo ACCESS
    # EXCLUSIVE (misma nota que la 0072).
    op.execute("ALTER TABLE usage_records NO FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        UPDATE usage_records u
           SET cost_usd = ({_PRICE_EXPR})
          FROM model_profiles p
         WHERE u.cost_usd IS NULL
           AND u.model = p.model_id
           AND ({_PRICE_EXPR}) IS NOT NULL
        """
    )
    op.execute("ALTER TABLE usage_records FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Se devuelve el catálogo a "medido, sin precio" y se deshace el
    # reprecio SOLO de los dos modelos que esta migración tocó — poner a
    # NULL el coste de las filas de Anthropic borraría el trabajo de la
    # 0072.
    op.execute("ALTER TABLE usage_records NO FORCE ROW LEVEL SECURITY")
    op.get_bind().execute(
        sa.text(
            """
            UPDATE usage_records
               SET cost_usd = NULL
             WHERE model = ANY(:models)
            """
        ),
        {"models": list(_MODELS)},
    )
    op.execute("ALTER TABLE usage_records FORCE ROW LEVEL SECURITY")
    op.get_bind().execute(
        sa.text(
            """
            UPDATE model_profiles
               SET price_input_per_mtok = NULL,
                   price_output_per_mtok = NULL,
                   price_cache_read_per_mtok = NULL,
                   price_per_minute = NULL,
                   updated_at = now()
             WHERE model_id = ANY(:models)
            """
        ),
        {"models": list(_MODELS)},
    )
