"""``model_profiles`` y ``tenant_model_bindings`` (WP-19, plataforma v2).

Dos agujeros que cierra:

1. **El precio no vive en ninguna parte.** WP-18 dejó 716 filas de
   ``usage_records`` con ``cost_usd NULL`` porque no había de dónde sacar
   la tarifa. Con el catálogo en la base, actualizar precios es un UPDATE,
   no un despliegue — que es justo lo que se quiere cuando un proveedor
   cambia tarifas a mitad de mes.
2. **El modelo se elige por variable de entorno GLOBAL**
   (``llm_classify_model`` / ``llm_respond_model`` en el worker, el
   fallback a pelo en ``bootstrap.py``). Ponerle Haiku a un cliente
   sensible a latencia y dejar a otro en Sonnet exige hoy un redeploy que
   afecta a los dos. ``tenant_model_bindings`` lo vuelve una fila.

Decisiones:

- **``model_profiles`` no tiene ``tenant_id`` y por tanto no lleva RLS**:
  es catálogo de plataforma, igual para todos. Lo que sí es por tenant es
  la ELECCIÓN, y esa tabla sí va con RLS ENABLE + FORCE y el patrón
  ``NULLIF`` del repo (el cast pelado del plan convierte un GUC ausente en
  un 500 en vez de en cero filas).
- **``model_id`` es el identificador de LiteLLM tal cual**
  (``anthropic/claude-sonnet-4-6``), no el nombre corto. Es exactamente la
  cadena que el emisor de WP-17 guarda en ``usage_records.model``, así que
  el precio se resuelve con una igualdad y no con heurística de prefijos.
  De ahí el UNIQUE por ``model_id`` solo, además del (provider, model_id)
  del plan: el que factura busca por la cadena sola.
- **``numeric(12,6)`` y no ``(10,4)``**: a 4 decimales no cabe una tarifa
  por minuto de voz (del orden de $0,0004/min) ni una lectura de caché
  barata. Redondear la tarifa antes de multiplicarla por millones de
  tokens es error sistemático, no de redondeo.
- **Precios solo donde son verificables.** Se siembran las tarifas
  vigentes de Anthropic; las filas de OpenAI (fallback de QA y evals,
  transcripción) entran con precio NULL a propósito. NULL = medido y sin
  precio, que es la verdad; inventar una cifra plausible ensuciaría el
  margen sin que nadie lo notara.
- **Backfill incluido.** Con el catálogo puesto, las filas sin precio se
  reprecian aquí mismo. Es idempotente (solo toca ``cost_usd IS NULL``) y
  necesita apagar el FORCE RLS un instante: la migración corre como dueño
  de la tabla y FORCE aplica también al dueño. La ventana vive dentro de
  la transacción de la migración y bajo ACCESS EXCLUSIVE, así que ninguna
  sesión llega a ver la tabla sin forzar.

Revision ID: 0072_model_profiles
Revises: 0071_usage_cost_nullable
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0072_model_profiles"
down_revision: str | Sequence[str] | None = "0071_usage_cost_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Catálogo inicial: los modelos que el código invoca HOY. Precios por
# millón de tokens, tarifas de primera parte de Anthropic. Lectura de
# caché ≈0,1× input; escritura de caché (TTL 5 min) 1,25× input.
#
# ``cache_min_tokens`` no es decorativo: por debajo de ese prefijo el
# proveedor NO cachea y no devuelve error — el ahorro simplemente no
# aparece. Varía por generación (512 / 1024 / 4096), así que un prompt de
# 3k cachea en Sonnet 4.6 y silenciosamente no cachea en Haiku 4.5.
_SEED = [
    {
        "provider": "anthropic",
        "model_id": "anthropic/claude-sonnet-4-6",
        "display_name": "Claude Sonnet 4.6",
        "price_input_per_mtok": "3.000000",
        "price_output_per_mtok": "15.000000",
        "price_cache_read_per_mtok": "0.300000",
        "price_cache_write_per_mtok": "3.750000",
        "price_per_minute": None,
        "max_context": 1_000_000,
        "cache_min_tokens": 1024,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "provider": "anthropic",
        "model_id": "anthropic/claude-haiku-4-5",
        "display_name": "Claude Haiku 4.5",
        "price_input_per_mtok": "1.000000",
        "price_output_per_mtok": "5.000000",
        "price_cache_read_per_mtok": "0.100000",
        "price_cache_write_per_mtok": "1.250000",
        "price_per_minute": None,
        "max_context": 200_000,
        "cache_min_tokens": 4096,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        # Alias con fecha que usan QA Playground y el driver de evals.
        # Mismo modelo y mismas tarifas: sin esta fila, todo el consumo de
        # evaluación quedaría sin precio y el margen de QA sería invisible.
        "provider": "anthropic",
        "model_id": "anthropic/claude-haiku-4-5-20251001",
        "display_name": "Claude Haiku 4.5 (pinned)",
        "price_input_per_mtok": "1.000000",
        "price_output_per_mtok": "5.000000",
        "price_cache_read_per_mtok": "0.100000",
        "price_cache_write_per_mtok": "1.250000",
        "price_per_minute": None,
        "max_context": 200_000,
        "cache_min_tokens": 4096,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        # Fallback de QA y evals. Precio NULL a propósito: no se siembra
        # una tarifa de OpenAI sin fuente. Su consumo se cuenta y queda
        # sin precio hasta que alguien ponga la cifra buena.
        "provider": "openai",
        "model_id": "openai/gpt-4o",
        "display_name": "GPT-4o",
        "price_input_per_mtok": None,
        "price_output_per_mtok": None,
        "price_cache_read_per_mtok": None,
        "price_cache_write_per_mtok": None,
        "price_per_minute": None,
        "max_context": 128_000,
        "cache_min_tokens": None,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "provider": "openai",
        "model_id": "openai/whisper-1",
        "display_name": "Whisper v1 (transcripción)",
        "price_input_per_mtok": None,
        "price_output_per_mtok": None,
        "price_cache_read_per_mtok": None,
        "price_cache_write_per_mtok": None,
        "price_per_minute": None,
        "max_context": None,
        "cache_min_tokens": None,
        "supports_tools": False,
        "supports_vision": False,
    },
]

# Reprecio de lo ya medido. Los medidores de token van por millón; la voz
# va por minuto. Un medidor sin tarifa en el catálogo devuelve NULL y el
# WHERE lo descarta: se queda sin precio, que es lo correcto.
_PRICE_EXPR = """
    CASE u.meter
        WHEN 'llm.input_tokens'  THEN u.quantity / 1000000 * p.price_input_per_mtok
        WHEN 'llm.output_tokens' THEN u.quantity / 1000000 * p.price_output_per_mtok
        WHEN 'llm.cache_read'    THEN u.quantity / 1000000 * p.price_cache_read_per_mtok
        WHEN 'llm.cache_write'   THEN u.quantity / 1000000 * p.price_cache_write_per_mtok
        WHEN 'voice.minutes'     THEN u.quantity * p.price_per_minute
    END
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_profiles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            provider text NOT NULL,
            model_id text NOT NULL,
            display_name text NOT NULL,
            price_input_per_mtok       numeric(12,6),
            price_output_per_mtok      numeric(12,6),
            price_cache_read_per_mtok  numeric(12,6),
            price_cache_write_per_mtok numeric(12,6),
            price_per_minute           numeric(12,6),
            max_context integer,
            cache_min_tokens integer,
            supports_tools  boolean NOT NULL DEFAULT true,
            supports_vision boolean NOT NULL DEFAULT false,
            region text,
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT model_profiles_status_check
                CHECK (status IN ('active', 'deprecated')),
            CONSTRAINT model_profiles_provider_model_key UNIQUE (provider, model_id)
        )
        """
    )
    # El que factura busca por la cadena que guardó el emisor, sin saber el
    # proveedor. Si dos filas compartieran ``model_id``, el precio de un
    # turno dependería del orden de lectura.
    op.execute("CREATE UNIQUE INDEX ux_model_profiles_model_id ON model_profiles (model_id)")

    op.execute(
        """
        CREATE TABLE tenant_model_bindings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            role text NOT NULL,
            model_profile_id uuid NOT NULL REFERENCES model_profiles(id) ON DELETE RESTRICT,
            fallback_chain jsonb NOT NULL DEFAULT '[]'::jsonb,
            max_cost_per_turn_usd numeric(12,6),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT tenant_model_bindings_role_check CHECK (
                role IN (
                    'classify', 'respond', 'grade', 'improve',
                    'voice_llm', 'voice_stt', 'voice_tts'
                )
            ),
            CONSTRAINT tenant_model_bindings_tenant_role_key UNIQUE (tenant_id, role)
        )
        """
    )
    # ON DELETE RESTRICT y no CASCADE: borrar un perfil del catálogo no
    # puede dejar en silencio a un tenant sin modelo para un rol. Si algo
    # lo referencia, que falle y se migre el binding a mano.

    op.execute("ALTER TABLE tenant_model_bindings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_model_bindings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_model_bindings_tenant_isolation ON tenant_model_bindings
        USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)
        """
    )

    # ── seed del catálogo ─────────────────────────────────────────────
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO model_profiles (
                provider, model_id, display_name,
                price_input_per_mtok, price_output_per_mtok,
                price_cache_read_per_mtok, price_cache_write_per_mtok,
                price_per_minute, max_context, cache_min_tokens,
                supports_tools, supports_vision
            ) VALUES (
                :provider, :model_id, :display_name,
                :price_input_per_mtok, :price_output_per_mtok,
                :price_cache_read_per_mtok, :price_cache_write_per_mtok,
                :price_per_minute, :max_context, :cache_min_tokens,
                :supports_tools, :supports_vision
            )
            ON CONFLICT (provider, model_id) DO NOTHING
            """
        ),
        _SEED,
    )

    # ── backfill de lo medido sin precio (WP-18 dejó cost_usd NULL) ────
    # FORCE RLS aplica también al dueño de la tabla, así que el UPDATE no
    # vería ninguna fila sin apagarlo. La ventana está dentro de esta
    # transacción y bajo ACCESS EXCLUSIVE: no hay sesión que llegue a leer
    # la tabla sin forzar.
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
    # El precio se va con el catálogo: dejarlo puesto sería guardar cifras
    # que ya no se pueden auditar contra ninguna tarifa.
    op.execute("ALTER TABLE usage_records NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE usage_records u SET cost_usd = NULL
          FROM model_profiles p
         WHERE u.model = p.model_id
        """
    )
    op.execute("ALTER TABLE usage_records FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS tenant_model_bindings")
    op.execute("DROP TABLE IF EXISTS model_profiles")
