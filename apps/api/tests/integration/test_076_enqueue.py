"""Spec 076, requisitos 5.1 a 5.9, 6.2 y 6.6 — qué resultados entran en la cola de Meta.

Las reservas se crean con la herramienta ``reservas.create``, como lo hace el
agente: con el tenant, el cliente y la conversación del turno en el contexto.

- reserva del agente con precio → ``Purchase``; sin precio → ``LeadSubmitted``;
- nada si la medición del número está apagada, si el contacto tiene una baja
  activa en ese número, o si no hay clic ni teléfono;
- el clic que atribuye es el último del contacto **en ese número**;
- un reintento del turno no duplica;
- cancelar una reserva con evento encola ``OrderCanceled`` con el mismo clic y
  el mismo importe, la cancele quien la cancele; sin evento, nada;
- una reserva de la consola o de la lista de espera no entra;
- un pedido del agente (WooCommerce) entra con la conversación del turno.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import (
    conversation_context,
    customer_context,
    tenant_context,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AdConversionEvent,
    Channel,
    ChannelAdMeasurement,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    CustomerAdReferral,
    Reservation,
    WhatsAppOptOut,
)
from nexus_api.services.ad_conversions import enqueue_for_booking, enqueue_for_order
from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ANA_PHONE = "56911110000"


def _registry() -> Any:
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    return build_default_registry()


async def _channel(tenant_id: uuid.UUID, *, measured: bool) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        ch = Channel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+5699{uuid.uuid4().int % 10**7:07d}",
            status=ChannelStatus.ACTIVE,
            config={"phone_number_id": "PN"},
        )
        s.add(ch)
        await s.flush()
        if measured:
            s.add(
                ChannelAdMeasurement(
                    tenant_id=tenant_id,
                    channel_id=ch.id,
                    enabled=True,
                    meta_dataset_id="DS1",
                    enabled_by="console:test@auphere.com",
                    enabled_at=datetime.now(UTC),
                )
            )
        await s.commit()
        return ch.id


async def _world(
    db_session: Any,
    console_world: dict[str, Any],
    *,
    mode: str = "services",
    measured: bool = True,
    identifier: str = ANA_PHONE,
    phone: str | None = ANA_PHONE,
) -> dict[str, Any]:
    w = console_world["a"]
    shop = await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], mode=mode
    )
    ana = Customer(
        tenant_id=w["tenant_id"], identifier=identifier, phone=phone, name="Ana", preferences={}
    )
    db_session.add(ana)
    await db_session.commit()
    channel = await _channel(w["tenant_id"], measured=measured)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant_id"]):
        conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=w["tenant_id"],
            channel_id=channel,
            customer_id=ana.id,
            status=ConversationStatus.OPEN,
            last_message_at=datetime.now(UTC),
        )
        s.add(conv)
        await s.commit()
    return {**shop, "ana": ana.id, "channel": channel, "conv": conv.id, "registry": _registry()}


async def _click(
    world: dict[str, Any], *, channel: uuid.UUID | None = None, clid: str = "CLICK-ANA"
) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
        ref = CustomerAdReferral(
            tenant_id=world["tenant_id"],
            customer_id=world["ana"],
            conversation_id=world["conv"] if channel is None else None,
            channel_id=channel or world["channel"],
            provider_message_id=f"wamid.{uuid.uuid4().hex}",
            source_type="ad",
            source_id="A",
            ctwa_clid=clid,
            clicked_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        s.add(ref)
        await s.commit()
        return ref.id


async def _book(world: dict[str, Any], key: str = "k1", **extra: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "date": future_day().isoformat(),
        "time": "10:00",
        "idempotency_key": key,
    }
    if "corte" in world:
        args["service_id"] = str(world["corte"])
    else:
        args["party_size"] = 2
        args["time"] = "13:00"
    args.update(extra)
    with (
        tenant_context(world["tenant_id"]),
        customer_context(world["ana"]),
        conversation_context(world["conv"]),
    ):
        env = await world["registry"].dispatch(
            "reservas.create", args, whitelist=["reservas.create"]
        )
    out = dict(env["result"])
    assert out.get("booking"), out
    return out


async def _events(world: dict[str, Any]) -> list[AdConversionEvent]:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
        rows = list(
            (await s.execute(sa.select(AdConversionEvent).order_by(AdConversionEvent.created_at)))
            .scalars()
            .all()
        )
        for r in rows:
            s.expunge(r)
        return rows


async def test_an_agent_booking_with_price_is_a_purchase(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    ref = await _click(world)
    out = await _book(world)
    (ev,) = await _events(world)
    assert ev.event_name == "Purchase"
    assert (ev.value_minor, ev.currency) == (15000, "CLP")
    assert ev.source_kind == "reservation" and ev.source_id == str(out["booking"]["id"])
    assert ev.event_id == f"reservation:{out['booking']['id']}:Purchase"
    assert ev.channel_id == world["channel"] and ev.customer_id == world["ana"]
    assert ev.referral_id == ref
    assert ev.status == "pending"


async def test_without_price_it_is_a_lead(db_session, console_world) -> None:
    world = await _world(db_session, console_world, mode="capacity")
    await _click(world)
    await _book(world)
    (ev,) = await _events(world)
    assert ev.event_name == "LeadSubmitted"
    assert ev.value_minor is None and ev.currency is None


async def test_measurement_off_means_nothing(db_session, console_world) -> None:
    world = await _world(db_session, console_world, measured=False)
    await _click(world)
    await _book(world)
    assert await _events(world) == []


async def _opt_out(
    world: dict[str, Any], *, channel: uuid.UUID, lifted: bool = False, by_phone: bool = False
) -> None:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
        s.add(
            WhatsAppOptOut(
                tenant_id=world["tenant_id"],
                channel_id=channel,
                customer_id=None if by_phone else world["ana"],
                recipient_phone=ANA_PHONE if by_phone else None,
                scope="marketing",
                source="keyword",
                reason="keyword_stop",
                opted_out_at=datetime.now(UTC) - timedelta(days=1),
                opted_in_at=datetime.now(UTC) if lifted else None,
            )
        )
        await s.commit()


@pytest.mark.parametrize("by_phone", [False, True])
async def test_an_active_opt_out_on_the_number_blocks(
    db_session, console_world, by_phone: bool
) -> None:
    world = await _world(db_session, console_world)
    await _click(world)
    await _opt_out(world, channel=world["channel"], by_phone=by_phone)
    await _book(world)
    assert await _events(world) == []


async def test_a_lifted_or_other_number_opt_out_does_not_block(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    other = await _channel(world["tenant_id"], measured=False)
    await _click(world)
    await _opt_out(world, channel=world["channel"], lifted=True)
    await _opt_out(world, channel=other)
    await _book(world)
    assert len(await _events(world)) == 1


async def test_a_click_on_another_number_does_not_attribute(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    other = await _channel(world["tenant_id"], measured=False)
    await _click(world, channel=other, clid="OTHER-NUMBER")
    await _book(world)
    (ev,) = await _events(world)
    # Sin clic de este número: sale con el teléfono cifrado, sin clic.
    assert ev.referral_id is None


async def test_no_click_and_no_phone_means_nothing(db_session, console_world) -> None:
    # Una persona con nombre de usuario de WhatsApp: solo BSUID, sin teléfono.
    world = await _world(db_session, console_world, identifier="ES.100000000000000001", phone=None)
    await _book(world)
    assert await _events(world) == []


async def test_a_retry_does_not_duplicate(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    await _click(world)
    await _book(world, key="same")
    await _book(world, key="same")
    assert len(await _events(world)) == 1


async def test_cancelling_sends_the_cancellation_with_the_same_click(
    db_session, console_world
) -> None:
    world = await _world(db_session, console_world)
    first = await _click(world)
    out = await _book(world)
    # Un clic más nuevo después de reservar no cambia a quién se atribuye.
    await _click(world, clid="NEWER")
    with (
        tenant_context(world["tenant_id"]),
        customer_context(world["ana"]),
        conversation_context(world["conv"]),
    ):
        env = await world["registry"].dispatch(
            "reservas.cancel", {"booking_id": out["booking"]["id"]}, whitelist=["reservas.cancel"]
        )
    assert env["result"].get("booking"), env["result"]
    purchase, cancel = await _events(world)
    assert cancel.event_name == "OrderCanceled"
    assert cancel.cancels_event_id == purchase.id
    assert cancel.referral_id == first == purchase.referral_id
    assert (cancel.value_minor, cancel.currency) == (15000, "CLP")
    assert cancel.event_id == f"reservation:{out['booking']['id']}:OrderCanceled"


async def test_cancelling_from_the_console_also_sends_it(db_session, console_world) -> None:
    from nexus_api.services.reservations.core import Actor, cancel_booking, load_ctx

    world = await _world(db_session, console_world)
    await _click(world)
    out = await _book(world)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
        ctx = await load_ctx(s, world["tenant_id"])
        assert ctx is not None
        res = await s.get(Reservation, uuid.UUID(str(out["booking"]["id"])))
        assert res is not None
        await cancel_booking(
            s, ctx, res, by="business", actor=Actor("person", "Lucía"), now=datetime.now(UTC)
        )
        await s.commit()
    assert [e.event_name for e in await _events(world)] == ["Purchase", "OrderCanceled"]


async def test_cancelling_without_an_event_sends_nothing(db_session, console_world) -> None:
    world = await _world(db_session, console_world, measured=False)
    out = await _book(world)
    with (
        tenant_context(world["tenant_id"]),
        customer_context(world["ana"]),
        conversation_context(world["conv"]),
    ):
        await world["registry"].dispatch(
            "reservas.cancel", {"booking_id": out["booking"]["id"]}, whitelist=["reservas.cancel"]
        )
    assert await _events(world) == []


@pytest.mark.parametrize("origin", ["person", "waitlist", "walkin"])
async def test_bookings_not_made_in_the_chat_do_not_enter(
    db_session, console_world, origin: str
) -> None:
    world = await _world(db_session, console_world)
    await _click(world)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
        res = Reservation(
            tenant_id=world["tenant_id"],
            mode="capacity",
            status="confirmed",
            starts_at=datetime.now(UTC) + timedelta(days=2),
            ends_at=datetime.now(UTC) + timedelta(days=2, hours=1),
            origin=origin,
            channel="phone",
            created_by_kind="person",
            price_minor=15000,
            currency="CLP",
            customer_id=world["ana"],
            conversation_id=world["conv"],
        )
        s.add(res)
        await s.flush()
        await enqueue_for_booking(s, res)
        await s.commit()
    assert await _events(world) == []


async def test_an_agent_order_enters_with_the_turns_conversation(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    await _click(world)
    sm = get_sessionmaker()
    with (
        tenant_context(world["tenant_id"]),
        customer_context(world["ana"]),
        conversation_context(world["conv"]),
    ):
        async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
            await enqueue_for_order(s, order_id="1234", total="24990", currency="CLP")
            await s.commit()
    (ev,) = await _events(world)
    assert (ev.event_name, ev.source_kind, ev.source_id) == ("OrderCreated", "woo_order", "1234")
    assert (ev.value_minor, ev.currency) == (24990, "CLP")


async def test_an_order_without_a_turn_does_not_enter(db_session, console_world) -> None:
    world = await _world(db_session, console_world)
    sm = get_sessionmaker()
    with tenant_context(world["tenant_id"]), customer_context(world["ana"]):
        async with sm() as s, tenant_scoped_session(s, world["tenant_id"]):
            await enqueue_for_order(s, order_id="1235", total="100", currency="CLP")
            await s.commit()
    assert await _events(world) == []


async def test_the_woocommerce_hook_enqueues_through_its_own_session(
    db_session, console_world
) -> None:
    """El enganche de ``woocommerce.create_order`` y ``build_checkout_link``
    (``_measure_order``): abre su sesión de herramienta, que confirma al salir, y
    el pedido queda en cola con la conversación del turno."""
    from types import SimpleNamespace

    from nexus_mcp.servers.woocommerce.tools import _measure_order

    world = await _world(db_session, console_world)
    await _click(world)
    with (
        tenant_context(world["tenant_id"]),
        customer_context(world["ana"]),
        conversation_context(world["conv"]),
    ):
        await _measure_order(SimpleNamespace(id=4321, total="12990", currency="CLP"))  # type: ignore[arg-type]
    (ev,) = await _events(world)
    assert (ev.event_name, ev.source_kind, ev.source_id) == ("OrderCreated", "woo_order", "4321")


async def test_measuring_an_order_never_costs_the_order(
    db_session, console_world, monkeypatch
) -> None:
    """Si medir falla, el pedido sigue: ``_measure_order`` no lanza."""
    from types import SimpleNamespace

    from nexus_mcp.servers.woocommerce.tools import _measure_order

    from nexus_api.services import ad_conversions

    async def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("meta down")

    monkeypatch.setattr(ad_conversions, "enqueue_for_order", boom)
    world = await _world(db_session, console_world)
    with (
        tenant_context(world["tenant_id"]),
        customer_context(world["ana"]),
        conversation_context(world["conv"]),
    ):
        await _measure_order(SimpleNamespace(id=1, total="1", currency="CLP"))  # type: ignore[arg-type]
    assert await _events(world) == []
