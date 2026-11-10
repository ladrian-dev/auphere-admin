"""Recepción que deriva — spec 047, T177 (historia 33; requisitos 53.1 a 53.8).

Un número con Recepción y sus destinos. El despachador es el de verdad y la
herramienta ``reception.handoff`` también, contra la base de verdad; lo único de
mentira es el grafo (``Turns``), que en el turno de un agente con plan llama a la
herramienta como lo haría el modelo, y en los demás contesta.

- **Marcar**: «Recepción», con sus destinos y cuándo derivar a cada uno; el
  borrador gana la herramienta, y nunca hacia un agente de otro cliente.
- **Derivar**: el mismo número y el mismo hilo; responde el destino, en el mismo
  turno y desde entonces, con lo suyo; la Bandeja dice «La atiende…».
- **Límites**: solo a los agentes de su lista y de su cliente; el resumen sí, lo
  propio de Recepción no; a la tercera ida y vuelta, una persona; con el destino
  en pausa o archivado, no deriva.
- **El gasto** cuenta en quien responde, y **el estado** de cada agente va por
  separado dentro de la clave del hilo de hoy.
- **Hasta cuándo**: resolver la conversación, 24 h sin mensajes o archivar el
  destino la devuelven a Recepción.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_mcp import build_default_registry
from nexus_worker.metering import collector
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound
from nexus_worker.runtime.model_resolver import PinnedModel, pinned_for, with_pin
from nexus_worker.runtime.pipeline import _build_handler_messages
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AgentStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Tenant,
    TenantPlan,
    TenantStatus,
    ToolCatalog,
)
from nexus_api.services import inbox_lifecycle, inbox_view, reception
from nexus_api.services.agent_spec.legacy import LEGACY_DEPLOYMENT

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

HANDOFF = "reception.handoff"
CUSTOMER = "+34600333444"
WHOLESALE = "Cuando pidan precios de mayorista o cajas para su tienda."
SUMMARY = "Quiere comprar al por mayor para su tienda."


# ── el mundo ────────────────────────────────────────────────────────────────


def _spec(name: str, prompt: str, targets: list[tuple[uuid.UUID, str]] | None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {"name": name, "description": f"{name} de la Barbería Cultor, por WhatsApp."},
        "instructions": {"legacy_text": prompt},
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "pinned", "deployment": LEGACY_DEPLOYMENT},
        "memory": {"scope": "shared"},
    }
    if targets is not None:
        doc["reception"] = {
            "enabled": True,
            "targets": [{"agent_id": str(a), "when": when} for a, when in targets],
        }
    return doc


@dataclass
class World:
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    reception: uuid.UUID
    ventas: uuid.UUID
    cobranza: uuid.UUID
    configs: dict[uuid.UUID, uuid.UUID]

    def event(self, content: str, *, user: str = CUSTOMER) -> InboundEvent:
        return InboundEvent(
            tenant_id=self.tenant_id,
            channel_id=self.channel_id,
            user_id=user,
            content=content,
            provider_message_id=f"wamid.{uuid.uuid4().hex}",
        )


PROMPTS = {
    "Recepción": "Eres la recepción de la barbería: saludas y orientas.",
    "Ventas mayoristas": "Eres Ventas mayoristas: tarifas por caja y pedidos grandes.",
    "Cobranza": "Eres Cobranza: recuerdas pagos pendientes.",
}


async def _world(
    db_session: AsyncSession,
    *,
    with_cobranza_in_list: bool = False,
    ventas_back_to_reception: bool = False,
) -> World:
    """Recepción en el número, con Ventas mayoristas en su lista (y Cobranza
    fuera, salvo que se pida). Todos publicados."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Barbería Cultor",
            slug=f"cultor-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        ids = {name: uuid.uuid4() for name in PROMPTS}
        for name, agent_id in ids.items():
            s.add(Agent(id=agent_id, tenant_id=tenant_id, name=name, lifecycle="published"))
        await s.flush()
        r, v, c = ids["Recepción"], ids["Ventas mayoristas"], ids["Cobranza"]
        targets = [(v, WHOLESALE)] + (
            [(c, "Cuando pregunten por un pago.")] if with_cobranza_in_list else []
        )
        specs = {
            r: _spec("Recepción", PROMPTS["Recepción"], targets),
            v: _spec(
                "Ventas mayoristas",
                PROMPTS["Ventas mayoristas"],
                [(r, "Cuando no sea una compra al por mayor.")]
                if ventas_back_to_reception
                else None,
            ),
            c: _spec("Cobranza", PROMPTS["Cobranza"], None),
        }
        configs: dict[uuid.UUID, uuid.UUID] = {}
        for version, (name, agent_id) in enumerate(ids.items(), start=1):
            receives = specs[agent_id].get("reception") is not None
            cfg = AgentConfig(
                tenant_id=tenant_id,
                agent_id=agent_id,
                version=version,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=PROMPTS[name],
                tools=[HANDOFF] if receives else [],
                channels=[],
                policies={},
                spec=specs[agent_id],
                created_by="test",
            )
            s.add(cfg)
            await s.flush()
            configs[agent_id] = cfg.id
        channel = Channel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3460{uuid.uuid4().int % 10**7:07d}",
            config={"phone_number_id": "PN"},
            status=ChannelStatus.ACTIVE,
            agent_id=r,
        )
        s.add(channel)
        await s.commit()
    return World(tenant_id, channel.id, r, v, c, configs)


