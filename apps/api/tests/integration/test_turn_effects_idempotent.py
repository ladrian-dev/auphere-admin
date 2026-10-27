"""Spec 047, T028 — un turno que se reintenta no repite nada que se note.

Requisitos 1.3 y 1.6. El turno revienta **después** de reservar y de dejar la
respuesta escrita (lo peor que puede pasar), y se reintenta como lo reintenta
el stream: mismo mensaje, mismo turno. Cada efecto pasa por ``turn_effects`` con
la clave ``turno:acción``:

- la reserva (una herramienta con efecto) ocurre una vez y el reintento recibe
  la misma respuesta;
- la respuesta al contacto se escribe una vez;
- el turno se mide con el mismo ``turn_id`` en los dos intentos, así que el
  débito (``channel:{turno}``, idempotente en el libro) se cobra una vez.

Contra el grafo de verdad (ReAct con ``InMemoryProvider``) y la base de verdad.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa
from langgraph.checkpoint.memory import MemorySaver
from nexus_mcp import MCPRegistry
from nexus_mcp.base import InputModel, OutputModel, ToolBase
from nexus_worker.metering import consumer as metering
from nexus_worker.metering.collector import USAGE_STREAM, record_llm_usage
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.dispatcher import process_inbound
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter, ToolCall
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.turns import TurnRetry

from nexus_api.core import redis_client
from nexus_api.db.models import TurnEffect

from ._turn_world import make_world, outbound_rows

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TOOL = "testshop.reserve"


class _ReserveIn(InputModel):
    slot: str


class _ReserveOut(OutputModel):
    booking_id: str


class CountingReserve(ToolBase):
    """Una reserva de verdad, contada. Si el reintento la repite, se ve."""

    name = TOOL
    description = "Reserva un hueco en la agenda del negocio."
    input_model = _ReserveIn
    output_model = _ReserveOut
    side_effects = ("mutates_db",)
    runs: ClassVar[int] = 0

    async def run(self, payload: InputModel) -> OutputModel:
        assert isinstance(payload, _ReserveIn)
        CountingReserve.runs += 1
        return _ReserveOut(booking_id=f"booking-{CountingReserve.runs}")


class CrashAfterTheTurn:
    """El grafo de verdad, que revienta la primera vez **después** de acabar: la
    reserva hecha y la respuesta escrita. Mide una llamada al modelo por intento,
    como haría el proveedor de verdad."""

    def __init__(self, graph: Any) -> None:
        self.graph = graph
        self.crashes = 1

    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> Any:
        record_llm_usage(
            model="t/r",
            provider="t",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            task="tool_turn",
        )
        final = await self.graph.ainvoke(state, config=config)
        if self.crashes:
            self.crashes -= 1
            raise RuntimeError("el worker murió justo al acabar")
        return final


def _graph() -> Any:
    def responder(call: Any) -> str:
        if call.role == "classify":
            return "info"
        return "Te reservé mañana a las 18:00." if _saw_tool(call) else ""

    def tool_caller(call: Any) -> list[ToolCall]:
        if call.role == "info" and not _saw_tool(call):
            return [ToolCall(id="r1", name=TOOL, arguments={"slot": "mañana 18:00"})]
        return []

    provider = InMemoryProvider(responder=responder, tool_caller=tool_caller)
    router = LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model="t/f"
    )
    return build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=router,
        checkpointer=MemorySaver(),
        mcp_registry=MCPRegistry(tools=[CountingReserve()]),
        use_ucm_formatter=False,
    )


def _saw_tool(call: Any) -> bool:
    return any(m.get("role") == "tool" for m in call.messages)


async def _world(db_session: Any) -> Any:
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import AgentConfig

    world = await make_world(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        await s.execute(
            sa.update(AgentConfig)
            .where(AgentConfig.agent_id == world.agent_id)
            .values(tools=[TOOL])
        )
        await s.commit()
    return world


async def test_a_retried_turn_reserves_once_and_answers_once(db_session) -> None:
    CountingReserve.runs = 0
    world = await _world(db_session)
    pipeline = CrashAfterTheTurn(_graph())
    event = world.event("quiero cita mañana a las 6", wamid="wamid.effects-1")

    with pytest.raises(TurnRetry):
        await process_inbound(event, pipeline=pipeline)
    assert CountingReserve.runs == 1
    assert len(await outbound_rows(world)) == 1

    # El stream lo vuelve a entregar: mismo mensaje, mismo turno.
    result = await process_inbound(event, pipeline=pipeline)

    assert result.get("skipped") is None
    assert CountingReserve.runs == 1, "la reserva no se repite"
    replies = await outbound_rows(world)
    assert [m.content for m in replies] == ["Te reservé mañana a las 18:00."], (
        "una sola respuesta llega al contacto"
    )
    rows = await _effects(world)
    keys = {r["idempotency_key"]: r["effect"] for r in rows}
    turn = rows[0]["turn_id"]
    assert keys[f"{turn}:{TOOL}:1"] == "tool", "la clave es turno:acción:n"
    assert keys[f"{turn}:reply:1"] == "reply"
    assert {r["turn_id"] for r in rows} == {turn}, "todo cuelga del mismo turno"


def test_each_real_effect_has_its_name_in_the_log() -> None:
    """``turn.effect`` (``contracts/events.md`` §5) dice qué clase de efecto es."""
    from nexus_worker.runtime.turn_effects import effect_for_tool

    assert effect_for_tool("reservas.create") == "reserve"
    assert effect_for_tool("booking.create_appointment") == "reserve"
    assert effect_for_tool("woocommerce.build_checkout_link") == "send_link"
    assert effect_for_tool("payments.request_review") == "send_link"
    assert effect_for_tool("billing.register_payment") == "charge"
    assert effect_for_tool("notion.create_page") == "tool"


async def _effects(world: Any) -> list[dict[str, Any]]:
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        result = await s.execute(
            sa.select(TurnEffect.turn_id, TurnEffect.effect, TurnEffect.idempotency_key)
        )
        return [dict(r) for r in result.mappings().all()]


async def _llm_entries(world: Any) -> list[dict[str, str]]:
    entries = await redis_client.get_redis().xrange(USAGE_STREAM)
    return [
        fields
        for _entry_id, fields in entries
        if fields.get("tenant_id") == str(world.tenant_id)
        and any(e["meter"].startswith("llm.") for e in json.loads(fields["events"]))
    ]


async def test_the_retry_is_charged_as_the_same_turn(db_session, monkeypatch) -> None:
    CountingReserve.runs = 0
    world = await _world(db_session)
    pipeline = CrashAfterTheTurn(_graph())
    event = world.event("quiero cita", wamid="wamid.effects-2")

    with pytest.raises(TurnRetry):
        await process_inbound(event, pipeline=pipeline)
    await process_inbound(event, pipeline=pipeline)

    turn_entries = await _llm_entries(world)
    assert len(turn_entries) == 2, "los dos intentos gastaron y los dos se miden"
    assert {f["source"] for f in turn_entries} == {"channel"}
    assert len({f["turn_id"] for f in turn_entries}) == 1, "mismo turno en los dos intentos"

    rows: list[dict[str, Any]] = []
    for fields in turn_entries:
        _tenant, entry_rows = metering.rows_from_entry(fields)
        rows.extend(entry_rows)
    weights = {"t/r": {"input": Decimal(1), "cache_read": Decimal(1), "output": Decimal(1)}}
    charged = metering._turn_quota(rows, weights)
    assert list(charged) == [turn_entries[0]["turn_id"]], "un débito por turno: channel:{turno}"
    assert uuid.UUID(turn_entries[0]["turn_id"])
