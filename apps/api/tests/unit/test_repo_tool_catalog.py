import pytest

from nexus_api.repositories import ToolCatalogRepository

pytestmark = pytest.mark.asyncio


async def test_list_seeds_present(db_session):
    repo = ToolCatalogRepository(db_session)
    items = await repo.list_all()
    names = {t.name for t in items}
    # Spec 048: ``booking.*`` is retired — out of the default listing.
    assert "booking.check_availability" not in names
    assert "reservas.find_slots" in names
    assert "queue.join_queue" in names
    assert "escalate.escalate_to_human" in names


async def test_list_count(db_session):
    repo = ToolCatalogRepository(db_session)
    items = await repo.list_all()
    # 21 Block-D (0003) + operator.consult_owner (0018) + 6 native-output
    # notification tools (0020) + response.send_interactive (0036) = 29;
    # + catalog.search_products y catalog.get_product (0135, spec 022) = 31;
    # + payments.request_review (0137, spec 025) = 32;
    # + los nueve reservas.* (0173, spec 043) = 41;
    # + reception.handoff (0200, spec 047) = 42;
    # minus the five booking.* the 0205 retired (spec 048: ``deprecated``) = 37.
    # The ``agendapro.*`` internal rows are gone (0021 and 0205).
    # WooCommerce tools live in connectors, not in the global tool_catalog
    # seed this repo test sees.
    assert len(items) == 37
    retired = await repo.list_all(include_deprecated=True)
    assert len(retired) == 42


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
    """Spec 048: the five ``booking.*`` are the retired ones — only they fall
    out of the default listing."""
    repo = ToolCatalogRepository(db_session)
    a = {t.name for t in await repo.list_all(include_deprecated=False)}
    b = {t.name for t in await repo.list_all(include_deprecated=True)}
    assert b - a == {
        "booking.check_availability",
        "booking.create_appointment",
        "booking.modify_appointment",
        "booking.cancel_appointment",
        "booking.get_appointments",
    }
