"""Garantía 4 — el estado del hilo vive en el checkpoint de su cliente
(spec 047, T016 · requisitos 56.4, 40.3 y 53.8).

La 047 mete estado nuevo en el hilo: la afinidad de modelo (``pinned_model``,
requisito 40.3) y, con Recepción, el estado de cada agente dentro del mismo
hilo (53.8). La garantía no cambia —el hilo es del cliente y otro cliente no lo
lee—, pero ahora la prueban el saver de verdad (``TenantScopedPostgresSaver``,
contra Postgres) y un **barrido de las claves del estado**: cada clave de
``AgentState`` se escribe en el checkpoint de un cliente y se comprueba que
vuelve entera a su hilo y que ni el hilo del vecino, ni una sesión con su GUC,
ni una sin GUC, la ven. Cuando ``pinned_model`` o el estado por agente entren en
``AgentState``, el barrido las cubre el mismo día, sin tocar este archivo.

``test_18``/``test_19`` prueban el trigger y la RLS de las tablas con SQL a
mano; ``test_4_*`` el formato del hilo con ``MemorySaver``. Esto junta las dos
cosas en el camino real.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from langgraph.checkpoint.base import empty_checkpoint
from nexus_worker.runtime.checkpointer import postgres_checkpointer
from nexus_worker.runtime.state import AgentState, new_state
from nexus_worker.runtime.thread_id import make_thread_id

from nexus_api.config import get_settings
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
)

from .conftest import make_pipeline, seed_active_agent_config, seed_channel

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

SHARED_USER = "+56911223344"


@pytest_asyncio.fixture
async def saver() -> AsyncIterator[Any]:
    """El saver de producción, contra la base de tests: ``setup()`` crea las
    tablas de LangGraph si faltan y el endurecimiento de 0065/0066 les pone
    ``tenant_id``, el trigger y la RLS, como al arrancar el worker."""
    async with postgres_checkpointer(get_settings().database_url) as s:
        yield s


def _sample(annotation: str, marker: str) -> Any:
    """Un valor de la forma de la clave, con la marca dentro si cabe."""
    if annotation.startswith("bool"):
        return True
    if annotation.startswith("int"):
        return 7
    if annotation.startswith("float"):
        return 0.5
    if annotation.startswith("list"):
        return [{"marker": marker}]
    if annotation.startswith("dict"):
        return {"marker": marker}
    return marker


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


async def _visible(tenant: uuid.UUID | None, thread_id: str, marker: str) -> dict[str, int]:
    """Lo que ve de ese hilo una sesión con la postura del saver (``nexus_app``)
    y el GUC de ``tenant`` (o sin GUC)."""
    async with get_sessionmaker()() as session:
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": "" if tenant is None else str(tenant)},
        )
        await session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        out = {}
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            out[table] = await session.scalar(
                sa.text(f"SELECT count(*) FROM {table} WHERE thread_id = :t"), {"t": thread_id}
            )
        out["marker_anywhere"] = await session.scalar(
            sa.text(
                "SELECT count(*) FROM checkpoints WHERE checkpoint::text LIKE :m "
                "OR metadata::text LIKE :m"
            ),
            {"m": f"%{marker}%"},
        )
        await session.rollback()
    return out


async def test_every_state_key_lives_in_its_clients_checkpoint(saver) -> None:
    """El barrido: TODAS las claves de ``AgentState``, de una vez."""
    a, b = uuid.uuid4(), uuid.uuid4()
    channel = uuid.uuid4()
    marker = f"ESTADO-A-{uuid.uuid4().hex[:8]}"
    keys = dict(AgentState.__annotations__)
    assert {"tenant_id", "agent_id", "intent", "history"} <= keys.keys(), keys
    # ``from __future__ import annotations`` en ``state.py``: el TypedDict
    # guarda ``ForwardRef('list[...]')``; lo que importa es el texto del tipo.
    values = {
        k: _sample(getattr(ann, "__forward_arg__", str(ann)), f"{marker}-{k}")
        for k, ann in keys.items()
    }
    # Hay claves que van en línea (texto) y claves que van a ``checkpoint_blobs``
    # (listas y diccionarios): el barrido pasa por las dos tablas.
    assert any(isinstance(v, list | dict) for v in values.values())

    thread_a = make_thread_id(a, channel, SHARED_USER)
    thread_b = make_thread_id(b, channel, SHARED_USER)  # mismo número, otro cliente
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = values
    checkpoint["channel_versions"] = {k: "00000000000000000000000000000001.0" for k in values}
    await saver.aput(
        _config(thread_a),
        checkpoint,
        {"source": "input", "step": 0},
        {k: "00000000000000000000000000000001.0" for k in values},
    )

    stored = await saver.aget_tuple(_config(thread_a))
    assert stored is not None
    back = stored.checkpoint["channel_values"]
    missing = sorted(k for k in values if back.get(k) != values[k])
    assert not missing, f"claves del estado que no vuelven a su hilo: {missing}"

    # El hilo del vecino —mismo canal, mismo número— no existe.
    assert await saver.aget_tuple(_config(thread_b)) is None
    assert [c async for c in saver.alist(_config(thread_b))] == []
    # Sin hilo no hay listado global.
    with pytest.raises(ValueError, match="sin prefijo"):
        await saver.aget_tuple({"configurable": {"thread_id": "global"}})

    # Lo mismo en SQL, con la postura del saver: el GUC de A lo ve; el de B y
    # ninguno, no; y la marca no aparece en nada que B pueda leer.
    as_a = await _visible(a, thread_a, marker)
    assert as_a["checkpoints"] == 1 and as_a["checkpoint_blobs"] >= 1, as_a
    for who in (b, None):
        seen = await _visible(who, thread_a, marker)
        assert seen == {
            "checkpoints": 0,
            "checkpoint_blobs": 0,
            "checkpoint_writes": 0,
            "marker_anywhere": 0,
        }, (who, seen)


async def test_a_real_turn_leaves_its_state_only_in_its_clients_thread(
    db_session, tenants_ab, agent_loader, in_memory_provider, llm_router, saver
) -> None:
    """Un turno de verdad con el saver de verdad: el estado queda en el hilo del
    cliente, con su ``tenant_id`` y su agente; el mismo número en el otro
    cliente no lo ve."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    cfg = await seed_active_agent_config(db_session, tenant_id=a, system_prompt="A", tools=[])
    await seed_active_agent_config(db_session, tenant_id=b, system_prompt="B", tools=[])
    ch_a = await seed_channel(db_session, tenant_id=a, provider_identifier="iso47-a")
    in_memory_provider.responder = lambda c: "info" if c.role == "classify" else "vale"

    cust = Customer(tenant_id=a, identifier=SHARED_USER, preferences={})
    db_session.add(cust)
    await db_session.commit()
    conv = Conversation(
        tenant_id=a, channel_id=ch_a.id, customer_id=cust.id, status=ConversationStatus.OPEN
    )
    db_session.add(conv)
    await db_session.commit()
    inbound = Message(
        tenant_id=a,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND,
        content="SECRETO-DEL-TURNO-A",
        tool_calls=[],
    )
    db_session.add(inbound)
    await db_session.commit()

    state = new_state(
        tenant_id=a,
        channel_id=ch_a.id,
        user_id=SHARED_USER,
        conversation_id=conv.id,
        customer_id=cust.id,
        inbound_message_id=inbound.id,
        user_message="SECRETO-DEL-TURNO-A",
    )
    state["agent_id"] = str(cfg.agent_id)
    thread_a = make_thread_id(a, ch_a.id, SHARED_USER)
    pipeline = make_pipeline(agent_loader=agent_loader, llm_router=llm_router, checkpointer=saver)
    await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_a}})

    stored = await saver.aget_tuple(_config(thread_a))
    assert stored is not None
    values = stored.checkpoint["channel_values"]
    assert values["tenant_id"] == str(a)
    assert values["agent_id"] == str(cfg.agent_id)
    assert values["user_message"] == "SECRETO-DEL-TURNO-A"

    thread_b = make_thread_id(b, ch_a.id, SHARED_USER)
    assert await saver.aget_tuple(_config(thread_b)) is None
    seen_by_b = await _visible(b, thread_a, "SECRETO-DEL-TURNO-A")
    assert seen_by_b["checkpoints"] == seen_by_b["marker_anywhere"] == 0, seen_by_b


