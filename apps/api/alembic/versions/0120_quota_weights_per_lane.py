"""Tres pesos de cuota, uno por carril (spec 007, R1 y R2).

**El defecto que esto corrige.** Un solo peso por modelo, aplicado al total de
la llamada, no puede representar tres precios distintos. Los proveedores cobran
la salida entre 5x y 6x la entrada, y la lectura de caché a una décima parte en
Anthropic y en la familia GPT-5.6 pero a **la mitad** en ``gpt-4o``. Con un
factor único, el multiplicador que cobramos sobre el coste sale distinto en cada
carril — y en el carril caro sale **por debajo de uno**:

============================  =======  =====  ======
modelo                        entrada  caché  salida
============================  =======  =====  ======
``openai/gpt-5.6-sol``          4,57x  4,57x  0,91x
``anthropic/claude-sonnet-4-6`` 4,57x  4,57x  0,91x
``openai/gpt-4o``               6,90x  1,38x  1,72x
``openai/gpt-5.6-terra``        5,00x  5,00x  0,83x
``anthropic/claude-haiku-4-5``  4,57x  4,57x  0,91x
``openai/gpt-5.6-luna``         5,00x  5,00x  0,83x
============================  =======  =====  ======

Los seis incumplen la regla: cinco venden la salida por debajo de coste y el
sexto se queda en 1,38x en caché, bajo el suelo de 1,50x. Y duele justo donde
más: la bolsa incluida paga el trabajo de teammates, que es **pesado en salida**.

**El peso se deriva de la tarifa del propio carril**, con un multiplicador único
de 2,2x sobre un precio de venta de 10 USD por millón de unidades — margen del
54,5 % por construcción, en los dieciocho carriles.

Tres decisiones que conviene no re-litigar:

- **Se siembra leyendo la tarifa de la PROPIA FILA, no de una lista.** La 0115
  llevaba los siete pesos escritos a mano y por eso quedó desincronizada del
  catálogo: una lista pasa en verde el día que alguien añade un modelo y no la
  toca. Aquí la fuente es la columna de al lado.
- **``NUMERIC(12,6)``, la escala de las tarifas, no la ``NUMERIC(6,3)`` de
  ``quota_weight``.** El peso *es* una tarifa reescalada. Con tres decimales el
  carril de caché de ``openai/gpt-5.6-luna`` vale 0,0044 y se guardaría como
  0,004 — 2,00x en vez de 2,20x. Sigue sobre el suelo, pero el siguiente modelo
  más barato puede no estarlo y nadie se enteraría.
- **``quota_weight`` NO se borra aquí.** Mismo argumento que la 0115 escribió
  para ``companion_monthly_token_cap``: crear la sustituta y eliminar la
  original en la misma migración deja un ``downgrade()`` incapaz de devolver los
  datos. La elimina una migración posterior, cuando el despliegue lleve un ciclo
  con las columnas nuevas.

**Y el peso sigue siendo dato, no cálculo derivado en runtime.** El comentario de
``model_profile.py`` ya lo dejó escrito y sigue vigente: derivarlo en cada
llamada haría que el contador del partner se moviera solo el día que un proveedor
ajeno cambie un precio, y un contador que se mueve solo no se puede explicar en
soporte. Lo que sí se hace con esa derivación es **comprobarla** (R6).

**Nada se revalora.** No hay reprecio, no hay backfill y ningún saldo se toca:
la unidad de cuota no cambia de definición, cambia su tasa de conversión desde
los tokens nativos. Un millón de unidades sigue siendo un millón de unidades.

Revision ID: 0120_quota_weights_per_lane
Revises: 0119_signup_partner_link
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0120_quota_weights_per_lane"
down_revision: str | Sequence[str] | None = "0119_signup_partner_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Multiplicador único sobre el coste de proveedor (spec 007, /speckit-clarify
#: del 2026-09-14). Enmienda a la baja el 65 % que el ADR-037 dio por decidido:
#: llevarlo a 2,857x subiría un 28,4 % la factura del consumo de clientes
#: finales, y hay tres clientes reales con tráfico.
_TARGET = "2.2"

#: USD por millón de unidades de cuota (``billing/pricing.py``). Escrito aquí
#: como literal y no importado a propósito: una migración es un hecho histórico
#: y no puede cambiar de resultado porque alguien edite un módulo compartido
#: seis meses después. Es el mismo criterio con el que la 0114 copió su reprecio
#: verbatim de la 0076.
_SELL = "10"

_LANES = (
    ("quota_weight_input", "price_input_per_mtok"),
    ("quota_weight_cache_read", "price_cache_read_per_mtok"),
    ("quota_weight_output", "price_output_per_mtok"),
)


def upgrade() -> None:
    for weight_col, _price_col in _LANES:
        op.execute(
            f"ALTER TABLE model_profiles ADD COLUMN IF NOT EXISTS {weight_col} numeric(12,6)"
        )

    # La siembra va ANTES de los CHECK: con el de «los tres o ninguno» puesto
    # primero, el UPDATE tendría que escribir las tres columnas en un solo
    # enunciado o violar la restricción a mitad de camino.
    #
    # Sólo se siembran los modelos que HOY se sirven por el carril de cuota
    # (``quota_weight IS NOT NULL``) y que tienen las tres tarifas. Un modelo al
    # que le falte una tarifa se queda sin pesos y por tanto deja de servirse:
    # es la verdad —no se puede derivar un peso de un precio que no existe— y es
    # ruidosa a propósito, porque la alternativa es cobrarlo mal en silencio.
    sets = ", ".join(f"{w} = ROUND(({_TARGET} * {p}) / {_SELL}, 6)" for w, p in _LANES)
    where = " AND ".join(f"{p} IS NOT NULL" for _w, p in _LANES)
    op.execute(
        f"""
        UPDATE model_profiles
           SET {sets},
               updated_at = now()
         WHERE quota_weight IS NOT NULL
           AND {where}
        """
    )

    for weight_col, _price_col in _LANES:
        op.execute(
            f"""
            ALTER TABLE model_profiles
              ADD CONSTRAINT ck_model_profiles_{weight_col}_pos
              CHECK ({weight_col} IS NULL OR {weight_col} > 0)
            """
        )

    # Los tres o ninguno. Un modelo con dos pesos y uno nulo no es «medio
    # servible»: es un error de configuración, y el carril que falta es
    # justamente el que nadie mira hasta que cuadra una factura.
    op.execute(
        """
        ALTER TABLE model_profiles
          ADD CONSTRAINT ck_model_profiles_quota_weight_lanes_all_or_none
          CHECK (
            (quota_weight_input IS NULL
             AND quota_weight_cache_read IS NULL
             AND quota_weight_output IS NULL)
            OR
            (quota_weight_input IS NOT NULL
             AND quota_weight_cache_read IS NOT NULL
             AND quota_weight_output IS NOT NULL)
          )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE model_profiles "
        "DROP CONSTRAINT IF EXISTS ck_model_profiles_quota_weight_lanes_all_or_none"
    )
    for weight_col, _price_col in _LANES:
        op.execute(
            f"ALTER TABLE model_profiles DROP CONSTRAINT IF EXISTS "
            f"ck_model_profiles_{weight_col}_pos"
        )
        op.execute(f"ALTER TABLE model_profiles DROP COLUMN IF EXISTS {weight_col}")
    # ``quota_weight`` sigue donde estaba con sus valores intactos: esta
    # migración nunca lo tocó, y por eso la bajada no puede perder nada.
