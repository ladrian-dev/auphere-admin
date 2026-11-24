"""Spec 076, requisitos 1.1 y 1.2 — el worker guarda el clic del anuncio.

``accept_inbound`` guarda una fila en ``customer_ad_referrals`` en la misma
transacción que el mensaje: el contacto, la conversación, el número y la hora del
mensaje. Una redistribución del mismo mensaje no la duplica, y un segundo clic
del mismo contacto añade otra fila. El stream trae el anuncio en
``referral_json``; un JSON roto no tira el mensaje.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import accept_inbound
from nexus_worker.streams.consumer import _to_event

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import CustomerAdReferral

from ._turn_world import conversation_of, make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

USER = "+34600111222"
AD = {
    "source_type": "ad",
    "source_id": "120200000000000",
    "source_url": "https://fb.me/ad",
    "headline": "Corte + barba",
    "body": "20% esta semana",
    "media_type": "image",
    "ctwa_clid": "ARAkLkA8rmlFeiCktEJ",
}


async def _referrals(world: Any) -> list[CustomerAdReferral]:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        rows = list(
            (await s.execute(sa.select(CustomerAdReferral).order_by(CustomerAdReferral.clicked_at)))
            .scalars()
            .all()
        )
        for row in rows:
            s.expunge(row)
        return rows


async def test_the_click_is_stored_with_its_contact_and_number(db_session) -> None:
    world = await make_world(db_session)
    accepted = await accept_inbound(world.event("Vi su anuncio", user=USER, referral=AD))

    (row,) = await _referrals(world)
    conv = await conversation_of(world, USER)
    assert row.customer_id == conv.customer_id
    assert row.conversation_id == accepted.conversation_id == conv.id
    assert row.channel_id == world.channel_id
    assert row.source_type == "ad"
    assert row.source_id == AD["source_id"]
    assert row.headline == AD["headline"]
    assert row.ad_text == AD["body"]
    assert row.ctwa_clid == AD["ctwa_clid"]
    assert row.clicked_at is not None


async def test_a_redelivery_does_not_duplicate(db_session) -> None:
    world = await make_world(db_session)
    event = world.event("Vi su anuncio", user=USER, referral=AD, wamid="wamid.same")
    await accept_inbound(event)
    await accept_inbound(event)
    assert len(await _referrals(world)) == 1


async def test_a_second_click_adds_a_row(db_session) -> None:
    world = await make_world(db_session)
    await accept_inbound(world.event("Vi su anuncio", user=USER, referral=AD))
    other = {**AD, "source_id": "999", "ctwa_clid": "SECOND"}
    await accept_inbound(world.event("Otra vez", user=USER, referral=other))
    rows = await _referrals(world)
    assert [r.ctwa_clid for r in rows] == [AD["ctwa_clid"], "SECOND"]


async def test_no_referral_no_row(db_session) -> None:
    world = await make_world(db_session)
    await accept_inbound(world.event("hola", user=USER))
    assert await _referrals(world) == []


def _fields(world: Any, **extra: str) -> dict[str, str]:
    return {
        "tenant_id": str(world.tenant_id),
        "channel_id": str(world.channel_id),
        "user_id": USER,
        "content": "Vi su anuncio",
        "provider": "meta",
        "provider_message_id": f"wamid.{uuid.uuid4().hex}",
        "kind": "text",
        **extra,
    }


async def test_the_consumer_reads_referral_json(db_session) -> None:
    world = await make_world(db_session)
    event = _to_event(_fields(world, referral_json=json.dumps(AD)))
    assert event.referral is not None
    assert event.referral["ctwa_clid"] == AD["ctwa_clid"]


async def test_a_broken_referral_does_not_drop_the_message(db_session) -> None:
    world = await make_world(db_session)
    event = _to_event(_fields(world, referral_json="{broken"))
    assert event.referral is None
    accepted = await accept_inbound(event)
    assert accepted.message_id is not None
    assert await _referrals(world) == []
