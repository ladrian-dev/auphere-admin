import pytest

from nexus_api.repositories import ToolCatalogRepository

pytestmark = pytest.mark.asyncio


async def test_list_seeds_present(db_session):
    repo = ToolCatalogRepository(db_session)
    items = await repo.list_all()
    names = {t.name for t in items}
    assert "booking.check_availability" in names
    assert "queue.join_queue" in names
    assert "escalate.escalate_to_human" in names


async def test_list_count(db_session):
    repo = ToolCatalogRepository(db_session)
    items = await repo.list_all()
    # 21 Block-D (0003) + operator.consult_owner (0018) + 6 native-output
    # notification tools (0020) + response.send_interactive (0036) = 29.
    # The 6 ``agendapro.*`` internal tools were removed by migration
    # 0021 (ADR-017). WooCommerce tools live in connectors, not in the
    # global tool_catalog seed this repo test sees.
    assert len(items) == 29


async def test_get_by_name(db_session):
    repo = ToolCatalogRepository(db_session)
    tool = await repo.get_by_name("booking.create_appointment")
    assert tool is not None
    assert tool.mcp_server == "booking-server"
    assert "external_api" in tool.side_effects
    assert "mutates_db" in tool.side_effects


async def test_get_by_name_unknown(db_session):
    repo = ToolCatalogRepository(db_session)
    assert await repo.get_by_name("does.not.exist") is None


async def test_list_excludes_deprecated_by_default(db_session):
    """All seeded tools are 'active', so include_deprecated=False yields the same."""
    repo = ToolCatalogRepository(db_session)
    a = await repo.list_all(include_deprecated=False)
    b = await repo.list_all(include_deprecated=True)
    assert len(a) == len(b)
