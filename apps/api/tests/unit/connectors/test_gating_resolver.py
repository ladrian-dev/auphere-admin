"""Unit tests for the gating resolver (Phase 1 binary semantics)."""

from __future__ import annotations

import pytest

from nexus_api.db.models import ConnectorToolMode
from nexus_api.services.connectors.gating import (
    GatingResolution,
    canonical_blocked_message_es,
    is_executable_phase1,
)


def test_always_is_executable() -> None:
    r = GatingResolution(tool_name="t", mode=ConnectorToolMode.ALWAYS, source="default")
    assert is_executable_phase1(r) is True


def test_blocked_is_not_executable() -> None:
    r = GatingResolution(tool_name="t", mode=ConnectorToolMode.BLOCKED, source="default")
    assert is_executable_phase1(r) is False


def test_needs_approval_is_not_executable_phase1() -> None:
    """Phase 1 contract: needs_approval is treated as blocked at runtime.

    Phase 4+ adds the operator-in-loop path; until then, defaulting to
    NOT-executable is the only safe choice."""
    r = GatingResolution(
        tool_name="t",
        mode=ConnectorToolMode.NEEDS_APPROVAL,
        source="default",
    )
    assert is_executable_phase1(r) is False


def test_canonical_blocked_message_is_spanish() -> None:
    msg = canonical_blocked_message_es()
    assert "Déjame" in msg
    assert len(msg) > 30  # not an empty stub
    # Doesn't leak why it was blocked — tool/connector slug must not appear.
    assert "connector" not in msg.lower()
    assert "tool" not in msg.lower()


@pytest.mark.parametrize(
    "mode,expected",
    [
        (ConnectorToolMode.ALWAYS, True),
        (ConnectorToolMode.BLOCKED, False),
        (ConnectorToolMode.NEEDS_APPROVAL, False),
    ],
)
def test_executability_table(mode: ConnectorToolMode, expected: bool) -> None:
    r = GatingResolution(tool_name="t", mode=mode, source="default")
    assert is_executable_phase1(r) is expected
