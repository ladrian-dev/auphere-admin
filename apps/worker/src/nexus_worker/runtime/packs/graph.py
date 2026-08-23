"""One compiled parent graph. Node names are FIXED. The pack is not a graph."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

PARENT_NODE_NAMES: tuple[str, ...] = ("send_template", "wait_reply", "end")
RECURSION_LIMIT = 8

_sender: Any = None


class PackState(TypedDict, total=False):
    partner_id: str
    thread_id: str
    run_id: str
    template_id: str
    sent: bool
    reply: Any


def set_sender(fn: Any) -> None:
    """Test hook. Production uses a noop until Meta is wired by the channel."""
    global _sender
    _sender = fn


def _get_sender() -> Any:
    if _sender is not None:
        return _sender

    def _noop() -> None:
        return None

    return _noop


async def node_send_template(state: PackState) -> dict[str, Any]:
    """Art. 50 first outbound. Receipt is written BEFORE wait_reply."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.packs.send import send_if_new

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        sent = await send_if_new(
            session,
            partner_id=uuid.UUID(str(state["partner_id"])),
            thread_id=str(state["thread_id"]),
            step_id="send_template",
            run_id=str(state["run_id"]),
            sender=_get_sender(),
        )
    return {"sent": sent}


def node_wait_reply(state: PackState) -> dict[str, Any]:
    reply = interrupt({"kind": "wait_reply", "thread_id": state.get("thread_id")})
    return {"reply": reply}


def node_end(_state: PackState) -> dict[str, Any]:
    return {}


def compile_parent_graph(*, checkpointer: Any = None) -> Any:
    graph = StateGraph(PackState)
    graph.add_node("send_template", node_send_template)
    graph.add_node("wait_reply", node_wait_reply)
    graph.add_node("end", node_end)  # type: ignore[arg-type]
    graph.add_edge(START, "send_template")
    graph.add_edge("send_template", "wait_reply")
    graph.add_edge("wait_reply", "end")
    graph.add_edge("end", END)
    return graph.compile(checkpointer=checkpointer)


def parent_node_names() -> tuple[str, ...]:
    return PARENT_NODE_NAMES
