"""The turn's conversation reaches the tools without the model writing it.

A required ``conversation_id`` is an internal UUID the model cannot know. Shown
to it, the model invents one or refuses the call: «I can't transfer you, the
conversation ID isn't available», and the hand-off to a person never happens
(QA canales Meta, 2026-10-31). So the model doesn't see a required one, and
``_dispatch_tool`` fills it in.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from nexus_mcp import ToolDef
from nexus_mcp.servers.escalate.tools import EscalateToHuman

import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime.llm import ToolCall

ESCALATE = EscalateToHuman.name
CONV = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))


def _plain_def() -> ToolDef:
    return ToolDef(
        name="catalog.search_products",
        description="Search",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    )


def _optional_def() -> ToolDef:
    return ToolDef(
        name="reservas.create",
        description="Book",
        parameters={
            "type": "object",
            "properties": {"service": {"type": "string"}, "conversation_id": {"type": "string"}},
            "required": ["service"],
        },
    )


@dataclass
class _Registry:
    defs: dict[str, ToolDef]
    dispatched: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def get_tool_definitions(self, whitelist: Any) -> list[ToolDef]:
        return [self.defs[n] for n in sorted(self.defs) if n in set(whitelist)]

    async def dispatch(self, name: str, args: dict[str, Any], *, whitelist: Any) -> dict[str, Any]:
        self.dispatched.append((name, args))
        return {"tool": name, "status": "ok", "result": {}}


def _registry() -> _Registry:
    defs = [EscalateToHuman.to_tool_def(), _plain_def(), _optional_def()]
    return _Registry({d.name: d for d in defs})


def test_the_model_does_not_see_a_required_conversation_id() -> None:
    defs = [d.to_openai_tool() for d in _registry().defs.values()]
    before = copy.deepcopy(defs)

    shown = {
        d["function"]["name"]: d["function"]["parameters"]
        for d in pipeline._hide_conversation_arg(defs)
    }

    assert "conversation_id" not in shown[ESCALATE]["properties"]
    assert "conversation_id" not in shown[ESCALATE]["required"]
    assert "reason" in shown[ESCALATE]["required"]
    # An optional one stays, and a tool without it is untouched.
    assert "conversation_id" in shown["reservas.create"]["properties"]
    plain = next(d for d in before if d["function"]["name"] == "catalog.search_products")
    assert shown["catalog.search_products"] == plain["function"]["parameters"]
    # The registry's own definitions are not mutated.
    assert defs == before


@pytest.mark.asyncio
async def test_a_required_conversation_id_is_filled_in_when_the_model_omits_it() -> None:
    reg = _registry()
    call = ToolCall(id="c1", name=ESCALATE, arguments={"reason": "Asked for a person"})

    env = await pipeline._dispatch_tool(reg, call, (ESCALATE,), "escalate", conversation_id=CONV)  # type: ignore[arg-type]

    assert env["status"] == "ok"
    assert reg.dispatched == [(ESCALATE, {"reason": "Asked for a person", "conversation_id": CONV})]


@pytest.mark.asyncio
async def test_an_invented_conversation_id_is_replaced() -> None:
    reg = _registry()
    call = ToolCall(
        id="c1", name="reservas.create", arguments={"service": "x", "conversation_id": "made-up"}
    )

    await pipeline._dispatch_tool(reg, call, ("reservas.create",), "book", conversation_id=CONV)  # type: ignore[arg-type]

    assert reg.dispatched[0][1]["conversation_id"] == CONV


@pytest.mark.asyncio
async def test_nothing_is_added_where_the_tool_has_no_conversation() -> None:
    reg = _registry()
    plain = ToolCall(id="c1", name="catalog.search_products", arguments={"q": "rosa"})
    optional = ToolCall(id="c2", name="reservas.create", arguments={"service": "x"})

    await pipeline._dispatch_tool(
        reg, plain, ("catalog.search_products",), "info", conversation_id=CONV
    )  # type: ignore[arg-type]
    await pipeline._dispatch_tool(reg, optional, ("reservas.create",), "book", conversation_id=CONV)  # type: ignore[arg-type]

    assert reg.dispatched == [
        ("catalog.search_products", {"q": "rosa"}),
        ("reservas.create", {"service": "x"}),
    ]


@pytest.mark.asyncio
async def test_without_a_conversation_nothing_is_filled_in() -> None:
    reg = _registry()
    call = ToolCall(id="c1", name=ESCALATE, arguments={"reason": "r"})

    await pipeline._dispatch_tool(reg, call, (ESCALATE,), "escalate", conversation_id=None)  # type: ignore[arg-type]

    assert reg.dispatched == [(ESCALATE, {"reason": "r"})]
