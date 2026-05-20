"""Unit tests for ``MCPRegistry`` dry_run mode (ADR-020 Phase 3).

These tests live in ``apps/api/tests/`` because they exercise the
integration point between ``apps/mcp`` and the QA Playground audit
callback. The registry itself has no dependency on the API package, so
the same tests could move to ``apps/mcp/tests/`` if that suite grows;
keeping them here gives us cross-package coverage in one CI run.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_mcp.base import InputModel, OutputModel, ToolBase
from nexus_mcp.registry import MCPRegistry, get_internal_caller_token

from nexus_api.core.tenant_context import tenant_context

pytestmark = pytest.mark.asyncio


# ── stub tools ───────────────────────────────────────────────────────────────


class _ReadIn(InputModel):
    pass


class _ReadOut(OutputModel):
    value: int = 42


class ReadOnlyTool(ToolBase):
    name = "demo.read"
    description = "read-only"
    input_model = _ReadIn
    output_model = _ReadOut
    side_effects = ()

    async def run(self, payload: _ReadIn) -> _ReadOut:
        return _ReadOut()


class _WriteIn(InputModel):
    pass


class _WriteOut(OutputModel):
    written: bool = True


class WritingTool(ToolBase):
    name = "demo.write"
    description = "mutates state"
    input_model = _WriteIn
    output_model = _WriteOut
    side_effects = ("mutates_db", "external_api")

    async def run(self, payload: _WriteIn) -> _WriteOut:  # pragma: no cover
        raise AssertionError("dry_run must not invoke this")


class InternalWritingTool(ToolBase):
    name = "demo.internal_write"
    description = "internal subprocess delegate that mutates state"
    input_model = _WriteIn
    output_model = _WriteOut
    side_effects = ("mutates_db",)

    async def run(self, payload: _WriteIn) -> _WriteOut:  # pragma: no cover
        raise AssertionError("dry_run must not invoke this")


# ── tests ────────────────────────────────────────────────────────────────────


async def test_dry_run_default_is_false():
    reg = MCPRegistry(tools=[WritingTool()])
    assert reg.dry_run is False


async def test_dry_run_blocks_side_effect_tool_and_runs_callback():
    audit_calls: list[tuple[str, dict, dict]] = []

    async def audit(name, args, synthetic):
        audit_calls.append((name, args, synthetic))

    reg = MCPRegistry(tools=[WritingTool()], dry_run=True, dry_run_audit=audit)
    with tenant_context(uuid.uuid4()):
        envelope = await reg.dispatch("demo.write", {}, whitelist=["demo.write"])
    assert envelope["status"] == "skipped:dry_run"
    assert envelope["result"]["blocked_by"] == "dry_run"
    assert envelope["result"]["side_effects_declared"] == [
        "mutates_db",
        "external_api",
    ]
    assert len(audit_calls) == 1
    name, args, synthetic = audit_calls[0]
    assert name == "demo.write"
    assert args == {}
    assert synthetic["status"] == "skipped:dry_run"


async def test_dry_run_lets_read_only_tools_pass():
    reg = MCPRegistry(
        tools=[ReadOnlyTool(), WritingTool()],
        dry_run=True,
    )
    with tenant_context(uuid.uuid4()):
        r = await reg.dispatch("demo.read", {}, whitelist=["demo.read"])
    assert r["status"] == "ok"
    assert r["result"]["value"] == 42


async def test_prod_registry_invokes_side_effect_tool():
    """Confirm the gate is opt-in: an old-style call without dry_run
    still runs the side-effect tool as before. Guards against accidental
    behaviour drift in already-deployed code paths.
    """

    # Replace WritingTool with one that completes so we can observe a
    # real invocation in prod mode.
    class _Ok(ToolBase):
        name = "demo.write"
        description = "fake write"
        input_model = _WriteIn
        output_model = _WriteOut
        side_effects = ("mutates_db",)

        async def run(self, payload: _WriteIn) -> _WriteOut:
            return _WriteOut(written=True)

    reg = MCPRegistry(tools=[_Ok()])
    with tenant_context(uuid.uuid4()):
        r = await reg.dispatch("demo.write", {}, whitelist=["demo.write"])
    assert r["status"] == "ok"
    assert r["result"]["written"] is True


async def test_dry_run_audit_failure_does_not_break_conversation():
    """If the audit callback raises, the dispatch must still return the
    synthetic envelope — the gate (no real call) must hold even when
    persistence is broken.
    """

    async def bad_audit(name, args, synthetic):
        raise RuntimeError("audit table is down")

    reg = MCPRegistry(tools=[WritingTool()], dry_run=True, dry_run_audit=bad_audit)
    with tenant_context(uuid.uuid4()):
        envelope = await reg.dispatch("demo.write", {}, whitelist=["demo.write"])
    assert envelope["status"] == "skipped:dry_run"


async def test_dry_run_gates_internal_dispatch_too():
    """The dispatch_internal path (used by subprocess delegates like
    agendapro) MUST also be gated — otherwise the public booking tool
    would be blocked but its delegate would still hit the provider.
    """
    audit_calls: list[str] = []

    async def audit(name, args, synthetic):
        audit_calls.append(name)

    reg = MCPRegistry(
        internal_tools=[InternalWritingTool()],
        dry_run=True,
        dry_run_audit=audit,
    )
    with tenant_context(uuid.uuid4()):
        envelope = await reg.dispatch_internal(
            "demo.internal_write",
            {},
            caller_token=get_internal_caller_token(),
        )
    assert envelope["status"] == "skipped:dry_run"
    assert audit_calls == ["demo.internal_write"]
