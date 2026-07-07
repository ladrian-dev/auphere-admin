"""Admin-only agents skip the LLM classifier.

The dispatcher already gates the sender to a whitelisted admin, and every
message is a command for the tool-using agent — the book/queue/info/escalate
taxonomy never fits (the classifier always returned 'fallback'). So the
classify node routes admin-only agents straight to 'fallback' without the
extra LLM round-trip (~1-2s saved per turn).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexus_worker.runtime import pipeline as pipeline_mod
from nexus_worker.runtime.agent_loader import AgentBundle

pytestmark = [pytest.mark.unit]


def _bundle(policies: dict) -> AgentBundle:
    return AgentBundle(
        tenant_id=uuid.uuid4(),
        version=1,
        version_id=uuid.uuid4(),
        system_prompt="x",
        tools=frozenset({"billing.list_overdue"}),
        policies=policies,
    )


def _state() -> dict:
    return {
        "tenant_id": str(uuid.uuid4()),
        "conversation_id": None,
        "inbound_message_id": None,
        "user_message": "lista de morosos",
    }


@pytest.fixture(autouse=True)
def _no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``_load_recent_history`` hits the DB — stub it out.
    monkeypatch.setattr(pipeline_mod, "_load_recent_history", AsyncMock(return_value=[]))


async def test_admin_only_skips_classifier() -> None:
    loader = MagicMock()
    loader.load = AsyncMock(
        return_value=_bundle(
            {"admin_access": {"admin_only": True, "admin_phones": ["+34610777570"]}}
        )
    )
    llm = MagicMock()
    llm.classify = AsyncMock()

    node = pipeline_mod.make_classify_node(loader, llm)
    result = await node(_state())

    assert result["intent"] == "fallback"
    assert result["route"] == "fallback"
    llm.classify.assert_not_awaited()  # the whole point: no LLM round-trip


async def test_non_admin_agent_still_classifies() -> None:
    loader = MagicMock()
    loader.load = AsyncMock(return_value=_bundle({}))  # normal agent
    llm = MagicMock()
    llm.classify = AsyncMock(return_value="info")

    node = pipeline_mod.make_classify_node(loader, llm)
    result = await node(_state())

    llm.classify.assert_awaited_once()
    assert result["intent"] == "info"
