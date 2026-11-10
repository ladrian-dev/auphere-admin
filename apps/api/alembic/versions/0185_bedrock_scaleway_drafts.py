"""Bedrock y Scaleway, en borrador — spec 047, T142 (requisitos 41.5 y 41.6;
research D21 y D44).

Entran en el catálogo los despliegues que el contrato propone como candidatos
(``router-and-catalog.md`` §3), **todos en ``draft``** y con lo que de verdad se
sabe hoy, ni una cosa más:

- **AWS Bedrock con inferencia en la UE**: Claude Haiku 5.5 y Sonnet 5.5 por los
  perfiles de inferencia ``eu.``, desde ``eu-south-2``. Credenciales: el rol IAM
  de la tarea del proxy (ninguna clave). Retención cero:
  ``data_retention_mode:none``.
- **Scaleway, en París**: gpt-oss-120b y gpt-oss-20b (Apache-2.0) y
  whisper-large-v3 (MIT), por su API compatible con OpenAI. Clave en Secrets
  Manager. Retención cero: ``store=false`` (y la de Scaleway por defecto).

Lo que **no** se afirma porque nadie lo ha comprobado (constitución §V y §VIII):

- ``zero_retention`` queda en ``false``: la regla se fuerza en el cable, pero el
  contrato sin retención no está firmado (D44);
- ``contract_dpa`` y ``subprocessor_listed`` en ``false``: Bedrock (inferencia)
  y Scaleway no están dados de alta como subprocesadores;
- las licencias tienen su identificador, sin enlace ni fecha de lectura;
- sin precios ni pesos del medidor: se cargan con su fuente y su fecha desde el
  panel (los del contrato son ilustrativos);
- sin certificación por clase.

Así ``router_catalog.activate_deployment`` los rechaza diciendo todo lo que
falta, que es lo correcto hasta que Luis los dé de alta. Las rutas de Bedrock
(``eu.anthropic.claude-…-5-5``) se comprueban contra ``aws bedrock
list-inference-profiles --region eu-south-2`` antes de certificar.

Revision ID: 0185_bedrock_scaleway_drafts
Revises: 0183_business_hours_services
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0185_bedrock_scaleway_drafts"
down_revision: str | Sequence[str] | None = "0183_business_hours_services"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEDROCK_REGION = "eu-south-2"
SCALEWAY_REGION = "fr-par"

_CLAUDE_CAPS: dict[str, Any] = {
    "tools": True,
    "parallel_tools": True,
    "strict_structured_outputs": True,
    "structured_outputs": True,
    "vision": True,
    "audio": False,
    "cache_mode": "explicit",
    "cache_min_tokens": 4096,
    "context_management": True,
    "reasoning_control": "effort",
    "tool_name_charset": "dotted_ok",
    "context_window": 200000,
    "max_output": 64000,
}

#: Las filas, con la forma de las columnas de ``model_profiles``.
DRAFTS: tuple[dict[str, Any], ...] = (
    {
        "model_id": "bedrock/eu.anthropic.claude-haiku-5-5",
        "display_name": "Claude Haiku 5.5 · Bedrock UE",
        "provider": "aws_bedrock",
        "family": "anthropic-claude",
        "route": "eu.anthropic.claude-haiku-5-5",
        "region": BEDROCK_REGION,
        "retention_how": "data_retention_mode:none",
        "license_id": None,
        "capabilities": {**_CLAUDE_CAPS, "model": "claude-haiku-5-5", "tier": "basic"},
    },
    {
        "model_id": "bedrock/eu.anthropic.claude-sonnet-5-5",
        "display_name": "Claude Sonnet 5.5 · Bedrock UE",
        "provider": "aws_bedrock",
        "family": "anthropic-claude",
        "route": "eu.anthropic.claude-sonnet-5-5",
        "region": BEDROCK_REGION,
        "retention_how": "data_retention_mode:none",
        "license_id": None,
        "capabilities": {**_CLAUDE_CAPS, "model": "claude-sonnet-5-5", "tier": "medium"},
    },
    {
        "model_id": "scaleway/gpt-oss-120b",
        "display_name": "gpt-oss-120b · Scaleway París",
        "provider": "scaleway",
        "family": "openai-gpt-oss",
        "route": "gpt-oss-120b",
        "region": SCALEWAY_REGION,
        "retention_how": "store=false",
        "license_id": "apache-2.0",
        "capabilities": {
            "model": "gpt-oss-120b",
            "tools": True,
            "structured_outputs": True,
            "cache_mode": "none",
            "tool_name_charset": "no_dots",
            "context_window": 128000,
            "tier": "basic",
            "provider_jurisdiction": "eu",
        },
    },
    {
        "model_id": "scaleway/gpt-oss-20b",
        "display_name": "gpt-oss-20b · Scaleway París",
        "provider": "scaleway",
        "family": "openai-gpt-oss",
        "route": "gpt-oss-20b",
        "region": SCALEWAY_REGION,
        "retention_how": "store=false",
        "license_id": "apache-2.0",
        "capabilities": {
            "model": "gpt-oss-20b",
            "tools": True,
            "structured_outputs": True,
            "cache_mode": "none",
            "tool_name_charset": "no_dots",
            "context_window": 128000,
            "tier": "basic",
            "provider_jurisdiction": "eu",
        },
    },
    {
        "model_id": "scaleway/whisper-large-v3",
        "display_name": "whisper-large-v3 · Scaleway París",
        "provider": "scaleway",
        "family": "openai-whisper",
        "route": "whisper-large-v3",
        "region": SCALEWAY_REGION,
        "retention_how": "store=false",
        "license_id": "mit",
        "capabilities": {
            "model": "whisper-large-v3",
            "tools": False,
            "audio": True,
            "cache_mode": "none",
            "tier": "basic",
            "provider_jurisdiction": "eu",
        },
    },
)

MIGRATION = "migration:0185"


def upgrade() -> None:
    conn = op.get_bind()
    for row in DRAFTS:
        caps = row["capabilities"]
        conn.execute(
            sa.text(
                """
                INSERT INTO model_profiles (
                    provider, model_id, display_name, route, region, family, residency,
                    zero_retention, retention_how, license_id, contract_dpa,
                    subprocessor_listed, status, capabilities, quota, supports_tools,
                    supports_vision, max_context, cache_min_tokens
                ) VALUES (
                    :provider, :model_id, :display_name, :route, :region, :family, 'eu',
                    false, :retention_how, :license_id, false,
                    false, 'draft', CAST(:caps AS jsonb), CAST(:quota AS jsonb), :tools,
                    :vision, :context, :cache_min
                )
                ON CONFLICT (model_id) DO NOTHING
                """
            ),
            {
                **{k: v for k, v in row.items() if k != "capabilities"},
                "caps": json.dumps(caps, sort_keys=True),
                "quota": json.dumps({"tpm": None, "rpm": None, "verified_at": None}),
                "tools": bool(caps.get("tools")),
                "vision": bool(caps.get("vision")),
                "context": caps.get("context_window"),
                "cache_min": caps.get("cache_min_tokens"),
            },
        )


def downgrade() -> None:
    # Solo los que siguen en borrador: si alguien los activó, ya no son de la migración.
    op.get_bind().execute(
        sa.text("DELETE FROM model_profiles WHERE model_id = ANY(:ids) AND status = 'draft'"),
        {"ids": [row["model_id"] for row in DRAFTS]},
    )
