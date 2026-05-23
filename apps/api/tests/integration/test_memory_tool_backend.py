"""Functional coverage of ``NexusPostgresMemoryTool``.

These tests drive the tool against real Postgres + the trigger that
fills ``agent_memory_versions``. They live in apps/api/tests/integration
(not apps/worker/tests/unit) because the tool's behaviour is
inseparable from the DB schema in migration 0032 — the trigger, the
UNIQUE index, and RLS are all exercised here.

The isolation invariants live in ``tests/isolation/test_memory_isolation.py``;
this module only covers the *happy path* shape of each command + a few
"the docs say" semantic edges (str_replace on duplicates, create on
existing path).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from anthropic.types.beta import (
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)
from nexus_worker.memory import (
    MAX_MEMORY_BYTES_PER_CUSTOMER,
    NexusPostgresMemoryTool,
)
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio]


@pytest_asyncio.fixture
async def seeded_tenant(db_session) -> dict[str, uuid.UUID]:
    """One tenant + one customer, both real rows so FKs are satisfied."""
    from nexus_api.db.models import Customer, Tenant, TenantPlan

    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="MemTenant",
            slug=f"mem-{tenant_id.hex[:6]}",
            plan=TenantPlan.INTERNAL,
        )
    )
    await db_session.flush()
    # Customer needs a tenant-scoped session (RLS on customers).
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    customer = Customer(
        tenant_id=tenant_id,
        identifier="wa:111",
        name="Test Customer",
    )
    db_session.add(customer)
    await db_session.commit()
    return {"tenant_id": tenant_id, "customer_id": customer.id}


async def _set_tenant(db_session, tenant_id: uuid.UUID) -> None:
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))


def _tool(ids: dict[str, uuid.UUID]) -> NexusPostgresMemoryTool:
    return NexusPostgresMemoryTool(
        tenant_id=ids["tenant_id"], customer_id=ids["customer_id"]
    )


# ── create + view ────────────────────────────────────────────────────


async def test_create_then_view_returns_line_numbers(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    res_create = await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/prefs.md",
            file_text="line one\nline two\nline three",
        )
    )
    assert "created" in res_create.lower()

    res_view = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/customer/me/prefs.md",
            view_range=None,
        )
    )
    assert isinstance(res_view, str)
    # 6-char right-aligned line numbers + tab separator (Anthropic format).
    assert "     1\tline one" in res_view
    assert "     2\tline two" in res_view
    assert "     3\tline three" in res_view


async def test_create_idempotent_fails(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/notes.md",
            file_text="first",
        )
    )
    res = await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/notes.md",
            file_text="second",
        )
    )
    # Should be a string-shaped error, NOT an exception.
    assert "already exists" in res.lower()


async def test_view_directory_returns_tab_separated_listing(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    for name in ("a.md", "b.md"):
        await tool.create(
            BetaMemoryTool20250818CreateCommand(
                command="create",
                path=f"/memories/customer/me/{name}",
                file_text="x",
            )
        )
    res = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/customer/me",
            view_range=None,
        )
    )
    assert isinstance(res, str)
    assert "a.md" in res
    assert "b.md" in res
    # Format: ``<size>\t<path>`` per line.
    for line in res.split("\n"):
        size, path = line.split("\t")
        assert size.isdigit()
        assert path.startswith("/memories/customer/")


# ── str_replace semantics ─────────────────────────────────────────────


async def test_str_replace_unique_match_succeeds(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/prefs.md",
            file_text="Likes morning slots\nDoesn't like beard",
        )
    )
    res = await tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path="/memories/customer/me/prefs.md",
            old_str="Doesn't like beard",
            new_str="Allergic to specific oil",
        )
    )
    assert "replaced" in res.lower()
    # Verify it stuck.
    view = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/customer/me/prefs.md",
            view_range=None,
        )
    )
    assert "Allergic to specific oil" in view
    assert "Doesn't like beard" not in view


async def test_str_replace_duplicate_match_errors(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/x.md",
            file_text="foo bar foo bar",
        )
    )
    res = await tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path="/memories/customer/me/x.md",
            old_str="foo",
            new_str="baz",
        )
    )
    assert "matches 2 times" in res or "be more specific" in res


# ── insert + delete + rename ─────────────────────────────────────────


async def test_insert_appends_line(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/notes.md",
            file_text="first\nsecond",
        )
    )
    await tool.insert(
        BetaMemoryTool20250818InsertCommand(
            command="insert",
            path="/memories/customer/me/notes.md",
            insert_line=1,
            insert_text="between",
        )
    )
    res = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/customer/me/notes.md",
            view_range=None,
        )
    )
    assert "     1\tfirst" in res
    assert "     2\tbetween" in res
    assert "     3\tsecond" in res


async def test_delete_removes_file(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/dead.md",
            file_text="bye",
        )
    )
    res = await tool.delete(
        BetaMemoryTool20250818DeleteCommand(
            command="delete",
            path="/memories/customer/me/dead.md",
        )
    )
    assert "deleted" in res.lower()
    # Subsequent view says "does not exist".
    view = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/customer/me/dead.md",
            view_range=None,
        )
    )
    assert "does not exist" in view.lower()


async def test_rename_within_same_scope(seeded_tenant) -> None:
    tool = _tool(seeded_tenant)
    await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/old.md",
            file_text="x",
        )
    )
    res = await tool.rename(
        BetaMemoryTool20250818RenameCommand(
            command="rename",
            old_path="/memories/customer/me/old.md",
            new_path="/memories/customer/me/new.md",
        )
    )
    assert "renamed" in res.lower()
    view_new = await tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path="/memories/customer/me/new.md",
            view_range=None,
        )
    )
    assert "     1\tx" in view_new


# ── versioning trigger ───────────────────────────────────────────────


async def test_audit_trigger_writes_versions_on_each_op(seeded_tenant, db_session) -> None:
    """Every INSERT / UPDATE / DELETE on agent_memories must produce a
    row in agent_memory_versions. Without this, ``str_replace`` history
    is lost forever."""
    tool = _tool(seeded_tenant)
    await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/x.md",
            file_text="v1",
        )
    )
    await tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path="/memories/customer/me/x.md",
            old_str="v1",
            new_str="v2",
        )
    )
    await tool.delete(
        BetaMemoryTool20250818DeleteCommand(
            command="delete",
            path="/memories/customer/me/x.md",
        )
    )
    async with db_session.begin():
        await _set_tenant(db_session, seeded_tenant["tenant_id"])
        rows = (
            await db_session.execute(
                text(
                    "SELECT operation, content FROM agent_memory_versions "
                    "ORDER BY versioned_at ASC"
                )
            )
        ).all()
    ops = [r[0] for r in rows]
    contents = [r[1] for r in rows]
    assert ops == ["insert", "update", "delete"]
    assert contents == ["v1", "v2", "v2"]  # delete records the last value


# ── byte cap ─────────────────────────────────────────────────────────


async def test_byte_cap_blocks_oversize_create(seeded_tenant) -> None:
    """A single create that would push the customer over the cap is
    rejected with a string error (LLM-correctable)."""
    tool = _tool(seeded_tenant)
    payload = "x" * (MAX_MEMORY_BYTES_PER_CUSTOMER + 100)
    res = await tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path="/memories/customer/me/huge.md",
            file_text=payload,
        )
    )
    assert "memory full" in res.lower()
    assert "exceed" in res.lower()