# ── T140: la afinidad del router (requisito 40.3) ──────────────────────────


def test_the_router_state_is_in_the_sweep() -> None:
    """``pinned_model`` (la afinidad, por agente) y ``router_escalations`` (los
    escalados de la última hora) son claves de ``AgentState``: el barrido de
    arriba las escribe y las busca en el hilo del vecino sin tocar nada más."""
    keys = AgentState.__annotations__.keys()
    assert {"pinned_model", "router_escalations"} <= keys, sorted(keys)


async def test_the_pin_round_trips_in_its_clients_thread_only(saver) -> None:
    """La afinidad que escribe el router vuelve entera al hilo de su cliente, por
    agente, y el mismo número en otro cliente no la ve: ni el saver ni el SQL."""
    from nexus_worker.runtime.model_resolver import (
        PinnedModel,
        pins_from_state,
        record_escalation,
        with_pin,
    )

    a, b = uuid.uuid4(), uuid.uuid4()
    channel = uuid.uuid4()
    agent, sibling = uuid.uuid4(), uuid.uuid4()
    marker = f"despliegue-a-{uuid.uuid4().hex[:8]}"
    pin = PinnedModel(deployment=marker, agent_version="v7", pinned_at=1_000.0, expires_at=4_600.0)
    other = PinnedModel(
        deployment=f"{marker}-hermano", agent_version="v2", pinned_at=1_000.0, expires_at=4_600.0
    )
    pins = with_pin(with_pin({}, agent, pin), sibling, other)
    values = {
        "tenant_id": str(a),
        "pinned_model": pins,
        "router_escalations": record_escalation([], now=1_000.0),
    }
    thread_a = make_thread_id(a, channel, SHARED_USER)
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = values
    checkpoint["channel_versions"] = {k: "00000000000000000000000000000001.0" for k in values}
    await saver.aput(
        _config(thread_a),
        checkpoint,
        {"source": "input", "step": 0},
        {k: "00000000000000000000000000000001.0" for k in values},
    )

    stored = await saver.aget_tuple(_config(thread_a))
    assert stored is not None
    back = pins_from_state(stored.checkpoint["channel_values"])
    assert back == {str(agent): pin, str(sibling): other}, "cada agente con su afinidad"
    assert stored.checkpoint["channel_values"]["router_escalations"] == [1_000.0]

    assert await saver.aget_tuple(_config(make_thread_id(b, channel, SHARED_USER))) is None
    for who in (b, None):
        seen = await _visible(who, thread_a, marker)
        assert seen["checkpoints"] == seen["checkpoint_blobs"] == seen["marker_anywhere"] == 0


