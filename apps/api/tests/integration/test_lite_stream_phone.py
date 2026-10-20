"""Spec 031 · R5.4 — la Bandeja en vivo con la credencial del teléfono
(tarea T067).

`GET /console/lite/inbox/stream` es la misma ruta para la web y para la app.
Con el teléfono:

- abre la línea (`ready`) y se suscribe **al canal de su cliente**, el que
  sale de la fila del teléfono, nunca de algo que mande la app;
- sin el módulo de la Bandeja, o con el teléfono cerrado, no abre nada.

La línea real dura minutos: aquí se toma solo su primer evento.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from starlette.responses import StreamingResponse

from nexus_api.api.console.lite import inbox_stream as stream_route
from nexus_api.db.models import ClientPhone
from tests.conftest import add_client_member, add_client_phone, make_client_access, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

STREAM = "/console/lite/inbox/stream"


@pytest.fixture
def first_event(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Swap the SSE response for one that yields the first event and ends;
    record which tenant's channel the route subscribed to."""
    channels: list[uuid.UUID] = []
    real_channel = stream_route.inbox_channel

    def channel(tenant_id: uuid.UUID) -> str:
        channels.append(tenant_id)
        return real_channel(tenant_id)

    class FirstEvent(StreamingResponse):
        def __init__(self, gen: Any) -> None:
            async def one() -> Any:
                async for event in gen:
                    yield json.dumps(event)
                    break

            super().__init__(one(), media_type="application/json")

    monkeypatch.setattr(stream_route, "inbox_channel", channel)
    monkeypatch.setattr(stream_route, "EventSourceResponse", FirstEvent)
    return channels


async def test_the_phone_opens_its_clients_line(
    client, db_session, console_world, first_event
) -> None:
    a = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    phone = await add_client_phone(db_session, membership_id=inbox["member"]["membership_id"])

    r = await client.get(STREAM, headers=phone["headers"]())
    assert r.status_code == 200, r.text
    assert json.loads(r.text)["event"] == "ready"
    assert first_event == [a["tenant_id"]]


async def test_without_the_inbox_module_there_is_no_line(
    client, db_session, console_world, first_event
) -> None:
    a = console_world["a"]
    await make_client_access(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"], modules=("panel",)
    )
    member = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    phone = await add_client_phone(db_session, membership_id=member["membership_id"])

    assert (await client.get(STREAM, headers=phone["headers"]())).status_code == 403
    assert first_event == []


async def test_a_closed_phone_cannot_reopen_the_line(
    client, db_session, console_world, first_event
) -> None:
    a = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    phone = await add_client_phone(db_session, membership_id=inbox["member"]["membership_id"])
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == phone["phone_id"])
        .values(revoked_at=datetime.now(UTC), revoked_reason="closed_by_auphere")
    )
    await db_session.commit()

    r = await client.get(STREAM, headers=phone["headers"]())
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "phone_closed"
    assert first_event == []
