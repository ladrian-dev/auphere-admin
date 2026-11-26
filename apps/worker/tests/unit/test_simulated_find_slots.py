"""Spec 080, requisito 3 — la agenda simulada busca sin fecha como la de verdad.

El Playground y las pruebas del agente usan la agenda simulada. Si contestara a una
búsqueda sin fecha con otra forma (o con un error), el modelo aprendería ahí un
contrato distinto del que encuentra con clientes de verdad.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from nexus_api.core.tenant_context import tenant_context
from nexus_mcp import MCPRegistry
from nexus_mcp.servers.reservas.schemas import FindSlotsOutput

from nexus_worker.runtime.llm import ToolCall
from nexus_worker.runtime.pipeline import _dispatch_tool
from nexus_worker.simulation.registry import SimulatedRegistry
from nexus_worker.simulation.world import SimService, World

pytestmark = pytest.mark.asyncio

#: Lunes 9 de noviembre de 2026, 13:24 en Madrid; abre todos los días de 10 a 20.
NOW = "2026-11-09T12:24:00+00:00"
OPEN = [[[600, 1200]] for _ in range(7)]
CUT = SimService(id=str(uuid.uuid4()), name="Corte", duration_min=30, bookable=True)


@pytest.fixture(autouse=True)
def tenant() -> Iterator[uuid.UUID]:
    with tenant_context(uuid.uuid4()) as tenant_id:
        yield tenant_id


def _registry(*, now: str = NOW, week: list[list[list[int]]] | None = OPEN) -> SimulatedRegistry:
    world = World(timezone="Europe/Madrid", now=now, week=week, services=[CUT])
    return SimulatedRegistry(world, base=MCPRegistry())


async def _find(registry: SimulatedRegistry, **args: Any) -> dict[str, Any]:
    env = await _dispatch_tool(
        registry,
        ToolCall(id="c", name="reservas.find_slots", arguments=args),
        ("reservas.find_slots",),
        "book",
    )
    assert env["status"] == "ok", env
    result = {k: v for k, v in env["result"].items() if k != "simulated"}
    FindSlotsOutput.model_validate(result)  # la forma de verdad, sin claves de más
    return result


async def test_without_a_date_the_first_times_are_today_in_order() -> None:
    out = await _find(_registry(), service_name="corte")

    assert out["date"] is None
    assert out["searched_from"] == "2026-11-09"
    slots = out["slots"]
    assert len(slots) == 6
    assert (slots[0]["date"], slots[0]["weekday"], slots[0]["time"]) == (
        "2026-11-09",
        "monday",
        "13:30",
    )
    assert [(s["date"], s["time"]) for s in slots] == sorted((s["date"], s["time"]) for s in slots)


async def test_after_closing_it_goes_on_to_the_next_open_day() -> None:
    week = [list(d) for d in OPEN]
    week[1] = []  # el martes cierra
    out = await _find(_registry(now="2026-11-09T20:30:00+00:00", week=week), service_name="corte")

    assert (out["slots"][0]["date"], out["slots"][0]["time"]) == ("2026-11-11", "10:00")
    assert out["slots"][0]["weekday"] == "wednesday"


async def test_with_no_hours_it_says_so() -> None:
    out = await _find(_registry(week=None), service_name="corte")

    assert out["closed"] is True and out["why_closed"] == "hours_missing"


async def test_with_a_date_the_shape_is_as_before() -> None:
    out = await _find(_registry(), date="2026-11-10", service_name="corte")

    assert out["date"] == "2026-11-10"
    assert "searched_from" not in out
    assert all("date" not in s and "weekday" not in s for s in out["slots"])