async def _conversation(w: World) -> Conversation:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w.tenant_id):
        conv = await s.scalar(
            sa.select(Conversation).where(Conversation.channel_id == w.channel_id)
        )
        assert conv is not None
        s.expunge(conv)
        return conv


async def _set(w: World, model: Any, row_id: uuid.UUID, **values: Any) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w.tenant_id):
        await s.execute(sa.update(model).where(model.id == row_id).values(**values))


async def _handoff(
    tenant_id: uuid.UUID, customer_id: uuid.UUID | str, to: uuid.UUID, summary: str = SUMMARY
) -> dict[str, Any]:
    """Lo que hace el modelo de Recepción: llamar a la herramienta del registro."""
    registry = build_default_registry()
    with tenant_context(tenant_id), customer_context(uuid.UUID(str(customer_id))):
        envelope: dict[str, Any] = await registry.dispatch(
            HANDOFF, {"to_agent_id": str(to), "summary": summary}, whitelist=[HANDOFF]
        )
    return envelope


class Turns:
    """El grafo de mentira. Apunta cada estado, el hilo y el buffer de consumo
    del turno; un agente con plan deriva (una vez por plan) y los demás contestan."""

    def __init__(self, plans: dict[uuid.UUID, list[uuid.UUID]] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.envelopes: list[dict[str, Any]] = []
        self.plans = {agent: list(to) for agent, to in (plans or {}).items()}

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        scope = collector._scope.get()
        self.calls.append(
            {
                **state,
                "thread_id": (config or {})["configurable"]["thread_id"],
                "usage": (scope.agent_id, scope.turn_id, scope.agent_config_id) if scope else None,
            }
        )
        agent = uuid.UUID(state["agent_id"])
        plan = self.plans.get(agent)
        if plan:
            envelope = await _handoff(
                uuid.UUID(state["tenant_id"]), state["customer_id"], plan.pop(0)
            )
            self.envelopes.append(envelope)
            return {"intent": "info", "response": "", "tool_calls": [envelope]}
        return {"intent": "info", "response": "ok", "tool_calls": []}

    def agents(self) -> list[str]:
        return [c["agent_id"] for c in self.calls]


# ── marcar ──────────────────────────────────────────────────────────────────


async def test_marking_reception_puts_the_tool_on_the_draft_and_never_another_clients_agent(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    from ..business._business_world import new_business, seed_agent

    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    other = await new_business(client, db_session, console_world, name="Floristería Lirio")
    front, _ = await seed_agent(db_session, biz.tenant_id, name="Recepción", prompt="Hola.")
    sales, _ = await seed_agent(db_session, biz.tenant_id, name="Ventas", prompt="Vendes.")
    foreign, _ = await seed_agent(db_session, other.tenant_id, name="Ventas", prompt="Vendes.")
    await db_session.commit()
    url = f"/console/clients/{biz.ref}/agents/{front}/draft"

    async def patch(reception_section: dict[str, Any] | None, expect: int = 200) -> Any:
        draft = (await client.get(url, headers=biz.headers())).json()
        spec = dict(draft["spec"])
        spec.pop("reception", None)
        if reception_section is not None:
            spec["reception"] = reception_section
        resp = await client.patch(
            url,
            json={"spec": spec},
            headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
        )
        assert resp.status_code == expect, resp.text
        return resp.json()

    on = {"enabled": True, "targets": [{"agent_id": str(sales), "when": WHOLESALE}]}
    body = await patch(on)
    assert HANDOFF in body["tools"], "Recepción gana la herramienta de derivar"
    assert body["spec"]["reception"]["targets"][0]["when"] == WHOLESALE

    refused = await patch(
        {"enabled": True, "targets": [{"agent_id": str(foreign), "when": WHOLESALE}]}, expect=422
    )
    assert [p["code"] for p in refused["detail"]["problems"]] == ["foreign_reference"]

    body = await patch({"enabled": False, "targets": []})
    assert HANDOFF not in body["tools"], "sin Recepción no hay derivación"


async def test_publishing_says_which_agent_is_reception(db_session: AsyncSession) -> None:
    w = await _world(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w.tenant_id):
        for agent_id in (w.reception, w.ventas):
            await reception.sync_reception_flag(s, agent_id)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w.tenant_id):
        flags = dict((await s.execute(sa.select(Agent.id, Agent.is_reception))).tuples().all())
    assert flags[w.reception] is True
    assert flags[w.ventas] is False


async def test_the_card_and_the_header_say_which_agent_is_reception(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """La tarjeta y la cabecera del agente dicen lo que dice la versión
    publicada: así la consola marca «Recepción» sin abrir cada borrador."""
    from ..business._business_world import new_business, seed_agent

    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    front, _ = await seed_agent(db_session, biz.tenant_id, name="Recepción", prompt="Hola.")
    sales, _ = await seed_agent(db_session, biz.tenant_id, name="Ventas", prompt="Vendes.")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(Agent).where(Agent.id == front).values(is_reception=True)
        )
    await db_session.commit()

    cards = await client.get(f"/console/clients/{biz.ref}/agents", headers=biz.headers())
    assert cards.status_code == 200, cards.text
    flags = {c["id"]: c["is_reception"] for c in cards.json()}
    assert (flags[str(front)], flags[str(sales)]) == (True, False)
    for agent_id, expected in ((front, True), (sales, False)):
        head = await client.get(
            f"/console/clients/{biz.ref}/agents/{agent_id}", headers=biz.headers()
        )
        assert head.status_code == 200, head.text
        assert head.json()["is_reception"] is expected


# ── derivar ─────────────────────────────────────────────────────────────────


async def test_the_target_answers_on_the_same_number_and_the_same_thread(
    db_session: AsyncSession,
) -> None:
    w = await _world(db_session)
    turns = Turns({w.reception: [w.ventas]})

    with capture_logs() as logs:
        await process_inbound(w.event("quiero comprar al por mayor"), pipeline=turns)

    assert turns.envelopes[0]["status"] == "ok"
    assert turns.envelopes[0]["result"]["handed_off"] is True
    assert turns.envelopes[0]["result"]["to_agent"] == "Ventas mayoristas"
    # En el mismo turno contesta el destino, en el mismo número y el mismo hilo.
    assert turns.agents() == [str(w.reception), str(w.ventas)]
    first, second = turns.calls
    assert first["conversation_id"] == second["conversation_id"]
    assert first["channel_id"] == second["channel_id"] == str(w.channel_id)
    assert first["thread_id"] == second["thread_id"]
    assert first["user_message"] == second["user_message"] == "quiero comprar al por mayor"

    conv = await _conversation(w)
    assert conv.handled_by_agent_id == w.ventas
    assert conv.reception_hops == 1

    handoffs = [e for e in logs if e["event"] == "reception.handoff"]
    assert len(handoffs) == 1
    assert {k: v for k, v in handoffs[0].items() if k not in {"event", "log_level"}} == {
        "tenant_id": str(w.tenant_id),
        "agent_id": str(w.reception),
        "conversation_id": str(conv.id),
        "from_agent_id": str(w.reception),
        "to_agent_id": str(w.ventas),
        "hop": 1,
    }

    # Desde ese turno responde el destino: el siguiente mensaje va directo.
    again = Turns()
    await process_inbound(w.event("¿cuánto cuesta la caja de 12?"), pipeline=again)
    assert again.agents() == [str(w.ventas)]

    # La Bandeja dice «La atiende Ventas mayoristas».
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w.tenant_id):
        row = await s.get(Conversation, conv.id)
        assert row is not None
        detail = await inbox_view.detail(s, row, tenant_id=w.tenant_id, me="nadie")
        page = await inbox_view.list_conversations(
            s, tenant_id=w.tenant_id, me="nadie", flt="all", q=None, cursor=None, limit=10
        )
        items, _ = await inbox_view.thread(
            s, row, tenant_id=w.tenant_id, me="nadie", before=None, limit=50
        )
    assert detail.agent == (w.ventas, "Ventas mayoristas")
    assert detail.handled_by == (w.ventas, "Ventas mayoristas")
    assert [i.agent for i in page.items] == [(w.ventas, "Ventas mayoristas")]
    changed = [i for i in items if i.type == "event" and i.event_kind == "agent_changed"]
    assert [i.detail for i in changed] == ["Ventas mayoristas"]


