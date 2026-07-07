"""Garantía 1 + 2 — Anthropic Memory tool cannot cross tenant or customer
boundaries.

Fase B of [[claude-platform-integration]]. The Memory tool stores
arbitrary content the LLM authored on a customer's behalf; without
isolation a single tenant's memory could read another's, or one
customer's preferences could leak into another conversation. Migration
0032 enforces tenant isolation via Postgres RLS; the path validator
enforces customer scoping app-side.

These tests drive ``NexusPostgresMemoryTool`` **directly** — not through
``MCPRegistry``. Built-in Anthropic tools have their own scoping
(per-turn instance carries tenant_id + customer_id) and the RLS layer
is what catches a bypass. Going through the registry would test the
wrong layer.

Each test seeds two tenants A and B (or two customers under the same
tenant) and asserts the worst case: the attacker cannot read the
victim's memory AND cannot tell whether it exists.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_worker.memory import NexusPostgresMemoryTool, PathValidationError
from nexus_worker.memory.path_validator import validate_and_resolve_path
from sqlalchemy import text

from nexus_api.db.models import AgentMemory

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _make_customer(session, tenant_id: uuid.UUID, identifier: str) -> uuid.UUID:
    """Seed a minimal Customer row for tests that need a customer_id in
    scope. The Memory tool itself does not query the customers table —
    it just stores the UUID — but the FK on agent_memories does, so the
    row has to exist."""
    from nexus_api.db.models import Customer

    cust = Customer(
        tenant_id=tenant_id,
        identifier=identifier,
        name=f"Test {identifier}",
    )
    session.add(cust)
    await session.flush()
    return cust.id


async def test_tenant_a_cannot_read_tenant_b_memory(db_session, tenants_ab) -> None:
    """The literal §B.4.1 P0 test.

    Tenant B writes ``/memories/tenant/secret.md`` with sensitive
    content. Tenant A, while authenticated to its own tenant context,
    runs ``view`` against the same path. The result must NOT include B's
    content. Anthropic's "does not exist" wording is what we surface —
    not "permission denied" — so even the *existence* of B's memory
    doesn't leak."""
    a, b = tenants_ab["a"], tenants_ab["b"]

    # B writes a tenant-wide secret.
    async with db_session.begin():
        await set_tenant(db_session, b)
        db_session.add(
            AgentMemory(
                tenant_id=b,
                customer_id=None,
                path="/memories/tenant/secret.md",
                content="SECRET-OF-B",
            )
        )

    # A — same path; RLS hides B's row, the tool reports "does not exist".
    async with db_session.begin():
        await set_tenant(db_session, a)
        tool_a = NexusPostgresMemoryTool(tenant_id=a, customer_id=None)
        result = await tool_a.view(_view("/memories/tenant/secret.md"))

    assert isinstance(result, str)
    assert "SECRET-OF-B" not in result
    assert "does not exist" in result.lower()


async def test_path_traversal_blocked(db_session, tenants_ab) -> None:
    """``..``, percent-encoded ``%2e%2e``, and Windows-style backslashes
    are all rejected by the path validator before SQL runs."""
    a = tenants_ab["a"]
    async with db_session.begin():
        await set_tenant(db_session, a)
        tool = NexusPostgresMemoryTool(tenant_id=a, customer_id=uuid.uuid4())
        for bad_path in [
            "/memories/customer/me/../../etc/passwd",
            "/memories/customer/me/%2e%2e/escape",
            "/memories/customer/me/..\\windows.ini",
            "/foo/passwd",  # wrong prefix entirely
        ]:
            # The tool surfaces validator errors as ``tool_result`` strings
            # (so the LLM can correct itself) rather than raising. Either
            # way the path must NEVER reach the SQL layer.
            with pytest.raises(PathValidationError):
                validate_and_resolve_path(bad_path, customer_id=tool._customer_id)


