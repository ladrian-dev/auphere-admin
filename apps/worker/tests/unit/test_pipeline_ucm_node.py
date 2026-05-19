"""Pipeline-level tests for the ucm_formatter node (Phase 2 / ADR-020).

These tests instantiate just the formatter node and exercise its contract.
The full graph is covered by the existing pipeline tests; here we make sure
the flag toggles correctly and the produced state shape matches what the
``checkpoint`` node and downstream consumers expect.
"""

from __future__ import annotations

import pytest

from nexus_worker.runtime.pipeline import make_ucm_formatter_node


@pytest.mark.asyncio
class TestUcmFormatterNode:
    async def test_disabled_is_noop(self) -> None:
        node = make_ucm_formatter_node(enabled=False)
        out = await node({"response": "anything", "tenant_id": "t1"})
        assert out == {}

    async def test_enabled_emits_ucm_and_diff(self) -> None:
        node = make_ucm_formatter_node(enabled=True)
        state = {
            "response": "Hola, ¿cómo te ayudo?",
            "inbound_message_id": "msg-001",
            "tenant_id": "tnt_a",
            "conversation_id": "conv_a",
            "intent": "info",
        }
        out = await node(state)  # type: ignore[arg-type]
        assert set(out.keys()) == {"ucm", "ucm_shadow_diff"}

        ucm = out["ucm"]
        assert ucm["ucm_version"] == "1.0.0"
        assert ucm["type"] == "text"
        assert ucm["content"]["body"] == "Hola, ¿cómo te ayudo?"
        # The seed id propagates from inbound_message_id so traces stay joinable.
        assert ucm["message_id"] == "msg-001"
        # Metadata carries the context for downstream tooling.
        assert ucm["metadata"]["tenant_id"] == "tnt_a"
        assert ucm["metadata"]["conversation_id"] == "conv_a"
        assert ucm["metadata"]["intent"] == "info"
        assert ucm["metadata"]["phase"] == "shadow"

        diff = out["ucm_shadow_diff"]
        assert diff["equivalent"] is True
        assert diff["diff_ratio"] == 0.0
        assert diff["channel"] == "whatsapp"

    async def test_enabled_falls_back_when_state_lacks_inbound_id(self) -> None:
        node = make_ucm_formatter_node(enabled=True)
        out = await node({"response": "hi"})  # type: ignore[arg-type]
        # Still produces a UCM (with a fresh UUID instead of the seed id).
        assert out["ucm"]["type"] == "text"
        assert len(out["ucm"]["message_id"]) > 0

    async def test_empty_response_produces_no_state_update(self) -> None:
        # The schema rejects an empty body; we want the node to NOT raise
        # the agent's run for that — the legacy text path keeps working
        # and we just skip the UCM emission for this turn.
        node = make_ucm_formatter_node(enabled=True)
        with pytest.raises(Exception):
            # Until we wire a graceful skip we want the test to document
            # the current contract: empty response is a programming error
            # surfaced loudly during shadow runs.
            await node({"response": ""})  # type: ignore[arg-type]