# ── C3: la afinidad que escribe un turno enrutado de verdad (T140) ─────────

ROUTED_KEY = "c3i-eu/answer-model"


async def _servable_answer_model(
    tenant_id: uuid.UUID, agent_id: uuid.UUID, cfg_id: uuid.UUID
) -> None:
    """Un despliegue que pasa el filtro duro y la batería de ``answer`` y de
    ``classify``, y está certificado **para ese agente** de ese cliente (42.3)."""
    import json

    from nexus_api.core.tenant_context import tenant_scoped_session

    caps = {"tools": True, "context_window": 200000, "strict_structured_outputs": True}
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                """
                INSERT INTO model_profiles (
                    provider, model_id, display_name, route, family, residency, zero_retention,
                    retention_how, contract_dpa, subprocessor_listed, status, capabilities,
                    supports_tools, max_context, price_input_per_mtok, price_output_per_mtok,
                    quota_weight_input, quota_weight_cache_read, quota_weight_output
                ) VALUES (
                    'c3i', :k, :k, :k, 'acme', 'eu', true, 'store=false', true, true, 'active',
                    CAST(:caps AS jsonb), true, 200000, 1, 5, 0.2, 0.02, 1
                )
                """
            ),
            {"k": ROUTED_KEY, "caps": json.dumps(caps)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_prices (deployment_id, valid_from, input, output, source_url) "
                "SELECT id, DATE '2026-10-01', 1, 5, 'https://example.invalid' "
                "FROM model_profiles WHERE model_id = :k"
            ),
            {"k": ROUTED_KEY},
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed) "
                "SELECT id, t, 1, '{}'::jsonb, 0.96, true FROM model_profiles, "
                "unnest(ARRAY['answer', 'classify']) AS t WHERE model_id = :k"
            ),
            {"k": ROUTED_KEY},
        )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.text(
                "INSERT INTO agent_model_certifications (tenant_id, agent_id, deployment_id, "
                "agent_config_id, suite_revision, result, passed, paid_by) "
                "SELECT :t, :a, id, :v, 1, '{}'::jsonb, true, 'auphere' "
                "FROM model_profiles WHERE model_id = :k"
            ),
            {"t": tenant_id, "a": agent_id, "v": cfg_id, "k": ROUTED_KEY},
        )