# ── límites ─────────────────────────────────────────────────────────────────


async def test_only_to_the_agents_of_its_list_and_of_its_client(db_session: AsyncSession) -> None:
    w = await _world(db_session)
    other = await _world(db_session)
    await process_inbound(w.event("hola"), pipeline=Turns())
    conv = await _conversation(w)

    for to, outcome in (
        (w.cobranza, "not_in_list"),
        (other.ventas, "not_in_list"),  # otro cliente: igual que uno que no existe
        (uuid.uuid4(), "not_in_list"),
        (w.reception, "same_agent"),
    ):
        envelope = await _handoff(w.tenant_id, conv.customer_id, to)
        assert envelope["status"] == "ok", envelope
        assert envelope["result"]["handed_off"] is False
        assert envelope["result"]["outcome"] == outcome, (to, envelope)
        assert envelope["result"]["to_agent"] is None, "no dice ni el nombre de otro agente"

    # Un agente que no es Recepción no deriva, aunque se le cuele la herramienta.
    await _set(w, Conversation, conv.id, handled_by_agent_id=w.ventas)
    envelope = await _handoff(w.tenant_id, conv.customer_id, w.cobranza)
    assert envelope["result"]["outcome"] == "not_reception"

    after = await _conversation(w)
    assert after.handled_by_agent_id == w.ventas
    assert after.reception_hops == 0


