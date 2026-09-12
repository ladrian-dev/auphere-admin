"""Tarifas de los tres modelos que vende el producto (spec 004, R1).

Cierra el ítem **C1** de ``PLAN-PENDIENTE-CORTE-2026-09-08``: Sol, Terra y
Luna entraron en la 0095 con las cinco columnas de tarifa a NULL y siguen así.
No es un detalle de catálogo: ``config.py`` sirve
``llm_companion_model = "openai/gpt-5.6-sol"``, así que **cada turno de
Companion y cada turno de teammate desde entonces está medido y sin valorar** —
``_turn_cost_usd`` devuelve ``None`` y ``usage_records.cost_usd`` se queda
vacío. El margen de teammates no es malo: es invisible.

**Fuente de las tarifas: la tabla oficial de precios de la API de OpenAI
(developers.openai.com/api/docs/pricing), consultada el 2026-09-11.** En USD por
millón de tokens:

============================  =======  ==============  =======
modelo                        entrada  entrada caché   salida
============================  =======  ==============  =======
``openai/gpt-5.6-sol``           4,00            0,40    20,00
``openai/gpt-5.6-terra``         2,00            0,20    12,00
``openai/gpt-5.6-luna``          0,20            0,02     1,20
============================  =======  ==============  =======

Se deja escrito de dónde salen y cuándo se consultaron por lo mismo que lo dejó
la 0076: revisar una tarifa dentro de un año no puede obligar a investigar de
cero.

Tres decisiones que conviene no re-litigar:

- **``price_cache_write_per_mtok`` se queda en NULL para los tres.** Es el mismo
  razonamiento que la 0076 escribió para ``gpt-4o``: OpenAI no cobra por
  escribir en caché, y además el emisor **nunca produce** ``llm.cache_write``
  para OpenAI (LiteLLM solo reporta ``cache_creation_input_tokens`` en
  Anthropic). Un 0 diría «medido, gratis», que es una afirmación que nadie ha
  verificado; NULL deja el hueco visible si algún día ese medidor empieza a
  llegar.
- **La caché de estos tres descuenta exactamente 0,1x** (0,40/4,00 · 0,20/2,00 ·
  0,02/0,20). Coincide con el peso que ``quota_tokens()`` ya aplica a
  ``cache_read`` desde C3. Es una coincidencia afortunada y conviene escribirla
  antes de que alguien cambie una de las dos creyendo que son independientes.
- **``max_context`` se queda como está.** Es el ítem B6 y no esta migración:
  rellenarlo sin fuente sería el mismo error que esto viene a arreglar.

**El reprecio es el de siempre**, copiado *verbatim* de la 0076 —que a su vez lo
copió de la 0072— y por el motivo que aquélla dejó escrito: una migración es un
hecho histórico y no puede cambiar de resultado porque alguien edite un módulo
compartido seis meses después. Solo toca ``cost_usd IS NULL``, así que en un
entorno sin consumo de estos modelos no cambia una fila, y en uno que lo tenga
lo valora sin reprocesar nada.

``meter_prices`` **no gana filas aquí**, y eso es una decisión, no un olvido:
ver ``metering/pricing_policy.py``. Los medidores ``llm.*`` se valoran contra
``model_profiles`` y darles además un precio unitario los cobraría dos veces;
los demás que faltaban están declarados como no valorados, con su motivo.

Revision ID: 0114_sold_model_prices
Revises: 0113_teammate_changes
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0114_sold_model_prices"
down_revision: str | Sequence[str] | None = "0113_teammate_changes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Carga inicial de tres filas, no un sitio donde consultar la tarifa: el precio
# vive en la base para que cambiarlo sea un UPDATE y no un despliegue (0072).
_PRICES = [
    {
        "model_id": "openai/gpt-5.6-sol",
        "price_input_per_mtok": "4.000000",
        "price_output_per_mtok": "20.000000",
        "price_cache_read_per_mtok": "0.400000",
    },
    {
        "model_id": "openai/gpt-5.6-terra",
        "price_input_per_mtok": "2.000000",
        "price_output_per_mtok": "12.000000",
        "price_cache_read_per_mtok": "0.200000",
    },
    {
        "model_id": "openai/gpt-5.6-luna",
        "price_input_per_mtok": "0.200000",
        "price_output_per_mtok": "1.200000",
        "price_cache_read_per_mtok": "0.020000",
    },
]

# Copiado verbatim de la 0076 a propósito. Ver el docstring.
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

#: El reprecio, como constante del módulo para que la prueba de integración
#: ejecute **este** enunciado y no una copia suya. Editar el SQL de arriba
#: rompe el test, que es exactamente lo que se quiere.
BACKFILL_SQL = f"""
UPDATE usage_records u
   SET cost_usd = ({_PRICE_EXPR})
  FROM model_profiles p
 WHERE u.cost_usd IS NULL
   AND u.model = p.model_id
   AND ({_PRICE_EXPR}) IS NOT NULL
"""


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE model_profiles
               SET price_input_per_mtok      = CAST(:price_input_per_mtok      AS numeric),
                   price_output_per_mtok     = CAST(:price_output_per_mtok     AS numeric),
                   price_cache_read_per_mtok = CAST(:price_cache_read_per_mtok AS numeric),
                   updated_at = now()
             WHERE model_id = :model_id
            """
        ),
        _PRICES,
    )

    # FORCE RLS aplica también al dueño de la tabla, así que sin apagarlo el
    # UPDATE no vería ninguna fila. La ventana vive dentro de esta transacción
    # y bajo ACCESS EXCLUSIVE (misma nota que la 0072 y la 0076).
    op.execute("ALTER TABLE usage_records NO FORCE ROW LEVEL SECURITY")
    op.execute(BACKFILL_SQL)
    op.execute("ALTER TABLE usage_records FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Se devuelve el catálogo a "medido, sin precio" y se deshace el reprecio
    # SOLO de los tres modelos que esta migración tocó: poner a NULL el coste
    # de las filas de Anthropic o de gpt-4o borraría el trabajo de la 0072 y de
    # la 0076.
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
                   updated_at = now()
             WHERE model_id = ANY(:models)
            """
        ),
        {"models": list(_MODELS)},
    )
