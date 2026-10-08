"""Spec 030 T020 — dos agentes de un mismo cliente (garantías 2, 4 y 5).

Un cliente puede tener varios agentes y cada número contesta con uno. Dentro
del cliente, los agentes son tan estancos como dos clientes en todo lo que es
**del agente** — y comparten lo que es **del cliente**:

- un turno en el número de «Ventas» lleva al modelo el prompt renderizado y
  la lista blanca de Ventas, y la versión que se carga es la suya
  (garantías 2 y 5);
- la caché del cargador guarda cada agente bajo su clave: cargar uno no
  devuelve el otro e invalidar uno no tira el otro;
- el hilo de LangGraph es por número (garantía 4): el mismo contacto en los
  dos números tiene dos hilos y ninguno ve los turnos del otro;
- el conocimiento es del cliente: no tiene dimensión de agente y los dos lo
  leen igual.

Cómo elige el despachador el agente del número (``channel.agent_id`` o el
principal) está en ``apps/worker/tests/unit/test_agent_by_channel.py``; aquí
el estado del turno lleva ``agent_id`` como lo deja el despachador.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.state import new_state
from nexus_worker.runtime.thread_id import make_thread_id

from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    KGNode,
    Message,
    MessageDirection,
)

from .conftest import (
    make_pipeline,
    seed_active_agent_config,
    seed_channel,
    set_tenant,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

PRINCIPAL_PROMPT = "Eres la recepción de la peluquería. MARCA-PRINCIPAL-7f3a."
SALES_PROMPT = "Eres el agente de ventas de bonos. MARCA-VENTAS-91c2."
PRINCIPAL_TOOLS = ["client.get_preferences"]
SALES_TOOLS = ["client.get_history"]
SHARED_CONTACT = "+34600111222"


async def _two_agents(db_session, tenant_id: uuid.UUID) -> dict[str, object]:
    """The principal (born with the first config, from the trigger) answers
    on one number; «Ventas», with its own live version, on another."""
    principal_cfg = await seed_active_agent_config(
        db_session, tenant_id=tenant_id, system_prompt=PRINCIPAL_PROMPT, tools=PRINCIPAL_TOOLS
    )
    sales = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name="Ventas")
    db_session.add(sales)
    await db_session.commit()
    sales_cfg = AgentConfig(
        tenant_id=tenant_id,
        agent_id=sales.id,
        version=2,
        status=AgentConfigStatus.ACTIVE,
        system_prompt_rendered=SALES_PROMPT,
        channels=[],
        tools=SALES_TOOLS,
        policies={},
        seed_template_ref=None,
    )
    db_session.add(sales_cfg)
    await db_session.commit()
    main_number = await seed_channel(
        db_session, tenant_id=tenant_id, provider_identifier=f"iso30-p-{uuid.uuid4().hex[:6]}"
    )
    sales_number = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"iso30-s-{uuid.uuid4().hex[:6]}",
        config={},
        status=ChannelStatus.ACTIVE,
        agent_id=sales.id,
    )
    db_session.add(sales_number)
    await db_session.commit()
    return {
        "principal": principal_cfg.agent_id,
        "principal_version": principal_cfg.version,
        "sales": sales.id,
        "main_number": main_number,
        "sales_number": sales_number,
    }


async def _turn(db_session, pipeline, *, tenant_id, channel, agent_id, text: str):
    # One person writing to both numbers is one customer of the client, with
    # one conversation per number.
    customer = await db_session.scalar(
        sa.select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.identifier == SHARED_CONTACT
        )
    )
    if customer is None:
        customer = Customer(tenant_id=tenant_id, identifier=SHARED_CONTACT, preferences={})
        db_session.add(customer)
        await db_session.commit()
    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=channel.id,
        customer_id=customer.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND,
        content=text,
        tool_calls=[],
    )
    db_session.add(inbound)
    await db_session.commit()
    await db_session.refresh(inbound)
    state = new_state(
        tenant_id=tenant_id,
        channel_id=channel.id,
        user_id=SHARED_CONTACT,
        conversation_id=conv.id,
        customer_id=conv.customer_id,
        inbound_message_id=inbound.id,
        user_message=text,
    )
    # What the dispatcher leaves on the state: the agent of this number.
    state["agent_id"] = str(agent_id)
    thread_id = make_thread_id(tenant_id, channel.id, SHARED_CONTACT)
    await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_id}})
    return thread_id


def _flat(call) -> str:
    return "\n".join(m["content"] for m in call.messages if isinstance(m.get("content"), str))


def _tool_names(call) -> set[str]:
    return {td.get("function", {}).get("name", "") for td in call.tools}


async def test_a_turn_on_the_sales_number_sees_only_sales(
    db_session, tenants_ab, agent_loader, in_memory_provider, llm_router, memory_saver
) -> None:
    tenant = tenants_ab["a"]
    world = await _two_agents(db_session, tenant)
    in_memory_provider.responder = lambda c: "info" if c.role == "classify" else "vale"
    pipeline = make_pipeline(
        agent_loader=agent_loader, llm_router=llm_router, checkpointer=memory_saver
    )

    await _turn(
        db_session,
        pipeline,
        tenant_id=tenant,
        channel=world["sales_number"],
        agent_id=world["sales"],
        text="¿cuánto cuesta el bono de diez cortes?",
    )

    answering = [c for c in in_memory_provider.calls if c.role == "info"]
    assert answering, "the info handler should have answered"
    for call in answering:
        text = _flat(call)
        assert "MARCA-VENTAS-91c2" in text
        assert "MARCA-PRINCIPAL-7f3a" not in text, "the principal's prompt reached Ventas' turn"
        leaked = _tool_names(call) - set(SALES_TOOLS) - {""}
        assert not {n for n in leaked if n in PRINCIPAL_TOOLS}, f"principal tools leaked: {leaked}"
        assert "client.get_preferences" not in _tool_names(call)

    bundle = await agent_loader.load(tenant, world["sales"])
    assert bundle.agent_id == world["sales"]
    assert bundle.version == 2
    assert bundle.tools == frozenset(SALES_TOOLS)


async def test_the_loader_cache_keeps_agents_apart(db_session, tenants_ab, agent_loader) -> None:
    tenant = tenants_ab["a"]
    world = await _two_agents(db_session, tenant)

    sales = await agent_loader.load(tenant, world["sales"])
    principal = await agent_loader.load(tenant, world["principal"])
    by_default = await agent_loader.load(tenant)

    assert sales.system_prompt == SALES_PROMPT
    assert principal.system_prompt == PRINCIPAL_PROMPT
    # No agent named → the principal, never whichever was cached last.
    assert by_default.system_prompt == PRINCIPAL_PROMPT
    assert by_default.version == world["principal_version"]

    # Publishing a new Ventas version invalidates Ventas only.
    await db_session.execute(
        sa.update(AgentConfig)
        .where(AgentConfig.agent_id == world["sales"])
        .values(system_prompt_rendered="Ventas, versión nueva. MARCA-VENTAS-v3.")
    )
    await db_session.commit()
    await agent_loader.invalidate(tenant, world["sales"])
    assert "MARCA-VENTAS-v3" in (await agent_loader.load(tenant, world["sales"])).system_prompt
    assert (await agent_loader.load(tenant, world["principal"])) is principal


async def test_each_number_has_its_own_thread(
    db_session, tenants_ab, agent_loader, in_memory_provider, llm_router, memory_saver
) -> None:
    tenant = tenants_ab["a"]
    world = await _two_agents(db_session, tenant)
    in_memory_provider.responder = lambda c: "info" if c.role == "classify" else "vale"
    pipeline = make_pipeline(
        agent_loader=agent_loader, llm_router=llm_router, checkpointer=memory_saver
    )

    main_thread = await _turn(
        db_session,
        pipeline,
        tenant_id=tenant,
        channel=world["main_number"],
        agent_id=world["principal"],
        text="quiero cita el martes SECRETO-CITA",
    )
    sales_thread = await _turn(
        db_session,
        pipeline,
        tenant_id=tenant,
        channel=world["sales_number"],
        agent_id=world["sales"],
        text="quiero un bono SECRETO-BONO",
    )
    assert main_thread != sales_thread

    def history(thread_id: str) -> str:
        snap = memory_saver.get({"configurable": {"thread_id": thread_id}})
        assert snap is not None, f"no checkpoint for {thread_id}"
        return repr(snap["channel_values"])

    assert "SECRETO-CITA" in history(main_thread)
    assert "SECRETO-BONO" not in history(main_thread)
    assert "SECRETO-BONO" in history(sales_thread)
    assert "SECRETO-CITA" not in history(sales_thread)

    # And the turn on the main number never saw Ventas' prompt.
    main_calls = [c for c in in_memory_provider.calls if "SECRETO-CITA" in _flat(c)]
    assert main_calls
    assert all("MARCA-VENTAS-91c2" not in _flat(c) for c in main_calls)


async def test_both_agents_read_the_same_client_knowledge(db_session, tenants_ab) -> None:
    """The knowledge graph belongs to the client: it has no agent dimension,
    so whatever agent answers reads the same nodes (and none of another
    client's)."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    assert "agent_id" not in KGNode.__table__.columns

    await _two_agents(db_session, a)
    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(KGNode(tenant_id=a, label="Service", properties={"name": "Bono 10"}))
    async with db_session.begin():
        await set_tenant(db_session, b)
        db_session.add(KGNode(tenant_id=b, label="Service", properties={"name": "Ajeno"}))

    async with db_session.begin():
        await set_tenant(db_session, a)
        names = {
            n.properties["name"]
            for n in (await db_session.execute(sa.select(KGNode).where(KGNode.label == "Service")))
            .scalars()
            .all()
        }
    assert names == {"Bono 10"}


async def test_an_agent_of_another_client_cannot_be_referenced(db_session, tenants_ab) -> None:
    """The database itself refuses a version or a number of client A that
    points at client B's agent — a single-column foreign key would not, and
    the admin takes ``agent_id`` from the query string."""
    from sqlalchemy.exc import IntegrityError

    a, b = tenants_ab["a"], tenants_ab["b"]
    await seed_active_agent_config(db_session, tenant_id=a, system_prompt="A", tools=[])
    foreign_cfg = await seed_active_agent_config(
        db_session, tenant_id=b, system_prompt="B", tools=[]
    )
    foreign_agent = foreign_cfg.agent_id

    db_session.add(
        AgentConfig(
            tenant_id=a,
            agent_id=foreign_agent,
            version=2,
            status=AgentConfigStatus.STAGED,
            system_prompt_rendered="hijack",
            channels=[],
            tools=[],
            policies={},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    db_session.add(
        Channel(
            tenant_id=a,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"iso30-x-{uuid.uuid4().hex[:6]}",
            config={},
            status=ChannelStatus.ACTIVE,
            agent_id=foreign_agent,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
