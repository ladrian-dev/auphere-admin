"""Spec 065, T029 (requisito 2.9): el copiloto propone el modelo de un agente, no de un cliente.

La propuesta pide ``client_ref`` y ``agent_id``; valida contra lo que ese agente puede
elegir (``GET …/agents/{id}/model``: la oferta del partner, sin la lista escrita a mano «uno
de los tres»), y se aplica por el mismo camino que la pantalla (``PUT …/agents/{id}/model``)
tras la confirmación de la persona. Los demás agentes del cliente no cambian.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.companion.tools.catalog import TOOLS_BY_NAME
from nexus_api.companion.tools.proposals import ProposalBuilder, ProposalRefused
from tests.unit.test_companion_actions import reader

pytestmark = pytest.mark.asyncio

AGENT = "6f1d6c34-1b8c-4c49-a3a1-7f3f6a7b0c11"
VIEW: dict[str, Any] = {
    "agent_id": AGENT,
    "choice": {"model_id": "openai/gpt-5.6-terra", "display_name": "Terra", "set_by": "operator"},
    "effective": {
        "model_id": "openai/gpt-5.6-terra",
        "display_name": "Terra",
        "source": "agent_operator",
        "outside_offer": None,
        "estimate": {"amount_micros": 6269, "currency": "USD", "basis": "agent_7d"},
    },
    "options": [
        {
            "model_id": "anthropic/claude-haiku-5-5",
            "display_name": "Claude Haiku 5.5",
            "provider": "anthropic",
            "line": "economy",
            "estimate": {"amount_micros": 341, "currency": "USD", "basis": "agent_7d"},
        },
        {
            "model_id": "openai/gpt-5.6-luna",
            "display_name": "Luna",
            "provider": "openai",
            "line": "economy",
            "estimate": {"amount_micros": 655, "currency": "USD", "basis": "agent_7d"},
        },
        {
            "model_id": "openai/gpt-5.6-terra",
            "display_name": "Terra",
            "provider": "openai",
            "line": "balanced",
            "estimate": {"amount_micros": 6269, "currency": "USD", "basis": "agent_7d"},
        },
    ],
    "notice": None,
    "can_change": True,
}
ROUTES = {f"/console/clients/jemma/agents/{AGENT}/model": VIEW}


async def test_the_proposal_is_for_one_agent_and_applies_by_its_route() -> None:
    proposal = await ProposalBuilder(read=reader(ROUTES)).build(
        "model",
        {"client_ref": "jemma", "agent_id": AGENT, "model_id": "openai/gpt-5.6-luna"},
    )
    assert proposal.kind == "model"
    assert proposal.apply_method == "PUT"
    assert proposal.apply_path == f"/console/clients/jemma/agents/{AGENT}/model"
    assert proposal.apply_body == {"model_id": "openai/gpt-5.6-luna"}
    assert proposal.expectations == {"model_id": "openai/gpt-5.6-luna"}
    assert "Luna" in proposal.title
    texts = " ".join(str(line) for line in proposal.diff)
    assert "Terra" in texts and "Luna" in texts


async def test_a_model_the_agent_cannot_choose_is_refused_with_the_real_options() -> None:
    """Claude Haiku sí, aunque no sea «uno de los tres»; Sol, si no está en su oferta, no."""
    build = ProposalBuilder(read=reader(ROUTES))
    ok = await build.build(
        "model",
        {"client_ref": "jemma", "agent_id": AGENT, "model_id": "anthropic/claude-haiku-5-5"},
    )
    assert ok.apply_body == {"model_id": "anthropic/claude-haiku-5-5"}
    with pytest.raises(ProposalRefused) as refused:
        await build.build(
            "model",
            {"client_ref": "jemma", "agent_id": AGENT, "model_id": "openai/gpt-5.6-sol"},
        )
    assert refused.value.error.code == "unknown_model"


async def test_proposing_the_model_it_already_has_changes_nothing() -> None:
    with pytest.raises(ProposalRefused) as refused:
        await ProposalBuilder(read=reader(ROUTES)).build(
            "model",
            {"client_ref": "jemma", "agent_id": AGENT, "model_id": "openai/gpt-5.6-terra"},
        )
    assert refused.value.error.code == "no_change"


async def test_an_agent_of_another_client_is_the_same_404() -> None:
    with pytest.raises(ProposalRefused) as refused:
        await ProposalBuilder(read=reader(ROUTES)).build(
            "model",
            {"client_ref": "ajeno", "agent_id": AGENT, "model_id": "openai/gpt-5.6-luna"},
        )
    assert refused.value.error.code in {"unknown_client", "unknown_agent"}


async def test_the_tool_asks_for_the_agent() -> None:
    spec = TOOLS_BY_NAME["console.propose_model"]
    names = {p.name for p in spec.params}
    assert {"client_ref", "agent_id", "model_id"} <= names
    assert "/agents/{agent_id}/model" in spec.path
    assert "uno de los tres" not in spec.description.lower()
