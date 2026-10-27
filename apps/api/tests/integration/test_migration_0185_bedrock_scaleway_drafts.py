"""Spec 047, T142 — la 0185 siembra Bedrock y Scaleway **en borrador**
(requisitos 41.2, 41.5 y 41.6; research D21 y D44).

Nadie los ha dado de alta como subprocesadores, ni ha firmado su retención
cero, ni ha leído sus licencias, ni ha cargado sus precios: la migración no lo
afirma. Así, la puerta de activación los rechaza diciendo todo lo que falta, el
hop no los ejecuta, la consola no los ofrece y el router no los elige.

La ida y vuelta de la migración la cubre ``test_migration_reversibility.py``.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.llm import RETENTION_WIRE
from nexus_worker.runtime.model_resolver import RouteContext, chain_for

from nexus_api.core import respond_catalog
from nexus_api.db.base import get_sessionmaker
from nexus_api.services.router_catalog import (
    ActivationRejected,
    activate_deployment,
    activation_problems,
    litellm_params_for,
    load_snapshot,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0185_bedrock_scaleway_drafts.py"
)


def _drafts() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("_mig_0185", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [dict(r) for r in module.DRAFTS]


KEYS = [r["model_id"] for r in _drafts()]


async def _snapshot() -> Any:
    async with get_sessionmaker()() as session:
        return await load_snapshot(session)


async def test_the_drafts_are_in_the_catalog_and_claim_nothing_unverified() -> None:
    snapshot = await _snapshot()
    rows = {k: snapshot.deployments[k] for k in KEYS}
    assert {d.provider for d in rows.values()} == {"aws_bedrock", "scaleway"}
    for key, deployment in rows.items():
        assert deployment.status == "draft", key
        assert deployment.residency == "eu", key
        assert not deployment.zero_retention, f"{key}: la retención cero no está firmada (D44)"
        assert deployment.retention_how in RETENTION_WIRE, f"{key}: regla que el cable no sabe"
        assert not deployment.contract_dpa and not deployment.subprocessor_listed, key
        assert deployment.prices == () and not deployment.weighted, key
        assert snapshot.certified_tasks(key) == frozenset(), key
    assert rows["bedrock/eu.anthropic.claude-haiku-5-5"].region == "eu-south-2"
    assert rows["bedrock/eu.anthropic.claude-haiku-5-5"].capabilities.tier == "basic"
    assert rows["bedrock/eu.anthropic.claude-sonnet-5-5"].capabilities.tier == "medium"
    assert rows["scaleway/whisper-large-v3"].capabilities.audio
    assert all(
        rows[k].capabilities.provider_jurisdiction == "eu" for k in KEYS if k.startswith("scaleway")
    ), "Scaleway es un proveedor europeo: entra en la restricción soberana el día que se active"


async def test_the_gate_rejects_them_saying_everything_that_is_missing() -> None:
    snapshot = await _snapshot()
    for key in KEYS:
        deployment = snapshot.deployments[key]
        missing = set(activation_problems(deployment, class_certified_tasks=()))
        assert {
            "no_zero_retention",
            "subprocessor_not_listed",
            "unweighted",
            "no_class_certification",
        } <= missing, key
        if deployment.license_id is not None:
            assert "license_unread" in missing, f"{key}: licencia sin leer entera"
    async with get_sessionmaker()() as session, session.begin():
        with pytest.raises(ActivationRejected) as err:
            await activate_deployment(session, "bedrock/eu.anthropic.claude-haiku-5-5")
    assert "subprocessor_not_listed" in err.value.missing


async def test_nothing_runs_offers_or_routes_them() -> None:
    async with get_sessionmaker()() as session:
        await respond_catalog.refresh_from_db(session)
    assert not set(KEYS) & set(respond_catalog.HOP_MODEL_IDS), "un borrador no se ejecuta"
    assert not set(KEYS) & set(respond_catalog.RESPOND_MODEL_ID_SET), "ni se ofrece"
    snapshot = await _snapshot()
    profile = snapshot.profiles["auto"]
    for task in ("classify", "answer", "tool_turn", "transcribe"):
        decision = chain_for(
            task,
            profile,
            RouteContext(
                tenant_id=uuid.uuid4(),
                catalog=snapshot,
                eu_only=True,
                agent_certified=frozenset(KEYS),
            ),
        )
        reasons = {r.deployment: r.reason for r in decision.rejected}
        assert all(reasons.get(k) == "status" for k in KEYS), (task, reasons)
        assert not set(decision.models) & set(KEYS)
    respond_catalog.reset()


async def test_the_proxy_registration_needs_no_key_for_bedrock() -> None:
    """Lo que se registra en el proxy LiteLLM (``/model/new``) para cada uno:
    Bedrock por el rol IAM de la tarea, Scaleway con su clave de Secrets Manager
    leída del entorno del proxy."""
    snapshot = await _snapshot()
    haiku = litellm_params_for(snapshot.deployments["bedrock/eu.anthropic.claude-haiku-5-5"])
    assert haiku == {
        "model": "bedrock/eu.anthropic.claude-haiku-5-5",
        "aws_region_name": "eu-south-2",
    }
    oss = litellm_params_for(snapshot.deployments["scaleway/gpt-oss-120b"])
    assert oss == {
        "model": "openai/gpt-oss-120b",
        "api_base": "os.environ/SCALEWAY_API_BASE",
        "api_key": "os.environ/SCALEWAY_API_KEY",
    }
    async with get_sessionmaker()() as session:
        provider = await session.scalar(
            sa.text(
                "SELECT provider FROM model_profiles WHERE model_id = 'anthropic/claude-haiku-4-5'"
            )
        )
    assert provider == "anthropic"
    with pytest.raises(ValueError, match="anthropic"):
        litellm_params_for(snapshot.deployments["anthropic/claude-haiku-4-5"])
