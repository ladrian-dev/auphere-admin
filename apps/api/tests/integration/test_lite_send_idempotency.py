"""Spec 031 · R6.4, CE-004 — un reintento nunca manda dos WhatsApp (T074).

En el teléfono la red se corta. La app manda cada mensaje con una
``Idempotency-Key`` que **reutiliza en cada reintento**; la API guarda la clave
en ``messages.idempotency_key`` (índice único por tenant, migración 0053) y un
segundo intento con la misma clave devuelve el mismo envío sin crear otro.

Lo que se fija aquí, en el envío de texto y en el de archivos:

- la primera vez, 201; la misma clave otra vez, 200 con el **mismo** cuerpo y
  sin una segunda fila;
- un envío ``failed`` se reintenta sobre **la misma fila**, comprobando antes
  las precondiciones (porque esta vez sí envía);
- dos peticiones a la vez con la misma clave no dan nunca un 500;
- la misma clave en otra conversación es 422, y una clave mal formada, 400.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Conversation, Message, MessageDirection, MessageStatus
from tests.conftest import add_client_phone, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def inbox(client, db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    box = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], conversations=2
    )
    phone = await add_client_phone(db_session, membership_id=box["member"]["membership_id"])
    conv = box["conversations"][0]
    taken = await client.post(
        f"/console/lite/inbox/conversations/{conv}/takeover", headers=phone["headers"]()
    )
    assert taken.status_code == 200, taken.text
    return {**box, "phone": phone, "conv": conv}


def _send_url(conv: uuid.UUID) -> str:
    return f"/console/lite/inbox/conversations/{conv}/messages"


async def _outbound(db_session, conv: uuid.UUID) -> list[Message]:
    db_session.expire_all()
    return list(
        (
            await db_session.scalars(
                sa.select(Message).where(
                    Message.conversation_id == conv,
                    Message.direction == MessageDirection.OUTBOUND,
                    Message.actor_kind == "member",
                )
            )
        ).all()
    )


async def test_the_same_key_sends_once(client, db_session, inbox) -> None:
    key = str(uuid.uuid4())
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": key}

    first = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})
    again = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})

    assert first.status_code == 201, first.text
    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    rows = await _outbound(db_session, inbox["conv"])
    assert len(rows) == 1
    assert rows[0].idempotency_key == key


async def test_without_a_key_nothing_changes(client, db_session, inbox) -> None:
    headers = inbox["phone"]["headers"]()
    a = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "uno"})
    b = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "uno"})
    assert a.status_code == b.status_code == 201
    assert len(await _outbound(db_session, inbox["conv"])) == 2


async def test_a_failed_send_is_retried_on_the_same_row(client, db_session, inbox) -> None:
    key = str(uuid.uuid4())
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": key}
    first = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})
    msg_id = uuid.UUID(first.json()["id"])
    await db_session.execute(
        sa.update(Message)
        .where(Message.id == msg_id)
        .values(status=MessageStatus.FAILED, attempts=3, failure_code="131000", last_error="x")
    )
    await db_session.commit()

    retry = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})

    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == str(msg_id)
    assert retry.json()["delivery"] == "pending"
    rows = await _outbound(db_session, inbox["conv"])
    assert [r.id for r in rows] == [msg_id]
    assert rows[0].status == MessageStatus.PENDING
    assert rows[0].attempts == 0 and rows[0].failure_code is None


async def test_a_replay_answers_even_after_the_window_closed(client, db_session, inbox) -> None:
    key = str(uuid.uuid4())
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": key}
    first = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == inbox["conv"])
        .values(last_inbound_at=datetime.now(UTC) - timedelta(days=2))
    )
    await db_session.commit()

    again = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})

    assert again.status_code == 200
    assert again.json() == first.json()


async def test_retrying_a_failed_send_rechecks_the_window(client, db_session, inbox) -> None:
    key = str(uuid.uuid4())
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": key}
    first = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})
    await db_session.execute(
        sa.update(Message)
        .where(Message.id == uuid.UUID(first.json()["id"]))
        .values(status=MessageStatus.FAILED)
    )
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == inbox["conv"])
        .values(last_inbound_at=datetime.now(UTC) - timedelta(days=2))
    )
    await db_session.commit()

    retry = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})

    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "window_closed"


async def test_concurrent_requests_with_one_key_never_500(client, db_session, inbox) -> None:
    key = str(uuid.uuid4())
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": key}

    results = await asyncio.gather(
        *[
            client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "a la vez"})
            for _ in range(4)
        ]
    )

    assert all(r.status_code in (200, 201) for r in results), [r.status_code for r in results]
    assert len({r.json()["id"] for r in results}) == 1
    assert len(await _outbound(db_session, inbox["conv"])) == 1


async def test_the_same_key_on_another_conversation_is_rejected(client, inbox) -> None:
    key = str(uuid.uuid4())
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": key}
    await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})
    other = inbox["conversations"][1]
    await client.post(
        f"/console/lite/inbox/conversations/{other}/takeover", headers=inbox["phone"]["headers"]()
    )

    resp = await client.post(_send_url(other), headers=headers, json={"text": "Hola"})

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "idempotency_key_reused"


@pytest.mark.parametrize("bad", ["no-es-un-uuid", "x" * 81])
async def test_a_malformed_key_is_400(client, inbox, bad: str) -> None:
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": bad}
    resp = await client.post(_send_url(inbox["conv"]), headers=headers, json={"text": "Hola"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "idempotency_key_invalid"


async def test_an_attachment_with_the_same_key_is_uploaded_once(
    client, db_session, inbox, monkeypatch
) -> None:
    from nexus_api.api.console.lite import inbox_media

    uploads: list[str] = []

    class _Stored:
        def __init__(self, key: str) -> None:
            self.key = key

    class _Storage:
        async def put_outbound(self, **kw: Any) -> _Stored:
            uploads.append(kw["filename"])
            return _Stored(f"tenants/x/outbound/{uuid.uuid4().hex}.jpg")

    monkeypatch.setattr(inbox_media, "get_media_storage", lambda: _Storage())
    key = str(uuid.uuid4())
    headers = {**inbox["phone"]["headers"](), "Idempotency-Key": key}
    files = {"file": ("foto.jpg", b"\xff\xd8\xff\xe0data", "image/jpeg")}
    url = f"/console/lite/inbox/conversations/{inbox['conv']}/attachments"

    first = await client.post(url, headers=headers, files=files)
    again = await client.post(url, headers=headers, files=files)

    assert first.status_code == 201, first.text
    assert again.status_code == 200, again.text
    assert again.json() == first.json()
    assert uploads == ["foto.jpg"]
    assert len(await _outbound(db_session, inbox["conv"])) == 1
