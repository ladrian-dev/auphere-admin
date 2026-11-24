"""Spec 076, requisito 4.3 — volver a autorizar un número no es dar de alta otro.

Un cliente en su tope de números que vuelve a pasar el registro insertado con
el **mismo** ``phone_number_id`` (para conceder el permiso de eventos) no
recibe el 409 de cuota. Uno que conecta un número nuevo, sí.

El orquestador del alta se sustituye por uno que responde 418: llegar a él es
haber pasado la cuota.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, Partner

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
def no_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reached(**_: Any) -> Any:
        raise HTTPException(status_code=418, detail="reached the signup")

    monkeypatch.setattr("nexus_api.api.console.whatsapp.complete_meta_signup", reached)


async def _at_quota(db_session: Any, w: dict[str, Any]) -> None:
    await db_session.execute(
        sa.update(Partner).where(Partner.id == w["partner_id"]).values(max_channels_per_client=1)
    )
    await db_session.commit()
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant_id"]):
        s.add(
            Channel(
                id=uuid.uuid4(),
                tenant_id=w["tenant_id"],
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier="+56999990001",
                status=ChannelStatus.ACTIVE,
                config={"phone_number_id": "PN1", "waba_id": "WABA1"},
            )
        )
        await s.commit()


async def _signup(client: Any, w: dict[str, Any], pnid: str) -> Any:
    return await client.post(
        f"/console/clients/{w['ref']}/channels/whatsapp/signup",
        json={"code": "c", "waba_id": "WABA1", "phone_number_id": pnid},
        headers=w["headers"](),
    )


async def test_reconnecting_the_same_number_passes_the_quota(
    client, db_session, console_world, no_meta
) -> None:
    w = console_world["a"]
    await _at_quota(db_session, w)
    r = await _signup(client, w, "PN1")
    assert r.status_code == 418, r.text


async def test_a_new_number_still_hits_the_quota(
    client, db_session, console_world, no_meta
) -> None:
    w = console_world["a"]
    await _at_quota(db_session, w)
    r = await _signup(client, w, "PN2")
    assert r.status_code == 409
