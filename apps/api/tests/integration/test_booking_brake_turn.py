"""Spec 056, T014 — el freno de citas en un turno de verdad (requisitos 1.2, 1.5 y 1.6).

El despachador de verdad (``process_inbound``) contra la base de verdad, con el
grafo de verdad y el transporte de verdad (``LiteLLMProvider``): lo único de
mentira es la petición al proveedor (``_proxied_acompletion``). Un agente sin
herramienta de reservar da por hecha una cita (escenario 2 de la historia 1):

- **dos afirmaciones**: la conversación espera a una persona con
  ``booking_unbacked`` y el contacto recibe la frase de traspaso, nunca la
  confirmación; con Bandeja el agente se calla en esa conversación;
- **una afirmación y una respuesta sincera**: sale la sincera y nada espera;
- **constancia**: una fila ``agent.booking_brake`` con el agente, el turno y el
  resultado, sin el texto;
- **cobro**: cada llamada ``classify`` del freno entra en el ``usage_turn`` del
  turno, con su tarea, como la del clasificador del grafo.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.metering import collector
from nexus_worker.runtime import llm as llm_mod
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.booking_brake import BOOKING_BRAKE_NOTE, CLASSIFY_PROMPT
from nexus_worker.runtime.dispatcher import process_inbound
from nexus_worker.runtime.llm import LiteLLMProvider, LLMRouter
from nexus_worker.runtime.pipeline import _HANDOFF_RESPONSE, build_pipeline

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, ConversationStatus

from ..conftest import add_client_member, make_client_access
from ._turn_world import conversation_of, make_world, outbound_rows, wallet_closed

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CLAIM = "¡Listo! Tu cita queda confirmada para el viernes a las 10."
CLAIM_AGAIN = "Tu cita del viernes a las 10 está confirmada. Te esperamos."
HONEST = "No he podido reservarla: no tengo cómo hacerlo. ¿Te paso con el equipo?"
#: The brake's classify calls report these input tokens, to find them in the meter.
BRAKE_TOKENS = 777


def _system_text(messages: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for m in messages:
        if m.get("role") != "system":
            continue
        content = m.get("content")
        if isinstance(content, list):
            out.extend(str(b.get("text") or "") for b in content if isinstance(b, dict))
        else:
            out.append(str(content))
    return "\n".join(out)


class _Wire:
    """What the provider answers, by the call's role: the graph's classifier
    says ``book``, the brake's says YES, and the agent one draft per attempt."""

    def __init__(self, drafts: list[str]) -> None:
        self.drafts = drafts
        self.brake_checks: list[dict[str, Any]] = []

    async def __call__(self, _litellm: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        role = kwargs["metadata"]["role"]
        messages = kwargs["messages"]
        usage = {"prompt_tokens": 100, "completion_tokens": 5}
        if role == "classify" and CLASSIFY_PROMPT in _system_text(messages):
            self.brake_checks.append(kwargs)
            text = "YES"
            usage = {"prompt_tokens": BRAKE_TOKENS, "completion_tokens": 1}
        elif role == "classify":
            text = "book"
        else:
            retried = any(BOOKING_BRAKE_NOTE in str(m.get("content")) for m in messages)
            text = self.drafts[1 if retried else 0]
        return {"choices": [{"message": {"content": text, "tool_calls": []}}], "usage": usage}


def _pipeline() -> Any:
    router = LLMRouter(
        provider=LiteLLMProvider(context_management=None),
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
    )
    return build_pipeline(
        agent_loader=AgentLoader(),
        llm_router=router,
        checkpointer=MemorySaver(),
        use_ucm_formatter=False,
    )


def _wire(monkeypatch: Any, drafts: list[str]) -> tuple[_Wire, list[tuple[str, list[Any]]]]:
    """The provider's answers, and every usage buffer as it is published."""
    wire = _Wire(drafts)
    monkeypatch.setattr(llm_mod, "_proxied_acompletion", wire)
    published: list[tuple[str, list[Any]]] = []

    async def capture(scope: Any) -> None:
        published.append((scope.turn_id, list(scope.events)))

    monkeypatch.setattr(collector, "_publish", capture)
    return wire, published


async def _brake_rows(tenant_id: uuid.UUID) -> list[AuditLog]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        rows = list(
            (await s.execute(sa.select(AuditLog).where(AuditLog.action == "agent.booking_brake")))
            .scalars()
            .all()
        )
        for row in rows:
            s.expunge(row)
        return rows


def _brake_usage(published: list[tuple[str, list[Any]]], turn_id: str) -> list[Any]:
    return [
        e
        for tid, events in published
        if tid == turn_id
        for e in events
        if e.task == "classify" and e.quantity == BRAKE_TOKENS
    ]


async def test_two_claims_wait_for_a_person_and_the_customer_never_reads_them(
    db_session, monkeypatch
) -> None:
    world = await make_world(db_session)
    wire, published = _wire(monkeypatch, [CLAIM, CLAIM_AGAIN])

    result = await process_inbound(
        world.event("Quiero cita el viernes a las 10"), pipeline=_pipeline()
    )

    assert result["response"] == _HANDOFF_RESPONSE
    assert result["turn_failure"] == {
        "kind": "handoff",
        "reason": "booking_unbacked",
        "detail": None,
    }
    conv = await conversation_of(world)
    assert conv.waiting_reason == "booking_unbacked"
    assert conv.status == ConversationStatus.ESCALATED
    assert conv.agent_active, "sin Bandeja el agente sigue; se avisa a los de escalado"
    sent = [m.content for m in await outbound_rows(world)]
    assert sent == [_HANDOFF_RESPONSE]
    assert not any(CLAIM in s or CLAIM_AGAIN in s for s in sent)

    # Requisito 1.5: la constancia, sin texto.
    [row] = await _brake_rows(world.tenant_id)
    assert row.actor == "system:worker"
    assert row.target == f"conversation:{conv.id}"
    assert row.after_json == {
        "agent_id": str(world.agent_id),
        "turn_id": result["turn_id"],
        "outcome": "handed_off",
    }
    assert CLAIM not in json.dumps(row.after_json) and CLAIM not in json.dumps(row.before_json)

    # Sin Bandeja, los destinatarios de escalado se enteran por la vía de hoy.
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world.tenant_id):
        escalated = (
            (
                await s.execute(
                    sa.select(AuditLog).where(AuditLog.action == "conversation.escalated")
                )
            )
            .scalars()
            .all()
        )
    assert [r.after_json.get("reason") for r in escalated] == ["booking_unbacked"]

    # Requisito 1.6: cada comprobación del freno se cobra dentro del turno.
    assert len(wire.brake_checks) == 2
    metered = _brake_usage(published, result["turn_id"])
    assert len(metered) == 2, metered
    assert all(e.idempotency_key.startswith(f"{result['turn_id']}:") for e in metered)


