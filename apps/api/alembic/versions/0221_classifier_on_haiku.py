"""Spec 047, requisito 69: el clasificador tiene su propio modelo, Claude Haiku 5.5.

Clasificar costaba el 7,5 % del gasto de staging con el modelo de responder, y solo
devuelve una palabra. El modelo entra en el catálogo con sus precios y sus tres pesos: sin
pesos, el turno que lo usa se quedaría sin cobrar (``metering.unweighted_model``).

Se copia la fila de Claude Haiku 4.5, con la misma clasificación de contrato y residencia,
porque es el mismo proveedor por la misma ruta. Los pesos salen de las tarifas como en la
0120: 2,2 sobre un precio de venta de 10 USD por millón de unidades.

Tarifas de https://platform.claude.com/docs/en/about-claude/pricing (2026-10-06): 0,10 de
entrada y 0,50 de salida por millón hasta 100.000 tokens de prompt, 0,50 y 2,50 por encima.
Caché con los multiplicadores de siempre: lectura 0,1 y escritura 1,25.

Revision ID: 0221_classifier_on_haiku
Revises: 0220_tests_on_the_clients_bag
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0221_classifier_on_haiku"
down_revision: str | Sequence[str] | None = "0220_tests_on_the_clients_bag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODEL = "anthropic/claude-haiku-5-5"
SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO model_profiles (
            provider, model_id, display_name,
            price_input_per_mtok, price_output_per_mtok,
            price_cache_read_per_mtok, price_cache_write_per_mtok,
            max_context, cache_min_tokens, supports_tools, supports_vision, status,
            quota_weight, quota_weight_input, quota_weight_cache_read, quota_weight_output,
            route, family, residency, zero_retention, contract_dpa, subprocessor_listed,
            capabilities, quota
        )
        SELECT
            provider, '{MODEL}', 'Claude Haiku 5.5',
            0.100000, 0.500000, 0.010000, 0.125000,
            1000000, cache_min_tokens, supports_tools, supports_vision, 'active',
            0.046, 0.022000, 0.002200, 0.110000,
            '{MODEL}', family, residency, zero_retention, contract_dpa, subprocessor_listed,
            capabilities, quota
        FROM model_profiles
        WHERE model_id = 'anthropic/claude-haiku-4-5'
        ON CONFLICT (model_id) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO model_prices (
            deployment_id, valid_from, input, cache_read, cache_write, output,
            surcharge, source_url, currency, unit
        )
        SELECT
            id, CURRENT_DATE, 0.100000, 0.010000, 0.125000, 0.500000,
            '{{"above_tokens": 100000, "multiplier": 5, "applies_to": "whole_request"}}'::jsonb,
            '{SOURCE}', 'USD', 'per_million_tokens'
        FROM model_profiles
        WHERE model_id = '{MODEL}'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM model_profiles WHERE model_id = '{MODEL}'")
