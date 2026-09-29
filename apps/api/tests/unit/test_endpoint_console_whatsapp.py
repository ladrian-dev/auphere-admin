"""El número se puede mover (spec 021, Historia 1).

Un número desvinculado no ocupa sitio: otro cliente lo conecta, y el que lo
soltó conserva su historial. Y un número **vivo** en otro sitio sigue diciendo
«en uso» — con esas palabras y sin decir de quién es.

Aquí se simula **solo el cliente de Meta** (``build_meta_client``), no el
orquestador: el upsert del canal tiene que correr de verdad contra la base,
porque lo que se prueba es el índice.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.services import meta_signup_service

pytestmark = pytest.mark.asyncio


class _FakeMeta:
    """Lo mínimo que ``EmbeddedSignupOrchestrator.complete`` le pide a Meta."""

    def __init__(self, display_phone: str) -> None:
        self.display_phone = display_phone
        self.calls: list[str] = []

    async def exchange_code(self, **_: Any) -> dict[str, Any]:
        self.calls.append("exchange_code")
        return {"access_token": "EAA-fake", "expires_in": 3600}

    async def list_phone_numbers(self, **_: Any) -> dict[str, Any]:
        self.calls.append("list_phone_numbers")
        return {"data": [{"id": "PN-fake"}]}

    async def register_phone(self, **_: Any) -> dict[str, Any]:
        self.calls.append("register_phone")
        return {"success": True}

    async def subscribe_app(self, **_: Any) -> dict[str, Any]:
        self.calls.append("subscribe_app")
        return {"success": True}

    async def get_phone_number(self, **_: Any) -> dict[str, Any]:
        self.calls.append("get_phone_number")
        return {
            "display_phone_number": self.display_phone,
            "verified_name": "Prueba",
            "quality_rating": "GREEN",
            "messaging_limit_tier": "TIER_250",
        }

    async def close(self) -> None:
        pass


def _channel(tenant_id: uuid.UUID, number: str, status: ChannelStatus) -> Channel:
    return Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=number,
        config={"phone_number_id": "PN-old", "waba_id": "W-old"},
        status=status,
    )


class _MetaRefusesRegister(_FakeMeta):
    """Meta rechaza el ``register``: el número sigue en otra cuenta."""

    async def register_phone(self, **_: Any) -> dict[str, Any]:
        self.calls.append("register_phone")
        raise RuntimeError("(#133010) Account has not been registered")


async def _signup(
    client,
    who: dict,
    number: str,
    monkeypatch,
    *,
    fake: _FakeMeta | None = None,
    mode: str = "coexistence",
):
    fake = fake or _FakeMeta(number)
    monkeypatch.setattr(meta_signup_service, "build_meta_client", lambda: fake)
    r = await client.post(
        f"/console/clients/{who['ref']}/channels/whatsapp/signup",
        headers=who["headers"](),
        json={
            "code": "abc",
            "waba_id": "W-new",
            "phone_number_id": "PN-fake",
            "mode": mode,
        },
    )
    return r, fake


async def _row(db_session, channel_id: uuid.UUID) -> Channel | None:
    db_session.expire_all()
    return await db_session.get(Channel, channel_id)


async def test_b_connects_a_number_a_released(
    client, console_world, db_session, monkeypatch
) -> None:
    """T006 · R1.1, R1.2 — y también R4.1: B llega al 201 sin ningún paso de
    aprobación por medio."""
    a, b = console_world["a"], console_world["b"]
    number = f"+3461{uuid.uuid4().int % 10**7:07d}"
    suelto = _channel(a["tenant_id"], number, ChannelStatus.DISCONNECTED)
    db_session.add(suelto)
    await db_session.commit()

    r, _ = await _signup(client, b, number, monkeypatch)
    assert r.status_code == 201, r.text

    de_a = await _row(db_session, suelto.id)
    assert de_a is not None, "la fila de A desapareció: se perdió su historial"
    assert de_a.status is ChannelStatus.DISCONNECTED
    assert de_a.tenant_id == a["tenant_id"]

    de_b = await db_session.scalar(
        sa.select(Channel).where(
            Channel.provider_identifier == number, Channel.tenant_id == b["tenant_id"]
        )
    )
    assert de_b is not None and de_b.id != suelto.id
    assert de_b.status is ChannelStatus.ACTIVE


async def test_reconnecting_revives_the_same_channel(
    client, console_world, db_session, monkeypatch
) -> None:
    """T007 · R1.3 — ya se comporta así: el lookup no filtra por estado. El
    test lo fija para que nadie lo «arregle»."""
    a = console_world["a"]
    number = f"+3462{uuid.uuid4().int % 10**7:07d}"
    suelto = _channel(a["tenant_id"], number, ChannelStatus.DISCONNECTED)
    db_session.add(suelto)
    await db_session.commit()

    r, _ = await _signup(client, a, number, monkeypatch)
    assert r.status_code == 201, r.text
    assert r.json()["channel_id"] == str(suelto.id), "reconectar estrenó otra ficha"

    fila = await _row(db_session, suelto.id)
    assert fila is not None and fila.status is ChannelStatus.ACTIVE
    n = await db_session.scalar(
        sa.select(sa.func.count()).select_from(Channel).where(Channel.provider_identifier == number)
    )
    assert n == 1


async def test_a_live_number_elsewhere_is_in_use_and_names_nobody(
    client, console_world, db_session, monkeypatch
) -> None:
    """T008 · R1.4, R1.5."""
    a, b = console_world["a"], console_world["b"]
    number = f"+3463{uuid.uuid4().int % 10**7:07d}"
    vivo = _channel(a["tenant_id"], number, ChannelStatus.ACTIVE)
    db_session.add(vivo)
    await db_session.commit()

    r, _ = await _signup(client, b, number, monkeypatch)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["code"] == "number_in_use"
    texto = r.text.lower()
    for secreto in (str(a["tenant_id"]), str(a.get("partner_id", "")).lower() or "\x00"):
        assert secreto.lower() not in texto, "el 409 dice de quién es el número"

    intacto = await _row(db_session, vivo.id)
    assert intacto is not None and intacto.status is ChannelStatus.ACTIVE
    assert intacto.tenant_id == a["tenant_id"]


async def test_a_number_meta_still_holds_has_its_own_sentence(
    client, console_world, db_session, monkeypatch
) -> None:
    """T020 · R4.2 — Meta es el árbitro: si A no soltó el número en su
    Business Manager, ``register`` falla. Eso no es un fallo de la consola:
    tiene su código, y no dice de quién es el número. En modo Cloud API,
    que es el único que registra (coexistencia se salta ese paso)."""
    b = console_world["b"]
    number = f"+3462{uuid.uuid4().int % 10**7:07d}"
    r, fake = await _signup(
        client, b, number, monkeypatch, fake=_MetaRefusesRegister(number), mode="cloud_api"
    )
    assert r.status_code == 409, r.text
    body = r.json()["detail"]
    assert body["code"] == "number_held_by_previous_owner"
    assert "Business Manager" in body["message"]
    assert "register_phone" in fake.calls and "subscribe_app" not in fake.calls
    # Y no se escribió un canal a medias.
    assert (
        await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Channel)
            .where(Channel.provider_identifier == number)
        )
        == 0
    )