async def test_the_summary_passes_and_receptions_own_knowledge_does_not(
    db_session: AsyncSession,
) -> None:
    w = await _world(db_session)
    turns = Turns({w.reception: [w.ventas]})
    await process_inbound(w.event("quiero comprar al por mayor"), pipeline=turns)

    target = turns.calls[1]
    assert SUMMARY in target["system_addendum"]
    assert "Recepción" in target["system_addendum"]
    assert PROMPTS["Recepción"] not in target["system_addendum"]
    assert WHOLESALE not in target["system_addendum"], "el «cuándo» es de Recepción"

    loader = AgentLoader()
    front = await loader.load(w.tenant_id, w.reception)
    sales = await loader.load(w.tenant_id, w.ventas)
    assert [(t.agent_id, t.name, t.when) for t in front.reception_targets] == [
        (w.ventas, "Ventas mayoristas", WHOLESALE)
    ]
    assert sales.reception_targets == ()
    assert sales.system_prompt == PROMPTS["Ventas mayoristas"]
    messages = _build_handler_messages(
        {**target, "history": []},  # type: ignore[typeddict-item]
        sales,
        intent="info",
        kg_snapshot="",
    )
    text = "\n".join(str(m["content"]) for m in messages)
    assert PROMPTS["Recepción"] not in text
    assert WHOLESALE not in text
    assert SUMMARY in text


