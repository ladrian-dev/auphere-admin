"""Requisito 5 — Pendientes: lo que **mis** teammates esperan de mí.

Tres reglas que se prueban aquí: la bandeja es de la persona (no del partner),
no mezcla lo del Companion de la consola (supuesto confirmado), y decidir en un
sitio se ve en el otro sin recargar — el aviso viaja por el canal de la persona.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

import pytest

from nexus_api.db.models import Teammate
from nexus_api.db.models.companion import (
    RUN_WAITING,
    CompanionAction,
    CompanionRun,
    CompanionThread,
    TeammateTask,
)

pytestmark = pytest.mark.asyncio


async def _seed(db_session, world, *, principal_id: str | None = None, level: str = "aviso"):
    """Un teammate, su hilo, una tarea esperando y su acción propuesta."""
    principal = principal_id or world["user_id"]
    teammate = Teammate(
        id=uuid.uuid4(),
        partner_id=world["partner_id"],
        name="Sofía",
        job="Atención al cliente",
        model="auphere-sonnet",
        tool_names=["console.whoami"],
        permissions={
            "read": True,
            "write": False,
            "spend": False,
            "publish": False,
            "contact": False,
        },
        local_exec=False,
        created_by=principal,
    )
    db_session.add(teammate)
    await db_session.flush()
    thread = CompanionThread(
        id=uuid.uuid4(),
        principal_id=principal,
        partner_id=world["partner_id"],
        tenant_id=world["tenant_id"],
        teammate_id=teammate.id,
        title="t",
    )
    db_session.add(thread)
    await db_session.flush()
    run = CompanionRun(
        thread_id=thread.id,
        principal_id=principal,
        teammate_id=teammate.id,
        status=RUN_WAITING,
        ended_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.flush()
    task = TeammateTask(
        id=uuid.uuid4(),
        thread_id=thread.id,
        teammate_id=teammate.id,
        principal_id=principal,
        title="Revisa el canal",
        state="esperandote",
        expires_at=datetime.now(UTC).replace(year=datetime.now(UTC).year + 1),
        current_run_id=run.id,
    )
    db_session.add(task)
    await db_session.flush()
    action = CompanionAction(
        id=uuid.uuid4(),
        thread_id=thread.id,
        run_id=run.id,
        task_id=task.id,
        kind="prompt",
        payload={"title": "Asignar el rol de atención"},
        level=level,
        status="proposed",
        proposed_at=datetime.now(UTC),
    )
    db_session.add(action)
    task.pending_action_id = action.id
    await db_session.commit()
    return teammate, thread, run, task, action


async def test_the_inbox_lists_what_my_teammates_wait_for(client, db_session, console_world):
    a = console_world["a"]
    teammate, _thread, run, task, action = await _seed(db_session, a, level="critico")
    response = await client.get("/console/teammates/inbox", headers=a["headers"]())
    assert response.status_code == 200, response.text
    items = response.json()
    assert len(items) == 1
    item = items[0]
    assert item["action_id"] == str(action.id)
    assert item["task_id"] == str(task.id)
    assert item["run_id"] == str(run.id)
    assert item["teammate"] == {"id": str(teammate.id), "name": "Sofía"}
    assert item["level"] == "critico"
    assert item["client_ref"] == a["ref"]
    assert item["can_decide"] is True
    assert "tenant_id" not in json.dumps(item)


async def test_the_inbox_never_shows_another_persons_cards(client, db_session, console_world):
    a = console_world["a"]
    await _seed(db_session, a, principal_id="user_colleague_a")
    response = await client.get("/console/teammates/inbox", headers=a["headers"]())
    assert response.json() == []


async def test_the_inbox_ignores_the_console_companion(client, db_session, console_world):
    """Supuesto confirmado: Pendientes es de los teammates; el cajón sigue como está."""
    a = console_world["a"]
    thread = CompanionThread(
        id=uuid.uuid4(), principal_id=a["user_id"], partner_id=a["partner_id"], title="cajón"
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        CompanionAction(
            id=uuid.uuid4(),
            thread_id=thread.id,
            kind="prompt",
            payload={},
            status="proposed",
            proposed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    response = await client.get("/console/teammates/inbox", headers=a["headers"]())
    assert response.json() == []


async def test_a_card_the_role_cannot_decide_says_so(client, db_session, console_world):
    from tests.conftest import add_console_member

    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    await _seed(db_session, a, principal_id=analyst["user_id"])
    # El analista no puede ni abrir la bandeja: `teammates:use` no es suyo.
    denied = await client.get("/console/teammates/inbox", headers=analyst["headers"]())
    assert denied.status_code == 403


async def test_deciding_publishes_to_the_persons_inbox_channel(
    db_session, console_world, fake_redis
):
    """CE-003: el aviso viaja por el canal de la persona, no por sondeo."""
    from nexus_api.services.teammate_inbox import inbox_channel, publish_inbox_changed

    a = console_world["a"]
    _t, _th, _run, _task, action = await _seed(db_session, a)
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(inbox_channel(a["user_id"]))
    await asyncio.sleep(0.05)
    await publish_inbox_changed(
        fake_redis, principal_id=a["user_id"], action_id=action.id, decision="confirm"
    )
    for _ in range(50):
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if message:
            payload = json.loads(message["data"])
            assert payload == {
                "action_id": str(action.id),
                "decision": "confirm",
                "by": a["user_id"],
            }
            break
    else:
        raise AssertionError("el aviso no llegó al canal de la persona")
    await pubsub.unsubscribe(inbox_channel(a["user_id"]))


async def test_the_stream_says_when_it_is_listening_and_carries_the_decision(
    db_session, console_world, fake_redis
):
    """CE-003: el aviso llega por el canal de la persona.

    Se prueba el flujo, no el HTTP: un SSE infinito no cabe en un cliente de
    test (lo leería entero). El `ping` inicial es lo que dice «ya estoy
    suscrito»; sin él, un aviso publicado antes se perdería en silencio.
    """
    from nexus_api.services.teammate_inbox import inbox_events, publish_inbox_changed

    a = console_world["a"]
    _t, _th, _run, task, action = await _seed(db_session, a)
    stream = inbox_events(fake_redis, a["user_id"])

    first = await asyncio.wait_for(anext(stream), timeout=2)
    assert first.startswith("event: ping")

    await publish_inbox_changed(
        fake_redis, principal_id=a["user_id"], action_id=action.id, decision="confirm"
    )
    changed = await asyncio.wait_for(anext(stream), timeout=5)
    assert changed.startswith("event: inbox.changed")
    assert json.loads(changed.split("data: ", 1)[1].strip()) == {
        "action_id": str(action.id),
        "decision": "confirm",
        "by": a["user_id"],
    }

    from nexus_api.services.teammate_inbox import publish_task_state

    await publish_task_state(
        fake_redis, principal_id=a["user_id"], task_id=task.id, state="terminada", cause="completed"
    )
    state = await asyncio.wait_for(anext(stream), timeout=5)
    assert state.startswith("event: task.state")
    assert json.loads(state.split("data: ", 1)[1].strip())["cause"] == "completed"
    await stream.aclose()
