"""Consola: catálogo cerrado de modelos y binding respond. B es 404 opaco."""

from __future__ import annotations

import pytest

from nexus_api.core.respond_catalog import RESPOND_MODEL_IDS

pytestmark = pytest.mark.asyncio

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"


async def test_list_models_is_the_closed_catalog(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.get("/console/models", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [row["model_id"] for row in body]
    assert ids == list(RESPOND_MODEL_IDS)
    for row in body:
        assert "partner_id" not in row
        assert "tenant_id" not in row
        assert "price_input_per_mtok" not in row


# ── spec 016 · el modelo se elige sabiendo lo que cuesta (R5.1, R5.2) ──────────


async def test_list_models_explains_the_cost_in_credits(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.get("/console/models", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [row["model_id"] for row in body] == list(RESPOND_MODEL_IDS)
    for row in body:
        assert set(row) >= {"model_id", "display_name", "relative_cost", "weights"}
        assert isinstance(row["relative_cost"], int) and row["relative_cost"] >= 1
        assert set(row["weights"]) == {"input", "cache_read", "output"}
        assert row["display_name"]
    # El más económico es x1; el resto, su salida relativa a ese, redondeada.
    assert min(row["relative_cost"] for row in body) == 1
    cheapest = min(body, key=lambda r: r["weights"]["output"])
    for row in body:
        assert row["relative_cost"] == max(
            1, round(row["weights"]["output"] / cheapest["weights"]["output"])
        )


async def test_relative_costs_are_rounded_to_the_cheapest() -> None:
    from nexus_api.api.console.models import relative_costs
    from nexus_api.api.console.schemas_models import ModelWeightsOut

    w = lambda out: ModelWeightsOut(input=1, cache_read=0.1, output=out)  # noqa: E731
    assert relative_costs({"a": w(5), "b": w(20), "c": w(11)}) == {"a": 1, "b": 4, "c": 2}
    assert relative_costs({"a": w(0), "b": w(3)}) == {"a": 1, "b": 1}
    assert relative_costs({}) == {}


async def test_each_model_says_its_provider_and_line(client, console_world) -> None:
    """Spec 065 (T023; requisito 1.5): proveedor y gama, para la línea «para qué sirve»."""
    a = console_world["a"]
    resp = await client.get("/console/models", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    lines = {m["model_id"]: (m["provider"], m["line"]) for m in resp.json()}
    assert lines["openai/gpt-5.6-sol"] == ("openai", "max")
    assert lines["openai/gpt-5.6-terra"] == ("openai", "balanced")
    assert lines["openai/gpt-5.6-luna"] == ("openai", "economy")


# Spec 065 (requisito 12.4): el modelo por cliente se retiró. Lo que fijaban estas pruebas
# lo fijan ahora tests/integration/models/test_agent_model_console.py (por agente) y
# test_client_model_retired.py (la retirada).