async def test_a_routed_turn_pins_its_model_only_in_its_clients_thread(
    db_session, tenants_ab, agent_loader, in_memory_provider, llm_router, saver
) -> None:
    """Un agente en «Automático» responde con el despliegue que elige el router y
    la afinidad (``pinned_model``) queda en el checkpoint de **su** hilo, por
    agente; el mismo número en otro cliente no la ve, ni el saver ni el SQL."""
    from nexus_worker.runtime import model_resolver

    a, b = tenants_ab["a"], tenants_ab["b"]
    cfg = await seed_active_agent_config(
        db_session,
        tenant_id=a,
        system_prompt="A",
        tools=[],
        policies={"model_policy": {"kind": "profile", "profile": "auto"}},
    )
    await seed_active_agent_config(db_session, tenant_id=b, system_prompt="B", tools=[])
    ch_a = await seed_channel(db_session, tenant_id=a, provider_identifier="iso47-routed")
    await _servable_answer_model(a, cfg.agent_id, cfg.id)
    model_resolver.invalidate_catalog()
    in_memory_provider.responder = lambda c: "vale"
    try:
        cust = Customer(tenant_id=a, identifier=SHARED_USER, preferences={})
        db_session.add(cust)
        await db_session.commit()
        conv = Conversation(
            tenant_id=a, channel_id=ch_a.id, customer_id=cust.id, status=ConversationStatus.OPEN
        )
        db_session.add(conv)
        await db_session.commit()
        state = new_state(
            tenant_id=a,
            channel_id=ch_a.id,
            user_id=SHARED_USER,
            conversation_id=conv.id,
            customer_id=cust.id,
            inbound_message_id=uuid.uuid4(),
            user_message="hola",
        )
        state["agent_id"] = str(cfg.agent_id)
        thread_a = make_thread_id(a, ch_a.id, SHARED_USER)
        pipeline = make_pipeline(
            agent_loader=agent_loader, llm_router=llm_router, checkpointer=saver
        )
        await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_a}})

        answered = [c for c in in_memory_provider.calls if c.extra.get("task") == "answer"]
        assert [c.model for c in answered] == [ROUTED_KEY]
        stored = await saver.aget_tuple(_config(thread_a))
        assert stored is not None
        pins = stored.checkpoint["channel_values"]["pinned_model"]
        assert pins[str(cfg.agent_id)]["deployment"] == ROUTED_KEY
        assert pins[str(cfg.agent_id)]["agent_version"] == str(cfg.id)

        assert await saver.aget_tuple(_config(make_thread_id(b, ch_a.id, SHARED_USER))) is None
        for who in (b, None):
            seen = await _visible(who, thread_a, ROUTED_KEY)
            assert seen["checkpoints"] == seen["checkpoint_blobs"] == seen["marker_anywhere"] == 0
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(
                sa.text("DELETE FROM model_profiles WHERE model_id = :k"), {"k": ROUTED_KEY}
            )
        model_resolver.invalidate_catalog()
        # Leer el catálogo también instala la lista del hop: la fila de prueba no
        # puede quedarse en ella para las pruebas que vienen detrás (test_50).
        from nexus_api.core import respond_catalog

        respond_catalog.reset()