async def test_the_third_round_trip_goes_to_a_person(db_session: AsyncSession) -> None:
    w = await _world(db_session, ventas_back_to_reception=True)
    await process_inbound(w.event("hola"), pipeline=Turns())
    customer = (await _conversation(w)).customer_id

    # Dos idas y vueltas: Recepción → Ventas → Recepción → Ventas → Recepción.
    for hop, to in enumerate((w.ventas, w.reception, w.ventas, w.reception), start=1):
        envelope = await _handoff(w.tenant_id, customer, to)
        assert envelope["result"]["handed_off"] is True, envelope
        assert envelope["result"]["hop"] == hop

    envelope = await _handoff(w.tenant_id, customer, w.ventas)
    assert envelope["result"]["handed_off"] is False
    assert envelope["result"]["outcome"] == "loop"

    conv = await _conversation(w)
    assert conv.reception_hops == 4
    assert conv.handled_by_agent_id is None, "sigue en Recepción, el agente del número"
    assert conv.waiting_reason == "reception_loop"
    assert conv.status == ConversationStatus.ESCALATED, "espera a una persona"


@pytest.mark.parametrize("lifecycle", ["paused", "archived"])
async def test_no_handoff_to_a_paused_or_archived_target(
    db_session: AsyncSession, lifecycle: str
) -> None:
    w = await _world(db_session, with_cobranza_in_list=True)
    values: dict[str, Any] = {"lifecycle": lifecycle}
    if lifecycle == "paused":
        values["pause_reason"] = "manual"
    else:
        values["status"] = AgentStatus.ARCHIVED.value
    await _set(w, Agent, w.ventas, **values)
    # Cobranza, en la lista pero sin versión publicada: tampoco.
    await _set(w, AgentConfig, w.configs[w.cobranza], status=AgentConfigStatus.ARCHIVED)

    turns = Turns({w.reception: [w.ventas]})
    await process_inbound(w.event("quiero comprar al por mayor"), pipeline=turns)
    assert turns.agents() == [str(w.reception)], "se queda la conversación"
    assert turns.envelopes[0]["result"]["outcome"] == "target_unavailable"

    customer = (await _conversation(w)).customer_id
    envelope = await _handoff(w.tenant_id, customer, w.cobranza)
    assert envelope["result"]["outcome"] == "target_unavailable"

    conv = await _conversation(w)
    assert conv.handled_by_agent_id is None
    assert conv.reception_hops == 0


# ── el gasto y el estado ────────────────────────────────────────────────────


async def test_the_spend_counts_on_whoever_answers(db_session: AsyncSession) -> None:
    w = await _world(db_session)
    turns = Turns({w.reception: [w.ventas]})
    await process_inbound(w.event("quiero comprar al por mayor"), pipeline=turns)

    (front_agent, front_turn, front_cfg), (sales_agent, sales_turn, sales_cfg) = (
        c["usage"] for c in turns.calls
    )
    assert (front_agent, front_cfg) == (w.reception, w.configs[w.reception])
    assert (sales_agent, sales_cfg) == (w.ventas, w.configs[w.ventas])
    # Dos partidas del mismo turno, con su propia clave: ninguna pisa a la otra
    # en ``usage_records`` ni en el débito (``channel:{turno}``).
    assert front_turn != sales_turn
    assert sales_turn.startswith(front_turn)

    again = Turns()
    await process_inbound(w.event("¿y el envío?"), pipeline=again)
    assert again.calls[0]["usage"][0] == w.ventas


