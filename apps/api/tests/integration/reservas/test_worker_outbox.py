"""Spec 043 — ``reservation-outbox-cron`` (T016, Requisitos 5.6 y 7.6).

Dentro de la ventana de 24 h sale texto; fuera, la plantilla aprobada del
número; sin plantilla, sin teléfono, sin número o con la baja pedida, no sale
nada y el historial lo dice (``notify_failed``). Los errores se reintentan con
espera y, al tercero, la fila queda ``failed``: nunca se reintenta para siempre.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.persistence.messages import upsert_conversation_for_customer
from nexus_worker.streams.reservation_outbox_cron import process_tenant as send_outbox
from nexus_worker.streams.reservations_cron import process_tenant as reservations_tick

from nexus_api.db.models import (
    Conversation,
    Customer,
    MessageDirection,
    MessageStatus,
    Reservation,
    ReservationOutbox,
    WhatsAppOptOut,
)
from nexus_api.services.reservations import core, waitlist
from nexus_api.services.whatsapp_templates import TemplateOut
from tests.conftest import future_day, make_reservas
from tests.integration.reservas._worker import (
    DIGITS,
    PHONE,
    add_line,
    book,
    events,
    local,
    messages,
    outbox,
    scoped,
    when,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BUSINESS = "Client A One"
ALL_TEMPLATES = (
    "reserva_confirmada",
    "reserva_pide_confirmacion",
    "reserva_recordatorio",
    "reserva_cambiada",
    "reserva_cancelada",
    "reserva_hueco_libre",
)


def _approved(*names: str) -> list[TemplateOut]:
    return [
        TemplateOut(id=f"t-{n}", name=n, language="es", status="APPROVED", components=[])
        for n in names
    ]


@pytest.fixture
def templates(monkeypatch) -> dict[str, Any]:
    """Lo que Meta dice de las plantillas del número. Por defecto, todas las de
    Reservas aprobadas; cada prueba puede cambiarlo (o hacer que falle)."""
    state: dict[str, Any] = {"list": _approved(*ALL_TEMPLATES), "error": None, "calls": 0}

    async def _fake_fetch(_session, *, use_cache: bool = True):
        state["calls"] += 1
        if state["error"] is not None:
            raise state["error"]
        return list(state["list"]), "waba-1"

    monkeypatch.setattr("nexus_api.services.whatsapp_templates.fetch_templates", _fake_fetch)
    return state


@pytest.fixture
async def salon(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    out = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    out["channel_id"] = await add_line(db_session, w["tenant_id"])
    return out


async def _send(tenant_id, now) -> int:
    async with scoped(tenant_id) as s:
        return await send_outbox(s, tenant_id, now)


async def _tick(tenant_id, now) -> None:
    async with scoped(tenant_id) as s:
        await reservations_tick(s, tenant_id, now)


async def _open_conversation(tenant_id, channel_id, *, last_inbound_at) -> Conversation:
    async with scoped(tenant_id) as s:
        customer = await s.scalar(sa.select(Customer).where(Customer.identifier == DIGITS))
        assert customer is not None
        conv = await upsert_conversation_for_customer(
            s, channel_id=channel_id, customer_id=customer.id
        )
        conv.last_inbound_at = last_inbound_at
        return conv


async def _row(tenant_id, dedupe_key: str) -> ReservationOutbox:
    rows = [r for r in await outbox(tenant_id) if r.dedupe_key == dedupe_key]
    assert len(rows) == 1, [r.dedupe_key for r in await outbox(tenant_id)]
    return rows[0]


async def _ask(salon, *, status: str = "pending", phone: str | None = PHONE):
    """Una cita de Corte con Marcos y su petición de confirmación encolada."""
    tid = salon["tenant_id"]
    day = future_day(3)
    rid = await book(
        tid,
        day=day,
        at="12:00",
        status=status,
        phone=phone,
        staff=salon["marcos"],
        service=salon["corte"],
    )
    now = local(day, "12:00") - timedelta(hours=23)
    await _tick(tid, now)
    return rid, now, local(day, "12:00")


async def test_inside_the_window_it_goes_as_text(salon, templates) -> None:
    tid = salon["tenant_id"]
    rid, now, start = await _ask(salon)
    conv = await _open_conversation(
        tid, salon["channel_id"], last_inbound_at=now - timedelta(hours=1)
    )

    assert await _send(tid, now) == 1

    msgs = await messages(tid)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg.template_payload is None
    assert msg.conversation_id == conv.id
    assert msg.direction == MessageDirection.OUTBOUND
    assert msg.status == MessageStatus.PENDING
    assert msg.actor_kind == "system"
    assert msg.content == (
        f"Hola, Ana. Te esperamos en {BUSINESS} {when(start)} (Corte con Marcos). "
        "¿Nos confirmas que vienes? Responde SÍ o NO."
    )
    row = await _row(tid, f"ask:{rid}:auto")
    assert row.status == "sent"
    assert row.message_id == msg.id
    assert ("notified", "system", {"kind": "ask_confirmation", "via": "text"}) in await events(
        tid, rid
    )
    assert templates["calls"] == 0  # dentro de la ventana no hace falta preguntar a Meta


async def test_outside_the_window_it_goes_as_the_approved_template(salon, templates) -> None:
    tid = salon["tenant_id"]
    rid, now, start = await _ask(salon, status="confirmed")  # confirmada → recordatorio
    await _open_conversation(tid, salon["channel_id"], last_inbound_at=now - timedelta(hours=30))

    await _send(tid, now)

    [msg] = await messages(tid)
    assert msg.template_payload == {
        "name": "reserva_recordatorio",
        "language": "es",
        "params": {
            "body": {
                "nombre": "Ana",
                "negocio": BUSINESS,
                "cuando": when(start),
                "detalle": "Corte con Marcos",
            }
        },
    }
    assert msg.content.startswith("[template:reserva_recordatorio] Hola, Ana.")
    row = await _row(tid, f"reminder:{rid}")
    assert (row.status, row.message_id) == ("sent", msg.id)
    kinds = [(k, d) for k, _, d in await events(tid, rid)]
    assert ("reminder_sent", {"kind": "reminder", "via": "template"}) in kinds
    assert not [k for k, _ in kinds if k == "notified"]


async def test_a_first_contact_gets_a_conversation_and_the_template(salon, templates) -> None:
    tid = salon["tenant_id"]
    _rid, now, _start = await _ask(salon)

    await _send(tid, now)

    [msg] = await messages(tid)
    assert msg.template_payload["name"] == "reserva_pide_confirmacion"
    async with scoped(tid) as s:
        conv = await s.get(Conversation, msg.conversation_id)
        assert conv is not None
        assert conv.channel_id == salon["channel_id"]


async def test_without_an_approved_template_nothing_goes_out_and_history_says_so(
    salon, templates
) -> None:
    tid = salon["tenant_id"]
    templates["list"] = [
        TemplateOut(name="reserva_pide_confirmacion", language="es", status="PENDING"),
        *_approved("reserva_recordatorio"),
    ]
    rid, now, _start = await _ask(salon)

    await _send(tid, now)

    assert await messages(tid) == []
    row = await _row(tid, f"ask:{rid}:auto")
    assert (row.status, row.skip_reason) == ("skipped", "no_template")
    assert (
        "notify_failed",
        "system",
        {"kind": "ask_confirmation", "why": "no_template"},
    ) in await events(tid, rid)
    # Nada a medias: ni conversación nueva para un mensaje que no salió.
    async with scoped(tid) as s:
        assert (await s.scalar(sa.select(sa.func.count()).select_from(Conversation))) == 0


async def test_without_a_phone_nothing_goes_out_and_history_says_so(salon, templates) -> None:
    tid = salon["tenant_id"]
    day = future_day(3)
    rid = await book(
        tid, day=day, at="12:00", phone=None, staff=salon["marcos"], service=salon["corte"]
    )
    async with scoped(tid) as s:
        await core.enqueue_message(
            s, tenant_id=tid, kind="reminder", dedupe_key=f"reminder:{rid}", reservation_id=rid
        )

    await _send(tid, datetime.now(UTC) + timedelta(minutes=1))

    row = await _row(tid, f"reminder:{rid}")
    assert (row.status, row.skip_reason) == ("skipped", "no_phone")
    assert ("notify_failed", "system", {"kind": "reminder", "why": "no_phone"}) in await events(
        tid, rid
    )


async def test_who_opted_out_is_not_written_to(salon, templates) -> None:
    tid = salon["tenant_id"]
    rid, now, _start = await _ask(salon)
    async with scoped(tid) as s:
        s.add(
            WhatsAppOptOut(
                tenant_id=tid,
                channel_id=salon["channel_id"],
                recipient_phone=DIGITS,
                reason="keyword_stop",
                trigger_keyword="BAJA",
                opted_out_at=now - timedelta(days=10),
            )
        )

    await _send(tid, now)

    assert await messages(tid) == []
    row = await _row(tid, f"ask:{rid}:auto")
    assert (row.status, row.skip_reason) == ("skipped", "opted_out")
    assert any(
        k == "notify_failed" and d["why"] == "opted_out" for k, _, d in await events(tid, rid)
    )


async def test_without_a_whatsapp_line_it_is_skipped(db_session, console_world, templates) -> None:
    w = console_world["a"]
    salon = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    tid = salon["tenant_id"]
    rid, now, _start = await _ask(salon)

    await _send(tid, now)

    row = await _row(tid, f"ask:{rid}:auto")
    assert (row.status, row.skip_reason) == ("skipped", "no_channel")
    assert any(
        k == "notify_failed" and d["why"] == "no_channel" for k, _, d in await events(tid, rid)
    )


async def test_a_question_that_no_longer_applies_is_not_sent(salon, templates) -> None:
    """Confirmó (o se canceló) antes de que saliera: preguntar ya no tiene
    sentido. No es un fallo de aviso: no se apunta ``notify_failed``."""
    tid = salon["tenant_id"]
    rid, now, _start = await _ask(salon)
    async with scoped(tid) as s:
        await s.execute(
            sa.update(Reservation).where(Reservation.id == rid).values(status="confirmed")
        )

    await _send(tid, now)

    assert await messages(tid) == []
    row = await _row(tid, f"ask:{rid}:auto")
    assert (row.status, row.skip_reason) == ("skipped", "stale")
    assert not [k for k, _, _ in await events(tid, rid) if k == "notify_failed"]


async def test_errors_back_off_and_stop_after_three_attempts(salon, templates) -> None:
    tid = salon["tenant_id"]
    templates["error"] = RuntimeError("graph down")
    rid, t0, _start = await _ask(salon)
    key = f"ask:{rid}:auto"

    await _send(tid, t0)
    row = await _row(tid, key)
    assert (row.status, row.attempts) == ("pending", 1)
    assert row.next_attempt_at == t0 + timedelta(minutes=1)
    assert "graph down" in (row.last_error or "")

    await _send(tid, t0 + timedelta(seconds=30))  # todavía no toca
    assert (await _row(tid, key)).attempts == 1

    t1 = t0 + timedelta(minutes=1)
    await _send(tid, t1)
    row = await _row(tid, key)
    assert (row.status, row.attempts) == ("pending", 2)
    assert row.next_attempt_at == t1 + timedelta(minutes=5)

    t2 = t1 + timedelta(minutes=5)
    await _send(tid, t2)
    row = await _row(tid, key)
    assert (row.status, row.attempts) == ("failed", 3)
    assert ("notify_failed", "system", {"kind": "ask_confirmation", "why": "send_failed"}) in (
        await events(tid, rid)
    )

    await _send(tid, t2 + timedelta(hours=1))
    assert (await _row(tid, key)).attempts == 3
    assert await messages(tid) == []


async def test_one_bad_row_does_not_stop_the_others(salon, templates) -> None:
    """Un error en un aviso se queda en esa fila: los demás del lote salen."""
    tid = salon["tenant_id"]
    rid, now, _start = await _ask(salon)
    day = future_day(3)
    other = await book(
        tid,
        day=day,
        at="12:00",
        status="pending",
        phone="+56955556666",
        name="Carla",
        staff=salon["lucia"],
        service=salon["corte"],
    )
    await _tick(tid, now)
    # Carla escribió hace un rato (texto); a Ana le toca plantilla y Meta falla.
    async with scoped(tid) as s:
        carla = await s.scalar(sa.select(Customer).where(Customer.identifier == "56955556666"))
        assert carla is not None
        conv = await upsert_conversation_for_customer(
            s, channel_id=salon["channel_id"], customer_id=carla.id
        )
        conv.last_inbound_at = now - timedelta(minutes=10)
    templates["error"] = RuntimeError("graph down")

    await _send(tid, now)

    assert (await _row(tid, f"ask:{rid}:auto")).status == "pending"
    assert (await _row(tid, f"ask:{other}:auto")).status == "sent"
    assert len(await messages(tid)) == 1


async def test_a_waitlist_offer_says_the_slot_and_the_minutes(salon, templates) -> None:
    tid = salon["tenant_id"]
    day = future_day(3)
    rid = await book(
        tid,
        day=day,
        at="12:00",
        phone="+56955556666",
        name="Carla",
        staff=salon["marcos"],
        service=salon["corte"],
    )
    async with scoped(tid) as s:
        ctx = await core.load_ctx(s, tid)
        assert ctx is not None
        cust = await core.contact_customer(s, ctx, PHONE, "Ana")
        await waitlist.join(
            s,
            ctx,
            waitlist.NewEntry(
                contact_name="Ana",
                contact_phone=PHONE,
                joined_by_kind="person",
                customer_id=cust,
                service_id=salon["corte"],
            ),
        )
    now = datetime.now(UTC)
    async with scoped(tid) as s:
        ctx = await core.load_ctx(s, tid)
        assert ctx is not None
        res = await core.get_booking(s, rid)
        await core.cancel_booking(
            s, ctx, res, by="business", actor=core.Actor("person", "V"), now=now, notify=False
        )
        offer = await waitlist.open_after_cancel(s, ctx, res, now)
        assert offer is not None

    # La fila nace con ``next_attempt_at = now()`` de la base, algo después.
    await _send(tid, now + timedelta(minutes=1))

    [msg] = await messages(tid)
    assert msg.template_payload["name"] == "reserva_hueco_libre"
    assert msg.template_payload["params"]["body"] == {
        "nombre": "Ana",
        "negocio": BUSINESS,
        "cuando": when(local(day, "12:00")),
        "detalle": "Corte con Marcos",
        "minutos": "5",
    }
    assert msg.content == (
        f"[template:reserva_hueco_libre] Mensaje automático de {BUSINESS}: se liberó un hueco "
        f"{when(local(day, '12:00'))} (Corte con Marcos). ¿Lo quieres? Responde SÍ en los "
        "próximos 5 minutos y te lo reservamos."
    )
    [row] = [r for r in await outbox(tid) if r.kind == "offer"]
    assert row.status == "sent"


async def test_what_goes_out_is_metered_like_any_message(salon, templates, monkeypatch) -> None:
    """T042: el aviso de Reservas lo entrega el despachador de salida, que lo mide
    como un ``channel.message`` del cliente, igual que uno del agente. Ningún
    camino propio que se salte el medidor."""
    from nexus_worker.streams import outbound

    from nexus_api.db.base import get_sessionmaker
    from tests.integration.channels.conftest import FakeWhatsAppAdapter

    metered: list[dict[str, Any]] = []

    async def _message(**kw: Any) -> None:
        metered.append(kw)

    monkeypatch.setattr(outbound, "record_channel_message", _message)

    tid = salon["tenant_id"]
    _rid, now, _start = await _ask(salon)
    conv = await _open_conversation(
        tid, salon["channel_id"], last_inbound_at=now - timedelta(hours=1)
    )
    assert await _send(tid, now) == 1

    adapter = FakeWhatsAppAdapter()
    await outbound._drain_tenant(get_sessionmaker(), tid, {"meta": adapter}, batch_size=10)

    (msg,) = await messages(tid)
    assert msg.status == MessageStatus.SENT
    assert len(adapter.text_calls) == 1
    (measure,) = metered
    assert measure["tenant_id"] == tid
    assert measure["conversation_id"] == conv.id
    assert measure["provider_message_id"] == msg.provider_message_id
