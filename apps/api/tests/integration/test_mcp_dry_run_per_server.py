"""Dry-run smoke test per MCP server (ADR-020 Fase 6, Bloque B).

Goal
----

``apps/api/tests/unit/test_mcp_dry_run.py`` exercises the gate with stub
tools. That proves the registry's logic is right but does NOT prove that
each real server tool — with its real ``side_effects`` declaration —
gets blocked by the gate. A new tool merged tomorrow with
``side_effects = ()`` (e.g. someone forgets the marker on a destructive
operation) would compromise the QA Playground silently.

This file enumerates **every public tool with non-empty side_effects**
across every server in ``apps/mcp/src/nexus_mcp/servers/`` and asserts:

  - dry_run=True intercepts the dispatch BEFORE ``tool.run`` is invoked
  - the audit callback fires once with the tool's name + args
  - the synthetic envelope carries ``status == "skipped:dry_run"``
  - no real HTTP / DB / subprocess call leaks (we monkey-patch ``run``
    to a sentinel that raises if reached — registry blocks first)

For READ-ONLY tools (side_effects=()) the inverse: the gate must let
them through. We patch ``run`` to a deterministic stub and assert the
envelope returns ``status == "ok"``.

Coverage policy: every public-namespace tool with non-empty
side_effects is covered. The single internal-only namespace
(``agendapro_public.*``) is covered because the booking facade
delegates to it via ``dispatch_internal``; the dry_run gate covers
that path too. Composio proxies are tested with one synthesised
instance — the class enforces ``side_effects = ("external_api",)``
unconditionally, so coverage of one proxy is coverage of all.

Catalog snapshot (2026-05-19) — keep this in sync if a tool is added:

   side-effecting public tools                  read-only public tools
  ───────────────────────────────────           ─────────────────────────
   booking.check_availability                   booking.get_appointments
   booking.create_appointment                   client.get_preferences
   booking.modify_appointment                   client.get_history
   booking.cancel_appointment                   commission.calculate_commission
   client.update_preferences                    commission.get_barber_earnings
   escalate.escalate_to_human                   commission.get_daily_report
   notification.send_template                   queue.get_position
   notification.send_text                       queue.get_estimated_wait
   notification.send_image
   notification.send_audio
   notification.send_video
   notification.send_document
   notification.send_location
   notification.send_reaction
   notification.schedule_reminder
   notification.cancel_scheduled
   operator.consult_owner
   queue.join_queue
   queue.check_in
   queue.remove_from_queue
   woocommerce.list_products
   woocommerce.get_product
   woocommerce.list_product_variations
   woocommerce.list_categories
   woocommerce.list_orders
   woocommerce.get_order
   woocommerce.list_customers
   woocommerce.get_customer
   woocommerce.create_order
   woocommerce.update_order_status
   woocommerce.update_order
   woocommerce.add_order_note
   composio_proxy.<dynamic>     (one synthesised)

Internal namespace (``dispatch_internal`` path):
   agendapro_public.check_availability
   agendapro_public.create_appointment
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_mcp.base import ToolBase, make_envelope
from nexus_mcp.registry import MCPRegistry, get_internal_caller_token

from nexus_api.core.tenant_context import tenant_context

# pytest-asyncio runs in ``mode=auto`` so async tests are auto-marked;
# we leave non-async tests in this module unmarked.


# ── helpers ─────────────────────────────────────────────────────────────────


class _Sentinel(Exception):
    """Raised by patched ``run`` to prove the gate did NOT short-circuit
    properly. If a test sees this exception bubble up, the dry_run gate
    has failed: the registry called the real tool body instead of
    intercepting at the side_effects check.
    """


def _block_invoke(tool: ToolBase) -> None:
    """Replace ``tool.invoke`` with a sentinel that raises if reached.

    The dry_run gate must short-circuit BEFORE ``tool.invoke`` runs. Any
    actual call into invoke means the gate failed — and would also mean
    the real tool body would have executed in production. We patch
    invoke (not run) because the gate is upstream of invoke at the
    registry level (``registry.py`` calls ``tool.invoke(args)`` only
    when not blocked). This also avoids Pydantic validation of empty
    args inside ``invoke`` — irrelevant to the gate test.
    """

    async def _raise(_args: dict[str, Any]) -> dict[str, Any]:
        raise _Sentinel(f"tool {tool.name!r} invoke() was reached — dry_run gate FAILED")

    tool.invoke = _raise  # type: ignore[method-assign]


def _stub_invoke(tool: ToolBase) -> None:
    """Replace ``tool.invoke`` with a deterministic stub that mirrors a
    healthy real invocation. Used for read-only tools to confirm the
    gate does NOT block them — we don't care what the real tool would
    return, only that the registry let the call through.
    """

    async def _ok(args: dict[str, Any]) -> dict[str, Any]:
        return make_envelope(
            tool=tool.name,
            tenant_id=uuid.uuid4(),
            args=dict(args),
            result={"stubbed": True},
            status="ok",
        )

    tool.invoke = _ok  # type: ignore[method-assign]


# ── side-effecting tools enumeration ────────────────────────────────────────


def _all_side_effecting_public_tools() -> list[ToolBase]:
    """Materialise one instance of every public tool with non-empty
    side_effects. The list is built from each server's ``*_TOOLS``
    export — the import here is what fails CI if a new tool is added
    without being exported.
    """
    from nexus_mcp.servers.booking import BOOKING_TOOLS
    from nexus_mcp.servers.client import CLIENT_TOOLS
    from nexus_mcp.servers.escalate import ESCALATE_TOOLS
    from nexus_mcp.servers.notification import NOTIFICATION_TOOLS
    from nexus_mcp.servers.operator import OPERATOR_TOOLS
    from nexus_mcp.servers.queue import QUEUE_TOOLS

    classes: list[type[ToolBase]] = []
    classes.extend(BOOKING_TOOLS)
    classes.extend(CLIENT_TOOLS)
    classes.extend(ESCALATE_TOOLS)
    classes.extend(NOTIFICATION_TOOLS)
    classes.extend(OPERATOR_TOOLS)
    classes.extend(QUEUE_TOOLS)

    # Woocommerce gets a try/except — the package is a recent addition
    # and the suite must still surface the rest of the catalog if its
    # imports drift. If it fails to import in CI, the assertion below
    # explicitly fails so it is loud, not silent.
    try:
        from nexus_mcp.servers.woocommerce.tools import build_woocommerce_tools

        woo_instances = build_woocommerce_tools()
    except Exception as exc:  # pragma: no cover - keeps the rest of the suite alive
        pytest.fail(f"failed to import woocommerce tools: {exc!r}")

    instances = [c() for c in classes] + list(woo_instances)
    return [t for t in instances if t.side_effects]


def _all_read_only_public_tools() -> list[ToolBase]:
    from nexus_mcp.servers.booking import BOOKING_TOOLS
    from nexus_mcp.servers.client import CLIENT_TOOLS
    from nexus_mcp.servers.commission import COMMISSION_TOOLS
    from nexus_mcp.servers.queue import QUEUE_TOOLS

    classes: list[type[ToolBase]] = []
    classes.extend(BOOKING_TOOLS)
    classes.extend(CLIENT_TOOLS)
    classes.extend(COMMISSION_TOOLS)
    classes.extend(QUEUE_TOOLS)
    instances = [c() for c in classes]
    return [t for t in instances if not t.side_effects]


def _all_internal_side_effecting_tools() -> list[ToolBase]:
    from nexus_mcp.servers.agendapro_public import build_agendapro_public_tools

    return [t for t in build_agendapro_public_tools() if t.side_effects]


def _composio_proxy() -> ToolBase:
    """Synthesise a composio proxy instance. The class enforces
    ``side_effects = ("external_api",)`` unconditionally, so one proxy
    exercises the gate for the entire dynamic namespace.
    """
    from nexus_mcp.servers.composio_proxy import (
        ComposioProxyTool,
        ComposioToolBlueprint,
    )

    blueprint = ComposioToolBlueprint(
        tool_name="composio.test_tool",
        description="synthesised for dry-run smoke",
        input_schema={"type": "object"},
        toolkit_slug="test",
        connection_id="conn_test",
        user_id="tenant_test",
    )
    return ComposioProxyTool(blueprint)


# ── parametrisation: side-effecting public ──────────────────────────────────


_SIDE_EFFECTING_PUBLIC = [*_all_side_effecting_public_tools(), _composio_proxy()]
_READ_ONLY_PUBLIC = _all_read_only_public_tools()
_SIDE_EFFECTING_INTERNAL = _all_internal_side_effecting_tools()


@pytest.fixture
def audit_collector() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    return []


@pytest.fixture
def audit_callback(audit_collector):
    async def _cb(name: str, args: dict[str, Any], synthetic: dict[str, Any]) -> None:
        audit_collector.append((name, args, synthetic))

    return _cb


# ── side-effecting: gate must intercept and audit ───────────────────────────


@pytest.mark.parametrize(
    "tool",
    _SIDE_EFFECTING_PUBLIC,
    ids=[t.name for t in _SIDE_EFFECTING_PUBLIC],
)
async def test_dry_run_blocks_side_effecting_public_tool(tool, audit_callback, audit_collector):
    """Every side-effecting public tool MUST be intercepted by the gate
    before ``tool.run`` executes. Audit row fires once per attempt.
    """
    _block_invoke(tool)
    reg = MCPRegistry(tools=[tool], dry_run=True, dry_run_audit=audit_callback)
    with tenant_context(uuid.uuid4()):
        envelope = await reg.dispatch(tool.name, {}, whitelist=[tool.name])

    assert envelope["status"] == "skipped:dry_run", (
        f"{tool.name}: gate did not skip — envelope={envelope}"
    )
    assert envelope["result"]["blocked_by"] == "dry_run"
    assert set(envelope["result"]["side_effects_declared"]) == set(tool.side_effects)
    assert len(audit_collector) == 1, (
        f"{tool.name}: audit callback fired {len(audit_collector)} times, expected 1"
    )
    audited_name, audited_args, audited_envelope = audit_collector[0]
    assert audited_name == tool.name
    assert audited_args == {}
    assert audited_envelope["status"] == "skipped:dry_run"


# ── read-only: gate must NOT block ──────────────────────────────────────────


@pytest.mark.parametrize(
    "tool",
    _READ_ONLY_PUBLIC,
    ids=[t.name for t in _READ_ONLY_PUBLIC],
)
async def test_dry_run_lets_read_only_public_tool_pass(tool, audit_collector, audit_callback):
    """Read-only tools must NOT be intercepted. The agent expects real
    data during QA exploration; only mutating / external calls are
    sandboxed. Audit MUST stay empty for these.
    """
    _stub_invoke(tool)
    reg = MCPRegistry(tools=[tool], dry_run=True, dry_run_audit=audit_callback)
    with tenant_context(uuid.uuid4()):
        envelope = await reg.dispatch(tool.name, {}, whitelist=[tool.name])

    assert envelope["status"] == "ok", (
        f"{tool.name}: read-only tool was unexpectedly skipped — {envelope}"
    )
    assert audit_collector == [], (
        f"{tool.name}: audit fired for a read-only tool — {audit_collector}"
    )


# ── internal side-effecting (dispatch_internal path) ────────────────────────


@pytest.mark.parametrize(
    "tool",
    _SIDE_EFFECTING_INTERNAL,
    ids=[t.name for t in _SIDE_EFFECTING_INTERNAL],
)
async def test_dry_run_blocks_internal_side_effecting_tool(tool, audit_callback, audit_collector):
    """The internal namespace (``agendapro_public.*``) reaches dispatch
    via ``dispatch_internal``. The gate applies there too, otherwise
    public ``booking.create_appointment`` would be blocked while its
    subprocess delegate would still run.
    """
    _block_invoke(tool)
    reg = MCPRegistry(internal_tools=[tool], dry_run=True, dry_run_audit=audit_callback)
    with tenant_context(uuid.uuid4()):
        envelope = await reg.dispatch_internal(
            tool.name, {}, caller_token=get_internal_caller_token()
        )

    assert envelope["status"] == "skipped:dry_run"
    assert envelope["result"]["blocked_by"] == "dry_run"
    assert len(audit_collector) == 1
    assert audit_collector[0][0] == tool.name


# ── coverage assertion ──────────────────────────────────────────────────────


def test_coverage_floor_ninety_five_percent():
    """The spec demands >= 95% of side-effecting tools covered. We assert
    that no tool is silently excluded.

    The catalog is built from the ``*_TOOLS`` exports at module import
    time. If a new tool is added to a server but not exported, this
    test stays green by mistake — that's the risk we accept in exchange
    for the simplicity of the enumeration. Adding a new server requires
    extending ``_all_side_effecting_public_tools``; reviewers should
    block the PR if it touches a new namespace.
    """
    covered = {t.name for t in _SIDE_EFFECTING_PUBLIC}
    expected = {
        "booking.check_availability",
        "booking.create_appointment",
        "booking.modify_appointment",
        "booking.cancel_appointment",
        "client.update_preferences",
        "escalate.escalate_to_human",
        "notification.send_template",
        "notification.send_text",
        "notification.send_image",
        "notification.send_audio",
        "notification.send_video",
        "notification.send_document",
        "notification.send_location",
        "notification.send_reaction",
        "notification.schedule_reminder",
        "notification.cancel_scheduled",
        "operator.consult_owner",
        "queue.join_queue",
        "queue.check_in",
        "queue.remove_from_queue",
        "woocommerce.list_products",
        "woocommerce.get_product",
        "woocommerce.list_product_variations",
        "woocommerce.list_categories",
        "woocommerce.list_orders",
        "woocommerce.get_order",
        "woocommerce.list_customers",
        "woocommerce.get_customer",
        "woocommerce.create_order",
        "woocommerce.update_order_status",
        "woocommerce.update_order",
        "woocommerce.add_order_note",
        "composio.test_tool",  # synthetic composio proxy
    }
    missing = expected - covered
    extra = covered - expected
    assert not missing, f"side-effect dry_run coverage gap: {sorted(missing)} not exercised"
    # ``extra`` is non-fatal — it means someone added a tool and updated
    # the loader but forgot to refresh this list. Fail loud so the
    # docstring catalog above stays accurate.
    assert not extra, (
        f"coverage list out of sync — new side-effecting tools detected: {sorted(extra)}. "
        "Update the docstring + ``expected`` set."
    )


__all__ = [
    "make_envelope",  # re-export keeps mypy happy across the suite
]
