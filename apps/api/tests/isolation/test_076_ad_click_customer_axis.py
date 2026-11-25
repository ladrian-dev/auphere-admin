"""Garantía 8 — el clic de un anuncio es de una persona (spec 076, requisitos 1.6 y 6.6).

Dos contactos del mismo negocio, en el mismo número. El clic de A nunca aparece
en lo que se lee para B:

- el ``ad_origin`` de la conversación de B en la Bandeja lite;
- la nota del anuncio del turno de B;
- el evento de conversión de B (requisito 6.6): ni al encolar (el clic que
  atribuye es el del contacto del resultado) ni al enviar (aunque la fila
  apuntara al clic de A, sale el teléfono cifrado de B).

Las lecturas pasan por el contacto y el número **de la conversación**, nunca
por un argumento. Este archivo las recorre todas; si aparece una lectura nueva
del clic, entra aquí.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from nexus_worker.conversions.dispatcher import drain_tenant
from nexus_worker.runtime.dispatcher import InboundEvent, accept_inbound
from nexus_worker.runtime.pipeline import _load_recent_history

from nexus_api.core.guardrails.untrusted import TAG_AD_REFERRAL
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AdConversionEvent, Channel, ChannelStatus, ChannelType, Customer
from nexus_api.services.ad_conversion_dispatch import Outcome, Outgoing
from nexus_api.services.ad_conversions import attributing_click
from nexus_api.services.ad_referrals import last_click

from ..integration._turn_world import conversation_of, make_world
from ..integration.test_076_conversion_dispatch import _click
from ..integration.test_076_conversion_dispatch import _world as _measured_world

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

A, B = "+34600000001", "+34600000002"
AD = {
    "source_type": "ad",
    "source_id": "1",
    "headline": "Anuncio de A",
    "body": "solo A lo vio",
    "ctwa_clid": "CLICK-OF-A",
}


async def _second_number(world: Any) -> uuid.UUID:
    """Otro número del mismo negocio, con el mismo agente."""
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        channel = Channel(
            id=uuid.uuid4(),
            tenant_id=world.tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3461{uuid.uuid4().int % 10**7:07d}",
            config={"phone_number_id": "PN2"},
            status=ChannelStatus.ACTIVE,
            agent_id=world.agent_id,
        )
        s.add(channel)
        await s.commit()
        return channel.id


async def test_b_never_sees_a_click_of_a(db_session) -> None:
    world = await make_world(db_session)
    await accept_inbound(world.event("Vi su anuncio", user=A, referral=AD))
    accepted_b = await accept_inbound(world.event("hola", user=B))
    conv_b = await conversation_of(world, B)

    # La Bandeja lite.
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        assert (
            await last_click(s, customer_id=conv_b.customer_id, channel_id=world.channel_id) is None
        )
        conv_a = await conversation_of(world, A)
        mine = await last_click(s, customer_id=conv_a.customer_id, channel_id=world.channel_id)
        assert mine is not None and mine.ctwa_clid == "CLICK-OF-A"

    # La nota del turno.
    history = await _load_recent_history(world.tenant_id, str(accepted_b.conversation_id))
    assert not any(f"<{TAG_AD_REFERRAL}>" in m["content"] for m in history)
    assert not any("Anuncio de A" in m["content"] for m in history)


async def test_a_click_on_another_number_is_not_this_numbers(db_session) -> None:
    """El mismo contacto escribe a dos números del negocio: el clic del primero no
    es origen del segundo."""
    world = await make_world(db_session)
    second = await _second_number(world)
    await accept_inbound(world.event("Vi su anuncio", user=A, referral=AD))
    accepted = await accept_inbound(
        InboundEvent(
            tenant_id=world.tenant_id,
            channel_id=second,
            user_id=A,
            content="hola",
            provider_message_id=f"wamid.{uuid.uuid4().hex}",
        )
    )

    history = await _load_recent_history(world.tenant_id, str(accepted.conversation_id))
    assert not any(f"<{TAG_AD_REFERRAL}>" in m["content"] for m in history)


async def test_the_event_of_b_never_carries_the_click_of_a(db_session) -> None:
    """Requisito 6.6. A hizo clic; B, en el mismo número, consigue un resultado."""
    w = await _measured_world(db_session)
    click_of_a = await _click(w, clid="CLICK-OF-A")
    bob_phone = "56933334444"
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        bob = Customer(tenant_id=w["tenant"], identifier=bob_phone, phone=bob_phone, preferences={})
        s.add(bob)
        await s.flush()
        # Al encolar: el clic que atribuye es el del contacto del resultado.
        assert (
            await attributing_click(
                s, customer_id=bob.id, channel_id=w["channel"], at=datetime.now(UTC)
            )
            is None
        )
        # Al enviar: una fila de B que apuntara al clic de A.
        s.add(
            AdConversionEvent(
                tenant_id=w["tenant"],
                channel_id=w["channel"],
                customer_id=bob.id,
                referral_id=click_of_a,
                source_kind="reservation",
                source_id="rb",
                event_name="Purchase",
                event_id="reservation:rb:Purchase",
                event_time=datetime.now(UTC),
                value_minor=1000,
                currency="CLP",
                status="pending",
            )
        )
        await s.commit()

    sent: list[Outgoing] = []

    async def meta(out: Outgoing) -> Outcome:
        sent.append(out)
        return Outcome("sent")

    await drain_tenant(w["tenant"], send=meta)
    (out,) = sent
    assert "CLICK-OF-A" not in str(out.event)
    assert out.event["user_data"]["ph"] == [hashlib.sha256(bob_phone.encode()).hexdigest()]