async def test_with_the_inbox_the_agent_goes_quiet_in_that_conversation(
    db_session, console_world, monkeypatch
) -> None:
    a = console_world["a"]
    world = await make_world(db_session, tenant_id=a["tenant_id"])
    await make_client_access(
        db_session,
        partner_id=a["partner_id"],
        tenant_id=a["tenant_id"],
        modules=("panel", "inbox", "usage"),
    )
    await add_client_member(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    wallet_closed(monkeypatch, closed=False)  # the partner's client has a balance
    _wire(monkeypatch, [CLAIM, CLAIM_AGAIN])

    await process_inbound(world.event("Resérvame el viernes a las 10"), pipeline=_pipeline())

    conv = await conversation_of(world)
    assert conv.waiting_reason == "booking_unbacked"
    assert conv.status == ConversationStatus.ESCALATED
    assert not conv.agent_active, "con Bandeja, una persona la lleva desde aquí"
    assert (conv.takeover_context or {}).get("reason") == "booking_unbacked"
    assert conv.assigned_user_id is None


async def test_a_claim_then_the_truth_sends_the_truth_and_nothing_waits(
    db_session, monkeypatch
) -> None:
    world = await make_world(db_session)
    wire, published = _wire(monkeypatch, [CLAIM, HONEST])

    result = await process_inbound(
        world.event("Quiero cita el viernes a las 10"), pipeline=_pipeline()
    )

    assert result["response"] == HONEST
    assert result.get("turn_failure") is None
    conv = await conversation_of(world)
    assert conv.waiting_reason is None
    assert conv.agent_active
    assert [m.content for m in await outbound_rows(world)] == [HONEST]
    [row] = await _brake_rows(world.tenant_id)
    assert row.after_json["outcome"] == "retried"
    assert len(wire.brake_checks) == 1, "la respuesta sincera no pasa el filtro"
    assert len(_brake_usage(published, result["turn_id"])) == 1