async def test_each_agent_keeps_its_own_state_inside_todays_thread_key(
    db_session: AsyncSession,
) -> None:
    w = await _world(db_session)
    turns = Turns({w.reception: [w.ventas]})
    await process_inbound(w.event("quiero comprar al por mayor"), pipeline=turns)

    key = make_thread_id(w.tenant_id, w.channel_id, CUSTOMER)
    assert {c["thread_id"] for c in turns.calls} == {key}, "la clave del hilo no cambia"

    # Lo de cada agente (el modelo fijado y su versión) va por agente en el hilo.
    state: dict[str, Any] = {}
    for agent, deployment in ((w.reception, "anthropic/haiku"), (w.ventas, "openai/gpt")):
        pin = PinnedModel(
            deployment=deployment, agent_version=str(w.configs[agent]), pinned_at=0, expires_at=9
        )
        state["pinned_model"] = with_pin(state.get("pinned_model"), agent, pin)
    front, sales = pinned_for(state, w.reception), pinned_for(state, w.ventas)
    assert front is not None and sales is not None
    assert (front.deployment, front.agent_version) == (
        "anthropic/haiku",
        str(w.configs[w.reception]),
    )
    assert (sales.deployment, sales.agent_version) == ("openai/gpt", str(w.configs[w.ventas]))

    # Una derivación es del turno que la hizo: el siguiente empieza sin ella.
    fresh = new_state(
        tenant_id=w.tenant_id,
        channel_id=w.channel_id,
        user_id=CUSTOMER,
        conversation_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        inbound_message_id=uuid.uuid4(),
        user_message="hola",
    )
    assert fresh["reception_handoff"] == {}


# ── hasta cuándo ────────────────────────────────────────────────────────────


async def test_resolving_the_conversation_returns_it_to_reception(
    db_session: AsyncSession,
) -> None:
    w = await _world(db_session)
    await process_inbound(w.event("al por mayor"), pipeline=Turns({w.reception: [w.ventas]}))
    conv = await _conversation(w)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w.tenant_id):
        row = await s.get(Conversation, conv.id)
        assert row is not None
        await inbox_lifecycle.resolve(s, row, actor="client:marta")
    conv = await _conversation(w)
    assert (conv.handled_by_agent_id, conv.reception_hops) == (None, 0)

    turns = Turns()
    await process_inbound(w.event("otra cosa"), pipeline=turns)
    assert turns.agents() == [str(w.reception)]


async def test_a_quiet_conversation_returns_to_reception(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = await _world(db_session)
    await process_inbound(w.event("al por mayor"), pipeline=Turns({w.reception: [w.ventas]}))
    # Lo que se considera «sin mensajes» se acorta para no esperar 24 h.
    monkeypatch.setattr(reception, "HANDOFF_IDLE", timedelta(0))

    turns = Turns()
    await process_inbound(w.event("hola de nuevo"), pipeline=turns)
    assert turns.agents() == [str(w.reception)]
    conv = await _conversation(w)
    assert (conv.handled_by_agent_id, conv.reception_hops) == (None, 0)


async def test_an_archived_target_returns_the_conversation_to_reception(
    db_session: AsyncSession,
) -> None:
    w = await _world(db_session)
    await process_inbound(w.event("al por mayor"), pipeline=Turns({w.reception: [w.ventas]}))
    await _set(w, Agent, w.ventas, lifecycle="archived", status=AgentStatus.ARCHIVED.value)

    turns = Turns()
    await process_inbound(w.event("¿sigue ahí?"), pipeline=turns)
    assert turns.agents() == [str(w.reception)]


# ── el catálogo ─────────────────────────────────────────────────────────────


async def test_the_tool_is_in_the_catalog_with_the_registrys_schema(
    db_session: AsyncSession,
) -> None:
    from nexus_mcp.servers.reception import ReceptionHandoff

    from nexus_api.api.console.capability_names import CAPABILITY_NAMES

    row = await db_session.scalar(sa.select(ToolCatalog).where(ToolCatalog.name == HANDOFF))
    assert row is not None, "sin fila en el catálogo la herramienta no existe para nadie"
    assert row.mcp_server == "reception-server"
    assert list(row.side_effects) == ["mutates_db"]
    assert (row.read_only, row.destructive, row.requires_consent) == (False, False, False)
    assert row.connector_id is None
    assert row.input_schema == ReceptionHandoff.input_model.model_json_schema()
    assert row.output_schema == ReceptionHandoff.output_model.model_json_schema()
    assert HANDOFF in build_default_registry().names()
    assert ("tool", HANDOFF) in CAPABILITY_NAMES
