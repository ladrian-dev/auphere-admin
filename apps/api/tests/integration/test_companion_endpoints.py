"""El ciclo completo del Companion, extremo a extremo (CO-01).

Crear hilo → lanzar run → leer el stream → matar la conexión → reconectar
con ``since_seq`` → cero eventos perdidos, cero duplicados. Y el caso que
motivó todo el diseño: reiniciar la API a mitad de run y que el usuario vea
QUÉ pasó, no una pantalla en blanco.

El grafo real no se ejecuta (necesitaría claves y tardaría): se inyecta uno
compilado sobre ``InMemoryProvider``, así que el driver, el traductor, el
log de Redis, las filas de Postgres y la RLS sí corren de verdad.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.companion import build_companion_graph
from nexus_worker.runtime.llm import InMemoryProvider

from nexus_api.api.console import companion as companion_api
from nexus_api.config import get_settings
from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionMessage, CompanionRun

pytestmark = pytest.mark.asyncio

ANSWER = "Puedo ayudarte a ordenar el trabajo pero todavía no leo el estado real"


def _answer_and_meter(_call: Any) -> str:
    """Lo que hace el proveedor real dentro del grafo: responde **y** anota
    su consumo.

    ``InMemoryProvider`` no pasa por ``LiteLLMProvider._record_call``, que es
    el único punto de estrangulamiento donde se mide. Sin esta línea el test
    de medición pasaría en verde midiendo nada — que es exactamente el fallo
    que 0079 vino a cerrar en el playground.
    """
    from nexus_worker.metering import collector

    collector.record_llm_usage(
        model="anthropic/claude-sonnet-4-6",
        provider="anthropic",
        usage={"prompt_tokens": 1200, "completion_tokens": 340},
    )
    return ANSWER


@pytest_asyncio.fixture(autouse=True)
async def _companion_graph(monkeypatch) -> Any:
    """Un grafo real de LangGraph con proveedor en memoria."""
    provider = InMemoryProvider(responder=_answer_and_meter, thinking_text="pensando")
    graph = build_companion_graph(
        provider=provider,
        model="anthropic/claude-sonnet-4-6",
        checkpointer=MemorySaver(),
    )
    companion_api.set_graph_for_tests(graph)
    yield graph
    companion_api.reset_graph_cache_for_tests()


def _parse(wire: str) -> list[tuple[int, str, dict]]:
    out: list[tuple[int, str, dict]] = []
    for block in wire.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        seq, event, data = 0, "", {}
        for line in block.splitlines():
            if line.startswith("id: "):
                seq = int(line[4:])
            elif line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        out.append((seq, event, data))
    return out


async def _finished(run_id: uuid.UUID, principal_id: str, timeout: float = 5.0) -> CompanionRun:
    """Espera a que la fila del run se cierre. El POST devuelve 202 y el
    trabajo sigue por su cuenta: sin esperar aquí, el test correría contra
    una fila a medio escribir."""
    sm = get_sessionmaker()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, principal_id)
            run = await session.get(CompanionRun, run_id)
            if run is not None and run.status != "running":
                await session.refresh(run)
                return run
        await asyncio.sleep(0.05)
    raise AssertionError("el run no se cerró a tiempo")


async def _start(client, world, prompt: str = "hola") -> tuple[str, str]:
    created = await client.post(
        "/console/companion/threads", headers=world["headers"](), json={"title": "t"}
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]
    started = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=world["headers"](),
        json={"prompt": prompt},
    )
    assert started.status_code == 202, started.text
    return thread_id, started.json()["run_id"]


# ── el turno completo ──────────────────────────────────────────────────


async def test_a_turn_streams_text_cost_and_context(client, console_world):
    a = console_world["a"]
    _thread_id, run_id = await _start(client, a)
    await _finished(uuid.UUID(run_id), a["user_id"])

    resp = await client.get(f"/console/companion/runs/{run_id}/stream", headers=a["headers"]())
    assert resp.status_code == 200
    events = _parse(resp.text)
    names = [e for _s, e, _d in events]

    assert names[0] == "run.started"
    assert names[-1] == "run.completed"
    assert "text.delta" in names
    assert "reasoning.delta" in names

    text = "".join(d["text"] for _s, e, d in events if e == "text.delta")
    assert text == ANSWER

    cost = next(d for _s, e, d in events if e == "cost.updated")
    assert cost["input_tokens"] > 0 and cost["output_tokens"] > 0

    ctx = next(d for _s, e, d in events if e == "context.updated")
    # Ventana real del catálogo, nunca una estimación por caracteres.
    assert ctx["max_context"] > 10_000
    assert ctx["percent"] == pytest.approx(
        ctx["input_tokens"] * 100.0 / ctx["max_context"], rel=1e-3
    )

    budget = next(d for _s, e, d in events if e == "budget.updated")
    assert budget["cap"] > 0 and budget["used"] > 0


async def test_the_202_comes_back_before_the_work_is_done(client, console_world):
    """El punto entero de C1: la petición no espera al turno."""
    a = console_world["a"]
    _thread_id, run_id = await _start(client, a)
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        run = await session.get(CompanionRun, uuid.UUID(run_id))
        assert run is not None
    await _finished(uuid.UUID(run_id), a["user_id"])


async def test_the_thread_survives_a_refresh(client, console_world):
    """Después de un F5, el hilo se recompone: la pregunta y la respuesta
    están en Postgres, no en la memoria del navegador."""
    a = console_world["a"]
    thread_id, run_id = await _start(client, a, prompt="¿qué sabes hacer?")
    await _finished(uuid.UUID(run_id), a["user_id"])

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        rows = await companion_api._thread_history(session, uuid.UUID(thread_id))
    assert rows == [
        {"role": "user", "content": "¿qué sabes hacer?"},
        {"role": "assistant", "content": ANSWER},
    ]


# ── reconexión sin pérdida ─────────────────────────────────────────────


async def test_reconnecting_mid_run_loses_nothing_and_repeats_nothing(client, console_world):
    """El criterio de aceptación literal: matar la conexión a mitad de run
    y volver con ``since_seq``."""
    a = console_world["a"]
    _thread_id, run_id = await _start(client, a)
    await _finished(uuid.UUID(run_id), a["user_id"])

    first = await client.get(
        f"/console/companion/runs/{run_id}/events?since_seq=0&limit=3",
        headers=a["headers"](),
    )
    assert first.status_code == 200
    head = first.json()
    seen = [e["seq"] for e in head["events"]]
    assert len(seen) == 3
    assert head["available_from"] is None

    rest = await client.get(
        f"/console/companion/runs/{run_id}/events?since_seq={head['next_seq']}",
        headers=a["headers"](),
    )
    tail = [e["seq"] for e in rest.json()["events"]]
    assert not set(seen) & set(tail), "un evento entregado dos veces"
    assert seen + tail == list(range(1, len(seen) + len(tail) + 1)), "hay un hueco"
    assert rest.json()["events"][-1]["event"] == "run.completed"

    # Y el stream, desde el mismo punto, entrega exactamente lo mismo.
    streamed = await client.get(
        f"/console/companion/runs/{run_id}/stream?since_seq={head['next_seq']}",
        headers=a["headers"](),
    )
    assert [s for s, _e, _d in _parse(streamed.text)] == tail


async def test_the_events_endpoint_answers_only_its_own_events(client, console_world):
    """El historial es la transcripción del Companion — nunca la de un
    cliente final. El catálogo cerrado es lo que lo garantiza."""
    from nexus_api.api.companion_streaming import COMPANION_EVENTS

    a = console_world["a"]
    _thread_id, run_id = await _start(client, a)
    await _finished(uuid.UUID(run_id), a["user_id"])
    resp = await client.get(f"/console/companion/runs/{run_id}/events", headers=a["headers"]())
    for event in resp.json()["events"]:
        assert event["event"] in COMPANION_EVENTS, event["event"]
        assert set(event["data"]) <= COMPANION_EVENTS[event["event"]]


# ── reinicio de la API a mitad de run ──────────────────────────────────


async def test_a_run_orphaned_by_a_restart_is_closed_as_interrupted(client, console_world):
    """El reaper de arranque. Sin esto, el hilo se queda 'trabajando' para
    siempre y el cajón que reconecta espera eventos que nadie escribirá."""
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = uuid.UUID(created.json()["id"])

    # Un run que quedó abierto de un proceso que ya no existe.
    run_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        session.add(CompanionRun(id=run_id, thread_id=thread_id, principal_id=a["user_id"]))

    reaped = await companion_api.reap_stale_runs(older_than_seconds=0.0)
    assert reaped >= 1

    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        run = await session.get(CompanionRun, run_id)
        assert run is not None
        assert run.status == "interrupted"
        assert run.error and "reinici" in run.error.lower()

    # Y el stream lo dice en claro en vez de colgarse.
    resp = await client.get(f"/console/companion/runs/{run_id}/stream", headers=a["headers"]())
    events = _parse(resp.text)
    assert events[-1][1] == "run.completed"
    assert events[-1][2]["status"] == "interrupted"


async def test_the_reaper_leaves_a_fresh_run_of_another_replica_alone(client, console_world):
    """Un despliegue rodante NO puede matar los turnos vivos de la réplica
    que todavía no se ha apagado.

    El proceso que arranca no sabe qué runs son suyos, así que el corte es
    la duración máxima de un run: más viejo que eso está muerto lo ejecute
    quien lo ejecute; más nuevo, no se toca.
    """
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = uuid.UUID(created.json()["id"])
    run_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        session.add(CompanionRun(id=run_id, thread_id=thread_id, principal_id=a["user_id"]))

    await companion_api.reap_stale_runs()  # el corte real, no 0

    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        run = await session.get(CompanionRun, run_id)
        assert run is not None and run.status == "running"


async def test_an_expired_run_closes_the_stream_even_before_the_reaper(
    client, console_world, monkeypatch
):
    """El hueco que deja el corte conservador del reaper se cubre por el
    lado del lector: el usuario ve el cierre sin esperar a un reinicio."""
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = uuid.UUID(created.json()["id"])
    run_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        session.add(CompanionRun(id=run_id, thread_id=thread_id, principal_id=a["user_id"]))

    # Un log con un evento y nadie escribiendo: el proceso dueño murió.
    from nexus_api.api import companion_streaming as streaming
    from nexus_api.core.redis_client import get_redis

    await streaming.publish(
        get_redis(), run_id, seq=1, event="run.started", data={"run_id": str(run_id)}
    )

    # El run acaba de nacer pero su techo es cero: ya está caducado.
    from nexus_api.config import get_settings

    monkeypatch.setattr(get_settings(), "companion_run_max_seconds", 0.0)
    monkeypatch.setattr(streaming, "PING_INTERVAL_SECONDS", 0.05)

    resp = await client.get(f"/console/companion/runs/{run_id}/stream", headers=a["headers"]())
    events = _parse(resp.text)
    assert events[-1][1] == "run.completed"
    assert events[-1][2]["status"] == "interrupted"


# ── cancelación ────────────────────────────────────────────────────────


async def test_cancelling_is_an_explicit_call_not_a_closed_socket(client, console_world):
    a = console_world["a"]
    _thread_id, run_id = await _start(client, a)
    await _finished(uuid.UUID(run_id), a["user_id"])

    resp = await client.delete(f"/console/companion/runs/{run_id}", headers=a["headers"]())
    assert resp.status_code == 204
    # El run ya había terminado: cancelar es idempotente y no rompe nada.


# ── tope de gasto ──────────────────────────────────────────────────────


async def test_the_cap_is_the_companions_own_and_pauses_with_409(client, console_world, db_session):
    """Compartir tope con el playground haría que probar el agente y pedirle
    ayuda al Companion se robaran presupuesto entre sí.

    Desde CO-08 el tope **pausa en vez de matar** (§6.2 de CONTRACT-V2): el
    trabajo nuevo se rechaza con **409 ``budget_paused``** y no con 429. El
    cambio no es cosmético — 429 significa "vuelve a intentarlo", y aquí
    reintentar no sirve de nada: no pasa el tiempo, pasa que alguien sube el
    tope. Un ``Retry-After`` sería mentira.
    """
    import sqlalchemy as sa

    from nexus_api.db.models import Partner

    a = console_world["a"]
    await db_session.execute(
        sa.update(Partner)
        .where(Partner.id == a["partner_id"])
        .values(companion_monthly_token_cap=1)
    )
    await db_session.commit()

    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = created.json()["id"]

    # Primer turno: aún no hay consumo, pasa.
    first = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "hola"},
    )
    assert first.status_code == 202
    # Arranca (0 < 1) y cruza el tope al reportar su gasto: termina
    # ``paused``, no ``completed``. Es la pausa del §6.3, y conserva
    # historia, respuesta parcial y tokens.
    first_run = await _finished(uuid.UUID(first.json()["run_id"]), a["user_id"])
    assert first_run.status == "paused", first_run.status

    # Segundo: el tope de 1 token ya está pasado.
    second = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "otra"},
    )
    assert second.status_code == 409, second.text
    assert "Retry-After" not in second.headers
    detail = second.json()["detail"]
    assert detail["code"] == "budget_paused"
    # La instantánea del presupuesto viaja en el cuerpo para que la interfaz
    # pinte la explicación sin una segunda petición.
    assert set(detail) == {"code", "used", "cap", "period", "resets_at"}
    assert detail["used"] >= detail["cap"] == 1

    # El del playground sigue intacto: son dos presupuestos distintos.
    playground = await client.get("/console/playground/budget", headers=a["headers"]())
    assert playground.status_code == 200
    assert playground.json()["exhausted"] is False


async def test_the_budget_endpoint_counts_what_the_runs_spent(client, console_world):
    a = console_world["a"]
    before = await client.get("/console/companion/budget", headers=a["headers"]())
    assert before.status_code == 200
    assert before.json()["used"] == 0

    _thread_id, run_id = await _start(client, a)
    await _finished(uuid.UUID(run_id), a["user_id"])

    after = await client.get("/console/companion/budget", headers=a["headers"]())
    assert after.json()["used"] > 0
    assert after.json()["period"] == before.json()["period"]


async def test_the_spend_lands_in_usage_records_as_companion(client, console_world, fake_redis):
    """El gasto del Companion se mide **y se distingue**.

    Medirlo sin distinguirlo sería cambiar un agujero por una mentira: como
    ``qa``, competiría con el tope del playground; como ``channel``, se le
    facturaría al cliente final un gasto que no es suyo. Eso último no es
    un detalle de panel, es un error de facturación.
    """
    import sqlalchemy as sa
    from nexus_worker.metering import collector
    from nexus_worker.metering.consumer import drain_once

    from nexus_api.core.tenant_context import tenant_scoped_session

    a = console_world["a"]
    await fake_redis.delete(collector.USAGE_STREAM)

    created = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "t", "client_ref": a["ref"]},
    )
    assert created.status_code == 201
    started = await client.post(
        f"/console/companion/threads/{created.json()['id']}/runs",
        headers=a["headers"](),
        json={"prompt": "hola"},
    )
    run_id = started.json()["run_id"]
    await _finished(uuid.UUID(run_id), a["user_id"])

    await drain_once(fake_redis, consumer_name="test-companion")

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, a["tenant_id"]):
        rows = (
            await session.execute(
                sa.text(
                    "SELECT meter, source FROM usage_records WHERE tenant_id = :t ORDER BY meter"
                ),
                {"t": str(a["tenant_id"])},
            )
        ).all()
    assert rows, "el turno del Companion no dejó ninguna fila de consumo"
    assert {r.source for r in rows} == {"companion"}
    assert {r.meter for r in rows} == {"llm.input_tokens", "llm.output_tokens"}


# ── higiene del hilo ───────────────────────────────────────────────────


async def test_an_archived_thread_refuses_new_turns(client, console_world):
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = created.json()["id"]
    archived = await client.patch(
        f"/console/companion/threads/{thread_id}",
        headers=a["headers"](),
        json={"archived": True},
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    resp = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "hola"},
    )
    assert resp.status_code == 409


async def test_the_mode_switch_is_an_endpoint_not_a_model_decision(client, console_world):
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    assert created.json()["mode"] == "consult"
    patched = await client.patch(
        f"/console/companion/threads/{created.json()['id']}",
        headers=a["headers"](),
        json={"mode": "build"},
    )
    assert patched.status_code == 200
    assert patched.json()["mode"] == "build"


async def test_the_user_message_is_persisted_before_the_run_starts(client, console_world):
    """Si el turno reventara al primer token, la pregunta ya está en el
    hilo: el usuario no pierde lo que escribió."""
    a = console_world["a"]
    thread_id, run_id = await _start(client, a, prompt="una pregunta")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        import sqlalchemy as sa

        rows = (
            await session.execute(
                sa.select(CompanionMessage.role, CompanionMessage.content)
                .where(CompanionMessage.thread_id == uuid.UUID(thread_id))
                .order_by(CompanionMessage.seq)
            )
        ).all()
    assert rows[0] == ("user", "una pregunta")
    await _finished(uuid.UUID(run_id), a["user_id"])


# ── tope de turnos simultáneos por miembro ─────────────────────────────


async def _open_runs(thread_id: str, principal_id: str, count: int) -> None:
    """Deja ``count`` filas en ``running`` sin ejecutar nada. Es el estado
    en el que queda un miembro que lanzó varios turnos largos a la vez."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, principal_id)
        for _ in range(count):
            session.add(
                CompanionRun(
                    thread_id=uuid.UUID(thread_id),
                    principal_id=principal_id,
                    status="running",
                )
            )


