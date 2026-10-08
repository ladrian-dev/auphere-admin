"""Spec 030 T082 — respuestas guardadas y archivos (Requisitos 10.3 y 10.4).

- las respuestas guardadas son del cliente: crear, editar y «borrar», que
  **archiva** (constitución §IV: borrar no existe) y deja de listarla;
  ``title`` ≤ 80 y ``body`` ≤ 1.000; las de otro cliente no existen;
- un adjunto es JPEG o PNG hasta 5 MB o PDF hasta 16 MB; lo demás se rechaza
  diciendo el límite (415/413); se guarda con ``put_outbound`` y queda como
  mensaje ``member`` pendiente, con las mismas precondiciones que el texto.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog, Message, SavedReply
from nexus_api.services.media_storage import InMemoryMediaStorage
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

REPLIES = "/console/lite/inbox/replies"
BASE = "/console/lite/inbox/conversations"
MB = 1024 * 1024


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> InMemoryMediaStorage:
    store = InMemoryMediaStorage()
    monkeypatch.setattr("nexus_api.api.console.lite.inbox_media.get_media_storage", lambda: store)
    return store


async def test_saved_replies_are_archived_not_deleted(client, db_session, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    inbox = await make_inbox(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    other = await make_inbox(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])

    r = await client.post(
        REPLIES,
        headers=inbox["headers"](),
        json={"title": " Horario ", "body": "Abrimos de 10 a 20 h."},
    )
    assert r.status_code == 201, r.text
    reply = r.json()
    assert reply["title"] == "Horario"
    for bad in ({"title": "x" * 81, "body": "y"}, {"title": "t", "body": "y" * 1001}):
        assert (await client.post(REPLIES, headers=inbox["headers"](), json=bad)).status_code == 422

    edited = await client.patch(
        f"{REPLIES}/{reply['id']}", headers=inbox["headers"](), json={"body": "De 9 a 21 h."}
    )
    assert edited.status_code == 200 and edited.json()["body"] == "De 9 a 21 h."

    # Otro cliente no la ve ni la toca.
    assert (await client.get(REPLIES, headers=other["headers"]())).json() == []
    for call in (
        client.patch(f"{REPLIES}/{reply['id']}", headers=other["headers"](), json={"body": "z"}),
        client.delete(f"{REPLIES}/{reply['id']}", headers=other["headers"]()),
    ):
        assert (await call).status_code == 404

    gone = await client.delete(f"{REPLIES}/{reply['id']}", headers=inbox["headers"]())
    assert gone.status_code == 204
    assert (await client.get(REPLIES, headers=inbox["headers"]())).json() == []
    row = (
        await db_session.execute(
            sa.select(SavedReply).where(SavedReply.id == uuid.UUID(reply["id"]))
        )
    ).scalar_one()
    assert row.archived_at is not None
    again = await client.delete(f"{REPLIES}/{reply['id']}", headers=inbox["headers"]())
    assert again.status_code == 404


async def _take(client, inbox, conversation_id) -> None:
    r = await client.post(f"{BASE}/{conversation_id}/takeover", headers=inbox["headers"]())
    assert r.status_code == 200, r.text


async def _attach(client, inbox, conversation_id, *, name: str, mime: str, size: int):
    return await client.post(
        f"{BASE}/{conversation_id}/attachments",
        headers=inbox["headers"](),
        files={"file": (name, b"\x00" * size, mime)},
        data={"caption": "Te mando la carta"},
    )


async def test_an_image_goes_out_as_a_member_message(
    client, db_session, console_world, storage
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]

    blocked = await _attach(client, inbox, c0, name="carta.jpg", mime="image/jpeg", size=10)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "not_assigned_to_you"

    await _take(client, inbox, c0)
    r = await _attach(client, inbox, c0, name="carta.jpg", mime="image/jpeg", size=1024)
    assert r.status_code == 201, r.text
    msg = (
        await db_session.execute(sa.select(Message).where(Message.id == uuid.UUID(r.json()["id"])))
    ).scalar_one()
    assert msg.actor_kind == "member"
    assert msg.actor_id == inbox["member"]["membership_id"]
    assert msg.media_kind == "image"
    assert msg.media_filename == "carta.jpg"
    assert msg.content == "Te mando la carta"
    assert msg.status.value == "pending"
    body, mime = await storage.get_object(msg.media_s3_key)
    assert len(body) == 1024 and mime == "image/jpeg"

    (row,) = (
        await db_session.execute(
            sa.select(AuditLog).where(
                AuditLog.tenant_id == w["tenant_id"], AuditLog.action == "inbox.attachment_sent"
            )
        )
    ).scalars()
    assert row.after_json == {"kind": "image", "bytes": 1024}


async def test_files_out_of_bounds_are_refused_with_the_limit(
    client, db_session, console_world, storage
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    c0 = inbox["conversations"][0]
    await _take(client, inbox, c0)

    gif = await _attach(client, inbox, c0, name="a.gif", mime="image/gif", size=10)
    assert gif.status_code == 415
    assert gif.json()["detail"]["allowed"] == ["application/pdf", "image/jpeg", "image/png"]

    big = await _attach(client, inbox, c0, name="a.png", mime="image/png", size=5 * MB + 1)
    assert big.status_code == 413
    assert big.json()["detail"]["limit_bytes"] == 5 * MB

    pdf = await _attach(client, inbox, c0, name="carta.pdf", mime="application/pdf", size=6 * MB)
    assert pdf.status_code == 201, pdf.text
    assert storage._objects  # se guardó el PDF, y solo lo válido
    assert len(storage._objects) == 1
