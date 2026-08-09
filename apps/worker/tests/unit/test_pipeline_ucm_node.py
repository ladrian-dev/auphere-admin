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
        # No channel_type in state → the formatter falls back to whatsapp.
        assert diff["channel"] == "whatsapp"

    async def test_enabled_degrades_for_state_channel_type(self) -> None:
        """The shadow diff degrades for the channel the turn runs on.

        QA Playground turns carry ``channel_type="web"``; the formatter
        must honour it instead of always assuming WhatsApp.
        """
        node = make_ucm_formatter_node(enabled=True)
        out = await node(
            {
                "response": "Hola",
                "inbound_message_id": "msg-web",
                "tenant_id": "tnt_a",
                "channel_type": "web",
            }  # type: ignore[arg-type]
        )
        assert out["ucm_shadow_diff"]["channel"] == "web"

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
        with pytest.raises(Exception):  # noqa: B017 — contract test, see comment below
            # Until we wire a graceful skip we want the test to document
            # the current contract: empty response is a programming error
            # surfaced loudly during shadow runs.
            await node({"response": ""})  # type: ignore[arg-type]


# ── WP-13: checkpoint shrink ──────────────────────────────────────────────────


def test_checkpoint_shrink_clears_history_and_clamps_tool_dumps():
    from nexus_worker.runtime.state import (
        MAX_STATE_FIELD_BYTES,
        checkpoint_shrink_update,
    )

    huge = "x" * (MAX_STATE_FIELD_BYTES + 10_000)
    state = {
        "history": [{"role": "user", "content": "hola"}] * 50,
        "tool_calls": [
            {"tool": "catalog.list", "status": "ok", "result": huge},
            {"tool": "booking.create", "status": "ok", "result": "ok"},
        ],
    }
    update = checkpoint_shrink_update(state)  # type: ignore[arg-type]

    assert update["history"] == []
    clamped = update["tool_calls"][0]["result"]
    assert len(clamped.encode()) < MAX_STATE_FIELD_BYTES + 200
    assert "[truncated" in clamped
    # Small fields untouched.
    assert update["tool_calls"][1]["result"] == "ok"


def test_checkpoint_shrink_without_tool_calls():
    from nexus_worker.runtime.state import checkpoint_shrink_update

    assert checkpoint_shrink_update({"history": [{"a": 1}]}) == {"history": []}  # type: ignore[arg-type]
