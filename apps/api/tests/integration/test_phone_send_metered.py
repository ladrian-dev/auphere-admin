"""Spec 031 · R6.8 — lo que se envía desde el teléfono se mide igual (T036).

El medidor no mira quién envió: el despachador de salida emite un
``channel.message`` por cada saliente que el proveedor acepta
(``nexus_worker/streams/outbound.py``, ``record_channel_message``). Lo que hay
que garantizar es que el teléfono produce **la misma fila saliente** que la web
—pendiente, de la persona, en la misma conversación—, porque esa fila es lo que
el despachador envía y cobra al cliente. Si el teléfono crease otra cosa, el
envío se escaparía del medidor sin que nadie lo notara.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Message, MessageDirection
from tests.conftest import add_client_phone, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _shape(m: Message) -> dict[str, Any]:
    return {
        "direction": m.direction,
        "status": m.status,
        "actor_kind": m.actor_kind,
        "actor_id": m.actor_id,
        "conversation_id": m.conversation_id,
        "tenant_id": m.tenant_id,
        "content": m.content,
    }


async def test_a_phone_send_is_the_same_outbound_row_as_a_web_send(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    box = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    phone = await add_client_phone(db_session, membership_id=box["member"]["membership_id"])
    conv = box["conversations"][0]
    await client.post(
        f"/console/lite/inbox/conversations/{conv}/takeover", headers=phone["headers"]()
    )
    url = f"/console/lite/inbox/conversations/{conv}/messages"

    web = await client.post(url, headers=box["member"]["headers"](), json={"text": "igual"})
    app = await client.post(url, headers=phone["headers"](), json={"text": "igual"})
    assert web.status_code == app.status_code == 201

    db_session.expire_all()
    rows = {
        str(m.id): m
        for m in (
            await db_session.scalars(
                sa.select(Message).where(
                    Message.conversation_id == conv,
                    Message.direction == MessageDirection.OUTBOUND,
                    Message.actor_kind == "member",
                )
            )
        ).all()
    }
    assert _shape(rows[app.json()["id"]]) == _shape(rows[web.json()["id"]])
