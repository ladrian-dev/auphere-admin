"""Tres filas del catálogo cerrado Sol / Terra / Luna (Fase 2 consola).

Ids LiteLLM verbatim. Sin alias ``gpt-5.6``. Tarifas NULL hasta que se
carguen; no se toca C3 ni se reprecia consumo.

Revision ID: 0095_gpt56_respond_catalog
Revises: 0094_partner_wallet
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0095_gpt56_respond_catalog"
down_revision: str | Sequence[str] | None = "0094_partner_wallet"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED = [
    {
        "provider": "openai",
        "model_id": "openai/gpt-5.6-sol",
        "display_name": "Sol",
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "provider": "openai",
        "model_id": "openai/gpt-5.6-terra",
        "display_name": "Terra",
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "provider": "openai",
        "model_id": "openai/gpt-5.6-luna",
        "display_name": "Luna",
        "supports_tools": True,
        "supports_vision": True,
    },
]

_IDS = tuple(row["model_id"] for row in _SEED)


def upgrade() -> None:
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
                NULL, NULL, NULL, NULL, NULL,
                NULL, NULL,
                :supports_tools, :supports_vision
            )
            ON CONFLICT (provider, model_id) DO NOTHING
            """
        ),
        _SEED,
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM model_profiles WHERE model_id = ANY(:ids)"),
        {"ids": list(_IDS)},
    )