async def test_a_member_cannot_keep_more_turns_running_than_the_cap(client, console_world):
    """El hueco que el límite por minuto no tapa: 15 arranques/min con un
    techo de 300 s permitían decenas de runs vivos a la vez."""
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = created.json()["id"]

    cap = get_settings().companion_max_concurrent_runs
    await _open_runs(thread_id, a["user_id"], cap)

    refused = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "otro más"},
    )
    assert refused.status_code == 429, refused.text
    detail = refused.json()["detail"]
    assert str(cap) in detail and "running" in detail


async def test_a_run_past_its_own_ceiling_no_longer_blocks_the_member(
    client, console_world, monkeypatch
):
    """Un huérfano de un proceso muerto no puede dejar a nadie bloqueado.

    Es la razón de contar sobre ``companion.runs`` y no sobre un contador de
    Redis: un contador que se incrementa al arrancar se queda alto para
    siempre si el proceso muere antes de decrementarlo.
    """
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = created.json()["id"]
    await _open_runs(thread_id, a["user_id"], get_settings().companion_max_concurrent_runs)

    # El techo de duración pasa a ser cero: todos los abiertos están caducados.
    settings = get_settings()
    monkeypatch.setattr(settings, "companion_run_max_seconds", 0.0)
    accepted = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "sigo trabajando"},
    )
    assert accepted.status_code == 202, accepted.text


async def test_the_cap_is_per_member_not_per_partner(client, console_world, db_session):
    """Dos personas del mismo partner no se estorban: el sujeto del tope es
    el principal, igual que el de la RLS."""
    from tests.conftest import add_console_member

    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")

    created = await client.post(
        "/console/companion/threads", headers=a["headers"](), json={"title": "t"}
    )
    thread_id = created.json()["id"]
    await _open_runs(thread_id, a["user_id"], get_settings().companion_max_concurrent_runs)

    mine = await client.post(
        f"/console/companion/threads/{thread_id}/runs",
        headers=a["headers"](),
        json={"prompt": "x"},
    )
    assert mine.status_code == 429

    theirs_thread = await client.post(
        "/console/companion/threads", headers=other["headers"](), json={"title": "t"}
    )
    assert theirs_thread.status_code == 201
    theirs = await client.post(
        f"/console/companion/threads/{theirs_thread.json()['id']}/runs",
        headers=other["headers"](),
        json={"prompt": "x"},
    )
    assert theirs.status_code == 202, theirs.text