async def test_me_alias_resolves_to_current_customer_only(db_session, tenants_ab) -> None:
    """Two customers under the SAME tenant. Customer X writes via the
    ``me`` alias; the row's customer_id must equal X. Customer Y running
    the same ``view`` must not see X's file even though tenant RLS lets
    them share the table."""
    a = tenants_ab["a"]

    async with db_session.begin():
        await set_tenant(db_session, a)
        x_id = await _make_customer(db_session, a, "wa:111")
        y_id = await _make_customer(db_session, a, "wa:222")

    # X writes via "me".
    async with db_session.begin():
        await set_tenant(db_session, a)
        tool_x = NexusPostgresMemoryTool(tenant_id=a, customer_id=x_id)
        await tool_x.create(_create("/memories/customer/me/x_only.md", "X-PRIVATE"))

    # Verify the row's customer_id is X (not the literal string "me").
    async with db_session.begin():
        await set_tenant(db_session, a)
        rows = (
            await db_session.execute(text("SELECT customer_id, content FROM agent_memories"))
        ).all()
        # Exactly one row — the one X just wrote.
        assert len(rows) == 1
        assert str(rows[0][0]) == str(x_id)
        assert rows[0][1] == "X-PRIVATE"

    # Y views the same "me" path: resolved to /memories/customer/{Y_id},
    # so the SQL does not match X's row.
    async with db_session.begin():
        await set_tenant(db_session, a)
        tool_y = NexusPostgresMemoryTool(tenant_id=a, customer_id=y_id)
        view_y = await tool_y.view(_view("/memories/customer/me/x_only.md"))

    assert "X-PRIVATE" not in view_y
    assert "does not exist" in view_y.lower()


async def test_cross_customer_uuid_probe_reads_as_not_exists(db_session, tenants_ab) -> None:
    """Even if the LLM somehow knows another customer's UUID (the worst
    case), the path validator refuses with the same wording it uses for
    a missing path. The attacker cannot use the response to enumerate
    customers."""
    a = tenants_ab["a"]
    async with db_session.begin():
        await set_tenant(db_session, a)
        victim_id = await _make_customer(db_session, a, "wa:victim")
        attacker_id = await _make_customer(db_session, a, "wa:attacker")
        # Victim writes a memory file.
        db_session.add(
            AgentMemory(
                tenant_id=a,
                customer_id=victim_id,
                path=f"/memories/customer/{victim_id}/notes.md",
                content="VICTIM-DATA",
            )
        )

    async with db_session.begin():
        await set_tenant(db_session, a)
        tool = NexusPostgresMemoryTool(tenant_id=a, customer_id=attacker_id)
        result = await tool.view(_view(f"/memories/customer/{victim_id}/notes.md"))

    assert "VICTIM-DATA" not in result
    assert "does not exist" in result.lower()


async def test_unscoped_session_sees_no_memories(db_session, tenants_ab) -> None:
    """Fail-closed: a session with no ``app.tenant_id`` set returns zero
    rows regardless of what is in the table."""
    a = tenants_ab["a"]
    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(
            AgentMemory(
                tenant_id=a,
                customer_id=None,
                path="/memories/tenant/x.md",
                content="anything",
            )
        )

    async with db_session.begin():
        # No set_tenant — app.tenant_id is unset → RLS hides everything.
        await db_session.execute(text("RESET ROLE"))
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        rows = (await db_session.execute(text("SELECT count(*) FROM agent_memories"))).scalar_one()
        assert rows == 0


# ── command construction helpers ─────────────────────────────────────


def _view(path: str):
    """Build a ``BetaMemoryTool20250818ViewCommand`` for the given path."""
    from anthropic.types.beta import BetaMemoryTool20250818ViewCommand

    return BetaMemoryTool20250818ViewCommand(command="view", path=path, view_range=None)


def _create(path: str, file_text: str):
    """Build a ``BetaMemoryTool20250818CreateCommand``."""
    from anthropic.types.beta import BetaMemoryTool20250818CreateCommand

    return BetaMemoryTool20250818CreateCommand(command="create", path=path, file_text=file_text)
