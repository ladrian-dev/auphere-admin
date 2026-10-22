"""Spec 030 — el tiempo real de la Bandeja avisa de lo confirmado (bug
``bandeja-publica-antes-del-commit``).

El aviso no lleva cuerpo: quien lo oye vuelve a pedir la conversación por su
ruta. Si el aviso sale antes del commit, esa lectura ve el estado de antes y no
vuelve a pedir nada, porque el aviso ya pasó. Lo que fija este archivo:

- en cada acción de la Bandeja que avisa, lo que un suscriptor lee por su propia
  conexión **en el momento** de oír el aviso es lo que quedó confirmado;
- una acción que escribe y luego hace rollback no avisa de nada;
- toda ruta lite que escribe con un Redis propio está en la tabla de abajo, así
  que una ruta nueva que avise no se escapa de la primera comprobación.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.console.lite import inbox as inbox_routes
from nexus_api.api.deps import get_redis
from nexus_api.db.models import Conversation, ConversationTag, Message
from nexus_api.services.inbox_stream import inbox_channel
from nexus_api.services.media_storage import InMemoryMediaStorage
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


@dataclass(frozen=True)
class _Action:
    method: str
    route: str
    before: tuple[str, ...] = ()
    json: dict[str, Any] | None = None
    files: dict[str, Any] | None = None
    data: dict[str, str] | None = None


ACTIONS: dict[str, _Action] = {
    "takeover": _Action("POST", "takeover"),
    "release": _Action("POST", "release", before=("takeover",)),
    "messages": _Action("POST", "messages", before=("takeover",), json={"text": "Ya te atiendo"}),
    "attachments": _Action(
        "POST",
        "attachments",
        before=("takeover",),
        files={"file": ("carta.jpg", b"\x00" * 1024, "image/jpeg")},
        data={"caption": "Te mando la carta"},
    ),
    "resolve": _Action("POST", "resolve"),
    "reopen": _Action("POST", "reopen", before=("resolve",)),
    "tags": _Action("PUT", "tags", json={"tags": ["vip"]}),
}


async def _do(client, inbox: dict[str, Any], conversation_id: uuid.UUID, name: str):
    a = ACTIONS[name]
    return await client.request(
        a.method,
        f"{BASE}/{conversation_id}/{a.route}",
        headers=inbox["headers"](),
        json=a.json,
        files=a.files,
        data=a.data,
    )


async def _committed(engine, conversation_id: uuid.UUID) -> dict[str, Any]:
    """Lo confirmado, leído por una conexión aparte: lo único que vería otra
    pestaña al volver a pedir la conversación."""
    async with AsyncSession(engine) as s:
        conv = (
            await s.execute(
                sa.select(
                    Conversation.status,
                    Conversation.agent_active,
                    Conversation.agent_active_version,
                    Conversation.assigned_user_id,
                ).where(Conversation.id == conversation_id)
            )
        ).one()
        messages = (
            await s.execute(sa.select(Message.id).where(Message.conversation_id == conversation_id))
        ).scalars()
        tags = (
            await s.execute(
                sa.select(ConversationTag.tag).where(
                    ConversationTag.conversation_id == conversation_id
                )
            )
        ).scalars()
        return {
            "status": conv.status,
            "agent_active": conv.agent_active,
            "version": conv.agent_active_version,
            "assignee": conv.assigned_user_id,
            "messages": sorted(str(m) for m in messages),
            "tags": sorted(str(t) for t in tags),
        }


@dataclass(frozen=True)
class _Heard:
    channel: str
    event: dict[str, Any]
    committed: dict[str, Any]


@pytest.fixture
def heard(fake_redis, test_engine, monkeypatch: pytest.MonkeyPatch) -> list[_Heard]:
    """Un suscriptor que, en cuanto oye un aviso de la Bandeja, vuelve a leer la
    conversación por su propia conexión — lo que hace la consola al recibirlo."""
    out: list[_Heard] = []
    publish = fake_redis.publish

    async def _publish(channel: str, message: str) -> int:
        if channel.startswith("inbox:"):
            event = json.loads(message)
            seen = await _committed(test_engine, uuid.UUID(event["conversation_id"]))
            out.append(_Heard(channel=channel, event=event, committed=seen))
        return int(await publish(channel, message))

    monkeypatch.setattr(fake_redis, "publish", _publish)
    return out


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> InMemoryMediaStorage:
    store = InMemoryMediaStorage()
    monkeypatch.setattr("nexus_api.api.console.lite.inbox_media.get_media_storage", lambda: store)
    return store


@pytest.mark.parametrize("action", sorted(ACTIONS))
async def test_what_an_event_announces_is_already_committed(
    action: str, client, db_session, console_world, storage, heard, test_engine
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    for step in ACTIONS[action].before:
        r = await _do(client, inbox, c0, step)
        assert r.status_code < 300, r.text
    heard.clear()

    r = await _do(client, inbox, c0, action)
    assert r.status_code < 300, r.text

    assert heard, f"{action} no avisó"
    committed = await _committed(test_engine, c0)
    for h in heard:
        assert h.channel == inbox_channel(w["tenant_id"])
        assert h.committed == committed, (
            f"{action}: «{h.event['event']}» llegó antes del commit — quien lo oyó "
            f"leyó {h.committed}, y lo confirmado es {committed}"
        )


async def test_an_action_that_rolls_back_announces_nothing(
    client, db_session, console_world, heard, test_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    before = await _committed(test_engine, c0)

    async def _fails_after_writing(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("falla después de escribir")

    # Tomar el control escribe, hace flush y solo entonces pinta la respuesta.
    monkeypatch.setattr(inbox_routes, "_detail_out", _fails_after_writing)
    with pytest.raises(RuntimeError, match="después de escribir"):
        await _do(client, inbox, c0, "takeover")

    assert await _committed(test_engine, c0) == before
    assert heard == []


async def test_every_lite_route_that_announces_is_checked() -> None:
    """Una ruta lite avisa con el Redis que recibe ella misma
    (``redis = Depends(get_redis)``). La persona también usa Redis, pero por
    debajo de ``lite_scope``: eso no cuenta."""
    from nexus_api.main import app

    announcing: set[tuple[str, str]] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/console/lite/"):
            continue
        if any(d.call is get_redis for d in route.dependant.dependencies):
            announcing |= {(m, route.path) for m in route.methods - {"GET", "HEAD"}}

    checked = {(a.method, f"{BASE}/{{conversation_id}}/{a.route}") for a in ACTIONS.values()}
    # Spec 043: Reservas recibe su Redis para la ``Idempotency-Key`` (24 h) de
    # equipo, servicios, bloqueos y lista de espera; no avisa a la Bandeja.
    reservas = {r for r in announcing if r[1].startswith("/console/lite/reservas/")}
    assert reservas == {
        ("POST", "/console/lite/reservas/blocks"),
        ("POST", "/console/lite/reservas/services"),
        ("POST", "/console/lite/reservas/staff"),
        ("POST", "/console/lite/reservas/waitlist"),
    }
    import inspect

    from nexus_api.api.console.lite import reservas as reservas_routes

    assert "publish_inbox_event" not in inspect.getsource(reservas_routes)
    assert announcing - reservas == checked
