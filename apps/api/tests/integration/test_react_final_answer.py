"""Spec 047, T029 — el turno termina con respuesta, o con una persona avisada.

Requisitos 1.4 y 1.5.

- **La última iteración** pide una respuesta final sin herramientas. Antes iba
  sin ``tools``, y con un historial que lleva ``tool_calls`` Anthropic vía
  LiteLLM la rechaza (bug B3 de la auditoría del 2026-09-19, «error de LiteLLM
  en la última iteración», bloqueante de ADSL). Ahora declara el catálogo, lo
  cierra con ``tool_choice: "none"`` —como el cierre del Companion— y le pide
  al modelo que conteste con lo que tiene.
- **Un fallo del proveedor sin recuperación** (reintentos y alternativas
  agotados) pasa la conversación a la Bandeja con ``provider_failure`` y avisa a
  los destinatarios de escalado del canal; el turno no queda a medias.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime import llm as llm_mod
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.dispatcher import process_inbound
from nexus_worker.runtime.llm import InMemoryProvider, LLMResponse, LLMRouter, ToolCall
from nexus_worker.runtime.pipeline import FINAL_ANSWER_NOTE, MAX_TOOL_ITERATIONS, build_pipeline

from nexus_api.db.models import AgentConfig, AuditLog, ConversationStatus

from ._turn_world import conversation_of, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_ANSWER = "Tu última visita fue hace dos semanas."


def _note_in(call: Any) -> bool:
    return any(
        m.get("role") == "system" and FINAL_ANSWER_NOTE in str(m.get("content"))
        for m in call.messages
    )


async def _with_tools(db_session: Any, tools: list[str]) -> Any:
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    world = await make_world(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        await s.execute(
            sa.update(AgentConfig).where(AgentConfig.agent_id == world.agent_id).values(tools=tools)
        )
        await s.commit()
    return world


def _router(provider: Any) -> LLMRouter:
    return LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model="t/f"
    )


async def test_the_last_iteration_asks_for_a_final_answer_without_tools(db_session) -> None:
    world = await _with_tools(db_session, ["client.get_history"])
    provider = InMemoryProvider()
    # A model that would keep asking for the tool forever, and only answers
    # when it is told to close.
    provider.responder = lambda c: (
        "info" if c.role == "classify" else (_ANSWER if _note_in(c) else "")
    )
    provider.tool_caller = lambda c: (
        [ToolCall(id=uuid.uuid4().hex[:8], name="client.get_history", arguments={"limit": 5})]
        if c.role == "info"
        else []
    )
    pipeline = build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=_router(provider),
        checkpointer=MemorySaver(),
        use_ucm_formatter=False,
    )

    result = await process_inbound(world.event("dame mi historial"), pipeline=pipeline)

    assert result["response"] == _ANSWER, "el contacto no se queda sin respuesta"
    handler_calls = [c for c in provider.calls if c.role == "info"]
    assert len(handler_calls) == MAX_TOOL_ITERATIONS
    last = handler_calls[-1]
    assert last.tools, "sin catálogo, un historial con tool_calls es un 400 del proveedor"
    assert (last.extra or {}).get("tool_choice") == "none"
    assert _note_in(last)
    assert not any(_note_in(c) for c in handler_calls[:-1]), "solo el cierre lo pide"
    conv = await conversation_of(world)
    assert conv.waiting_reason is None


class _DeadProvider(InMemoryProvider):
    """Clasifica, y al responder el proveedor no contesta nunca."""

    async def acomplete_with_tools(self, **kwargs: Any) -> LLMResponse:
        raise RuntimeError("upstream 503")


async def test_a_provider_that_never_recovers_sends_the_conversation_to_a_person(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(llm_mod, "_RETRY_BACKOFF_S", 0.0)
    world = await make_world(db_session)
    provider = _DeadProvider(responder=lambda c: "info")
    pipeline = build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=_router(provider),
        checkpointer=MemorySaver(),
        use_ucm_formatter=False,
    )

    result = await process_inbound(world.event("¿abren mañana?"), pipeline=pipeline)

    assert result.get("turn_failure", {}).get("kind") == "llm_failed"
    conv = await conversation_of(world)
    assert conv.waiting_reason == "provider_failure"
    assert conv.status == ConversationStatus.ESCALATED
    # Sin Bandeja, los destinatarios de escalado del canal se enteran por la vía
    # de hoy: la fila que el alertador convierte en la plantilla al dueño.
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        rows = (
            (
                await s.execute(
                    sa.select(AuditLog).where(AuditLog.action == "conversation.escalated")
                )
            )
            .scalars()
            .all()
        )
    assert [r.after_json.get("reason") for r in rows] == ["provider_failure"]


class _GraphEndingIn:
    """A compiled graph stand-in: the turn ends with the given failure."""

    def __init__(self, failure: dict[str, Any]) -> None:
        self.failure = failure

    async def ainvoke(self, state: dict[str, Any], config: Any = None) -> dict[str, Any]:
        return {**state, "response": _ANSWER, "turn_failure": self.failure}


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        # Spec 047 (T140): a routed turn hands off with the router's reason.
        ({"kind": "handoff", "reason": "turn_limit"}, "turn_limit"),
        ({"kind": "llm_failed", "reason": "no_model", "detail": None}, "no_model"),
        # A reason the router does not give is a provider failure, as before.
        ({"kind": "handoff", "reason": "anything"}, "provider_failure"),
        ({"kind": "llm_failed", "detail": "upstream 503"}, "provider_failure"),
    ],
)
async def test_the_inbox_reason_is_the_one_the_turn_ended_with(
    db_session: Any, failure: dict[str, Any], expected: str
) -> None:
    world = await make_world(db_session)

    await process_inbound(world.event("¿abren mañana?"), pipeline=_GraphEndingIn(failure))

    conv = await conversation_of(world)
    assert conv.waiting_reason == expected
