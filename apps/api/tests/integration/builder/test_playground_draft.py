"""Spec 047, T082 — probarlo antes de que hable con nadie: el playground (historia 8; requisito 20).

- **Qué ejecuta**: el borrador, o una versión que se elija, con el mismo grafo
  que el canal.
- **Sin efectos**: una prueba adversarial que intenta cada herramienta con
  efecto. Ninguna reserva real, ningún aviso, ningún recordatorio, ningún cambio
  en los datos del cliente; todo queda en «Lo que habría hecho».
- **Simulación**: la hora simulada en la zona del negocio y la agenda simulada
  sembrada desde la ficha, que las acciones del agente modifican.
- **Lo que enseña**: las burbujas, señalando cuando hay más de una.
- **Quién**: owner, admin y builder; el analyst, en solo lectura.
- **Medidor**: la partida de construcción.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter, ToolCall
from nexus_worker.simulation.runner import set_simulation_router
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Conversation, Reservation, ScheduledJob
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business, write
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MADRID = ZoneInfo("Europe/Madrid")
WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    # La barbería tiene Reservas encendido: sin él, la agenda cuenta como sin activar (D67).
    await turn_reservas_on(db_session, biz)
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    await write(
        client,
        biz,
        "POST",
        "/services",
        {
            "name": "Corte de pelo",
            "bookable": True,
            "duration_min": 30,
            "price": {"kind": "amount", "amount_minor": 1500},
        },
        revision=0,
        expect=201,
    )
    return biz


@pytest.fixture
def scripted() -> Any:
    provider = InMemoryProvider()
    set_simulation_router(
        LLMRouter(provider=provider, classify_model="t/c", respond_model="t/r", fallback_model="")
    )
    yield provider
    set_simulation_router(None)


def _next_monday() -> date:
    today = datetime.now(MADRID).date()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


async def _agent(
    client: Any, biz: Biz, fake_redis: Any, tools: list[str] | None = None
) -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    agent_id = uuid.UUID(body["result"]["agent_id"])
    if tools is not None:
        url = f"/console/clients/{biz.ref}/agents/{agent_id}/draft"
        draft = (await client.get(url, headers=biz.headers())).json()
        spec = draft["spec"]
        spec["tools"] = tools
        spec.pop("procedures", None)
        resp = await client.patch(
            url,
            json={"spec": spec},
            headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
        )
        assert resp.status_code == 200, resp.text
    return agent_id


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}/playground/sessions"


def _script(
    provider: InMemoryProvider, calls: list[ToolCall], answer: str, *, intent: str = "info"
) -> None:
    """Un modelo que clasifica en ``intent``, pide estas herramientas, una por
    llamada, y luego contesta. Anota sus tokens como el proveedor de verdad."""
    from nexus_worker.metering.collector import record_llm_usage

    pending = list(calls)

    def tool_caller(call: Any) -> list[ToolCall]:
        if call.role == "classify" or not pending:
            return []
        return [pending.pop(0)]

    def responder(call: Any) -> str:
        record_llm_usage(
            model="anthropic/claude-haiku-5-5",
            provider="anthropic",
            usage={"prompt_tokens": 500, "completion_tokens": 50},
            task="classify" if call.role == "classify" else "answer",
        )
        return intent if call.role == "classify" else answer

    provider.responder = responder
    provider.tool_caller = tool_caller


async def test_it_runs_the_draft_with_simulated_time_and_agenda(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, scripted: InMemoryProvider
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    monday = _next_monday()
    # «Mañana a las 23:30»: la víspera, de noche, en la zona del negocio.
    sim_now = datetime.combine(monday - timedelta(days=1), datetime.min.time(), MADRID).replace(
        hour=23, minute=30
    )
    opened = await client.post(
        _url(biz, agent_id),
        json={"version": "draft", "now": sim_now.isoformat()},
        headers=biz.headers(),
    )
    assert opened.status_code == 201, opened.text
    session = opened.json()
    assert session["is_draft"] is True and session["timezone"] == "Europe/Madrid"
    assert datetime.fromisoformat(session["now"]).astimezone(MADRID).hour == 23
    assert session["services"][0]["name"] == "Corte de pelo"
    assert session["agenda"] == []

    _script(
        scripted,
        [
            ToolCall(id="c1", name="reservas.find_slots", arguments={"date": monday.isoformat()}),
            ToolCall(
                id="c2",
                name="reservas.create",
                arguments={"date": monday.isoformat(), "time": "10:00", "idempotency_key": "k1"},
            ),
        ],
        "Listo, te reservé el lunes a las 10:00.",
        intent="book",
    )
    sent = await client.post(
        f"{_url(biz, agent_id)}/{session['session_id']}/messages",
        json={"text": "Hola, ¿tienes hueco el lunes por la mañana?"},
        headers=biz.headers(),
    )
    assert sent.status_code == 200, sent.text
    out = sent.json()
    assert out["turn"]["bubbles"] == ["Listo, te reservé el lunes a las 10:00."]
    assert out["turn"]["several_bubbles"] is False
    phrases = [a["phrase"] for a in out["turn"]["actions"]]
    assert any(p.startswith("Reservar ") and "a las 10:00" in p for p in phrases), phrases
    # La agenda simulada cambió; la de verdad, no.
    assert len(out["agenda"]) == 1 and out["agenda"][0]["when"].endswith("a las 10:00")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        real = await db_session.scalar(sa.select(sa.func.count()).select_from(Reservation))
    assert real == 0
    # La nota de la hora que vio el modelo es la simulada.
    seen = "\n".join(str(m.get("content")) for c in scripted.calls for m in c.messages)
    assert (monday - timedelta(days=1)).strftime("%d/%m/%Y") in seen and "23:3" in seen


async def test_no_side_effect_leaves_the_simulation(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, scripted: InMemoryProvider
) -> None:
    tools = [
        "reservas.find_slots",
        "reservas.create",
        "escalate.escalate_to_human",
        "notification.schedule_reminder",
        "notification.send_template",
        "notification.send_text",
        "payments.request_review",
        "client.update_preferences",
    ]
    agent_id = await _agent(client, biz, fake_redis, tools=tools)
    session = (await client.post(_url(biz, agent_id), json={}, headers=biz.headers())).json()
    monday = _next_monday()
    url = f"{_url(biz, agent_id)}/{session['session_id']}/messages"
    # Turno 1, reservar: lo que cambia la agenda, los datos del cliente y los pagos.
    _script(
        scripted,
        [
            ToolCall(
                id="a",
                name="reservas.create",
                arguments={"date": monday.isoformat(), "time": "11:00", "idempotency_key": "k"},
            ),
            ToolCall(
                id="f",
                name="client.update_preferences",
                arguments={"preferences": {"barber": "Luis"}},
            ),
            ToolCall(
                id="e",
                name="payments.request_review",
                arguments={"conversation_id": str(uuid.uuid4()), "method": "transferencia"},
            ),
        ],
        "Hecho.",
        intent="book",
    )
    first = await client.post(url, json={"text": "Resérvame y paga"}, headers=biz.headers())
    assert first.status_code == 200, first.text
    # Turno 2, escalar: avisos, plantillas y una burbuja de más.
    _script(
        scripted,
        [
            ToolCall(
                id="b",
                name="escalate.escalate_to_human",
                arguments={
                    "conversation_id": str(uuid.uuid4()),
                    "reason": "Quiere hablar con Marta",
                },
            ),
            ToolCall(
                id="d",
                name="notification.send_template",
                arguments={"conversation_id": str(uuid.uuid4()), "template_name": "x"},
            ),
            ToolCall(
                id="g",
                name="notification.send_text",
                arguments={"conversation_id": str(uuid.uuid4()), "body": "Te mando otra burbuja."},
            ),
        ],
        "Hecho.",
        intent="escalate",
    )
    sent = await client.post(url, json={"text": "Pásame con Marta"}, headers=biz.headers())
    assert sent.status_code == 200, sent.text
    turn = sent.json()["turn"]
    tools_done = {a["tool"] for a in first.json()["turn"]["actions"]} | {
        a["tool"] for a in turn["actions"]
    }
    assert {
        "reservas.create",
        "client.update_preferences",
        "payments.request_review",
        "escalate.escalate_to_human",
        "notification.send_template",
    } <= tools_done, tools_done
    assert any(a["phrase"].startswith("Pasar la conversación al equipo") for a in turn["actions"])
    # 20.4: dos burbujas en el turno, y se señala.
    assert (
        turn["bubbles"] == ["Hecho.", "Te mando otra burbuja."] and turn["several_bubbles"] is True
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        reservations = await db_session.scalar(sa.select(sa.func.count()).select_from(Reservation))
        jobs = await db_session.scalar(sa.select(sa.func.count()).select_from(ScheduledJob))
        escalated = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Conversation)
            .where(Conversation.status == "escalated")
        )
    assert (reservations, jobs, escalated) == (0, 0, 0)
    assert (
        await fake_redis.xlen("nexus:outbound") == 0
        if await fake_redis.exists("nexus:outbound")
        else True
    )


async def test_a_version_of_the_history_can_be_chosen_and_time_moved(
    client: Any, biz: Biz, fake_redis: Any, scripted: InMemoryProvider
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    missing = await client.post(_url(biz, agent_id), json={"version": 99}, headers=biz.headers())
    assert missing.status_code == 404
    session = (
        await client.post(_url(biz, agent_id), json={"version": 1}, headers=biz.headers())
    ).json()
    assert session["version_number"] == 1
    later = datetime(2031, 3, 3, 9, 15, tzinfo=MADRID)
    moved = await client.patch(
        f"{_url(biz, agent_id)}/{session['session_id']}",
        json={"now": later.isoformat()},
        headers=biz.headers(),
    )
    assert moved.status_code == 200
    assert datetime.fromisoformat(moved.json()["now"]) == later


async def test_owner_admin_and_builder_send_and_the_analyst_only_reads(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, scripted: InMemoryProvider
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    builder = await add_console_member(db_session, partner_id=biz.partner_id, role="builder")
    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    opened = await client.post(_url(biz, agent_id), json={}, headers=builder["headers"]())
    assert opened.status_code == 201
    assert opened.json()["allowed"] == ["send", "set_time", "close"]
    sid = opened.json()["session_id"]
    denied = await client.post(_url(biz, agent_id), json={}, headers=analyst["headers"]())
    assert denied.status_code == 403
    _script(scripted, [], "Hola, ¿en qué te ayudo?")
    await client.post(
        f"{_url(biz, agent_id)}/{sid}/messages", json={"text": "Hola"}, headers=builder["headers"]()
    )
    seen = await client.get(f"{_url(biz, agent_id)}/{sid}", headers=analyst["headers"]())
    assert seen.status_code == 200
    assert seen.json()["allowed"] == []
    assert [t["role"] for t in seen.json()["transcript"]] == ["customer", "agent"]
    cant_send = await client.post(
        f"{_url(biz, agent_id)}/{sid}/messages", json={"text": "x"}, headers=analyst["headers"]()
    )
    assert cant_send.status_code == 403


async def test_it_is_metered_in_build_and_closing_leaves_nothing(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, scripted: InMemoryProvider
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    session = (await client.post(_url(biz, agent_id), json={}, headers=biz.headers())).json()
    _script(scripted, [], "Hola.")
    await client.post(
        f"{_url(biz, agent_id)}/{session['session_id']}/messages",
        json={"text": "Hola"},
        headers=biz.headers(),
    )
    entries = [e[1] for e in await fake_redis.xrange("nexus:usage") if e[1].get("source") == "qa"]
    assert entries, "el playground no publicó su consumo"
    assert entries[-1]["turn_id"].startswith(f"playground:{session['session_id']}")
    from nexus_api.db.models.usage_record import USAGE_LINE_BY_SOURCE

    assert USAGE_LINE_BY_SOURCE["qa"] == "build"
    closed = await client.delete(
        f"{_url(biz, agent_id)}/{session['session_id']}", headers=biz.headers()
    )
    assert closed.status_code == 204
    from nexus_api.db.models import Customer

    async with tenant_scoped_session(db_session, biz.tenant_id):
        left = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Conversation)
            .join(Customer, Customer.id == Conversation.customer_id)
            .where(Customer.identifier.like("sim::%"))
        )
    assert left == 0
    gone = await client.get(f"{_url(biz, agent_id)}/{session['session_id']}", headers=biz.headers())
    assert gone.status_code == 404
