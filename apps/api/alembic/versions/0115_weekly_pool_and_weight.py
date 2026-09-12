"""Pool semanal y peso por modelo (spec 004, R2 y R3).

Dos columnas, y las dos existen para que un número se pueda cambiar **sin
desplegar**, que es el mismo criterio con el que la 0072 puso los precios en la
base y no en el código.

**``partners.weekly_pool_tokens``** — el tamaño del consumo incluido que se
repone cada siete días. Se siembra preservando el volumen mensual de hoy
(``companion_monthly_token_cap x 7 / 30.44``): esta spec cambia el **ritmo** de
reposición, no la generosidad del producto. Cambiar las dos cosas a la vez haría
imposible saber cuál causó lo que se observe después.

``companion_monthly_token_cap`` **no se borra aquí**. Crear la sustituta y
eliminar la original en la misma migración deja un ``downgrade()`` incapaz de
devolver los datos, y la regla 3 de PLAN-CONSOLE-V1 pide ``downgrade()`` real
probado contra un dump de producción. Queda marcada como deprecada en el modelo,
y la elimina una migración posterior cuando el despliegue lleve un ciclo con la
columna nueva.

**``model_profiles.quota_weight``** — cuánto pesa un token de cuota de ese
modelo, normalizado al cerebro medio del catálogo cerrado (Terra = 1,000).

``NULL`` significa **«este modelo no se sirve por el carril de cuota de LLM»**,
no «peso 1». Es el mismo idioma que la tabla ya habla con las tarifas: una
ausencia declarada, nunca un cero disfrazado. ``openai/whisper-1`` se queda en
NULL **y sigue funcionando**, porque se mide por minutos y no pasa por
``quota_tokens()``.

Los pesos salen del coste real por token de cuota sobre el turno de referencia
de la evaluación (30 K de prompt con 80 % de acierto de caché y 1,5 K de
salida). Con ellos a tres decimales, **agotar un pool cuesta lo mismo con
cualquier cerebro**: entre 3,5144 $ y 3,5154 $ por millón en los seis modelos
del catálogo, 0,03 % de desviación. Ésa es la propiedad entera de R3.2.

Un detalle que conviene no perder: ``openai/gpt-4o`` pesa **1,724**, casi como
el modelo más caro, y su precio de entrada es la mitad. La diferencia está en la
caché — la cobra a 1,25 $, la mitad de la entrada, en vez de a una décima parte.
El peso mide **coste real por token de cuota**, caché incluida, no reputación de
modelo; un número puesto a ojo habría fallado justo ahí.

Revision ID: 0115_weekly_pool_and_weight
Revises: 0114_sold_model_prices
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0115_weekly_pool_and_weight"
down_revision: str | Sequence[str] | None = "0114_sold_model_prices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Normalizados a ``openai/gpt-5.6-terra`` = 1,000.
_WEIGHTS: list[dict[str, str]] = [
    {"model_id": "openai/gpt-5.6-luna", "quota_weight": "0.100"},
    {"model_id": "anthropic/claude-haiku-4-5", "quota_weight": "0.457"},
    {"model_id": "anthropic/claude-haiku-4-5-20251001", "quota_weight": "0.457"},
    {"model_id": "openai/gpt-5.6-terra", "quota_weight": "1.000"},
    {"model_id": "anthropic/claude-sonnet-4-6", "quota_weight": "1.371"},
    {"model_id": "openai/gpt-4o", "quota_weight": "1.724"},
    {"model_id": "openai/gpt-5.6-sol", "quota_weight": "1.828"},
]


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE partners
          ADD COLUMN IF NOT EXISTS weekly_pool_tokens bigint NOT NULL DEFAULT 115000
        """
    )
    op.execute(
        """
        ALTER TABLE partners
          ADD CONSTRAINT ck_partners_weekly_pool_nonneg
          CHECK (weekly_pool_tokens >= 0)
        """
    )
    # El DEFAULT de la columna no es 0 a propósito: 115 000 es el equivalente
    # semanal del defecto de ``companion_monthly_token_cap`` (500 000 al mes x
    # 7 / 30,44 = 114 980, redondeado a un número legible). Con un default de
    # cero, **todo partner nuevo nacería sin pool** y su Companion no
    # arrancaría — el mismo silencio con el que esta spec acaba en otro sitio.
    #
    # 7 / 30.44 preserva el volumen mensual de los partners EXISTENTES (R2.6).
    # El redondeo es al entero más cercano: a estas magnitudes la diferencia es
    # irrelevante y un FLOOR sistemático recortaría a todos un poco.
    op.execute(
        """
        UPDATE partners
           SET weekly_pool_tokens = GREATEST(
                 0, ROUND(COALESCE(companion_monthly_token_cap, 0) * 7.0 / 30.44)
               )
        """
    )

    op.execute("ALTER TABLE model_profiles ADD COLUMN IF NOT EXISTS quota_weight numeric(6,3)")
    op.execute(
        """
        ALTER TABLE model_profiles
          ADD CONSTRAINT ck_model_profiles_quota_weight_pos
          CHECK (quota_weight IS NULL OR quota_weight > 0)
        """
    )
    op.get_bind().execute(
        sa.text(
            """
            UPDATE model_profiles
               SET quota_weight = CAST(:quota_weight AS numeric),
                   updated_at = now()
             WHERE model_id = :model_id
            """
        ),
        _WEIGHTS,
    )

    # El trigger que siembra el libro al crear un partner (0094) escribía el
    # cap deprecado y el fin de MES. R2.7 exige que el partner nazca con pool y
    # con su vencimiento puestos **en el mismo acto** —sin una ventana en la que
    # exista sin saldo esperando a un proceso de fondo—, así que el trigger pasa
    # al pool semanal anclado a su propia fecha de alta.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION partner_wallets_on_partner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO partner_wallets (
                partner_id, included_remaining, included_expires_at, purchased_remaining
            )
            VALUES (
                NEW.id,
                NEW.weekly_pool_tokens,
                COALESCE(NEW.created_at, timezone('UTC', now())) + interval '7 days',
                0
            )
            ON CONFLICT (partner_id) DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )


def downgrade() -> None:
    # Se devuelve el trigger a su forma de la 0094: mes natural y cap deprecado.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION partner_wallets_on_partner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO partner_wallets (
                partner_id, included_remaining, included_expires_at, purchased_remaining
            )
            VALUES (
                NEW.id,
                NEW.companion_monthly_token_cap,
                (date_trunc('month', timezone('UTC', now())) + interval '1 month')
                    AT TIME ZONE 'UTC',
                0
            )
            ON CONFLICT (partner_id) DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "ALTER TABLE model_profiles DROP CONSTRAINT IF EXISTS ck_model_profiles_quota_weight_pos"
    )
    op.execute("ALTER TABLE model_profiles DROP COLUMN IF EXISTS quota_weight")
    op.execute("ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_weekly_pool_nonneg")
    op.execute("ALTER TABLE partners DROP COLUMN IF EXISTS weekly_pool_tokens")
