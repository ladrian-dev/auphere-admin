"""Spec 043 — ``reservations-cron`` con el reloj fijado (T014, Requisito 7).

Pedir confirmación y recordar a su hora, una sola vez; liberar en Aforo la que
sigue sin confirmar 1 h antes; pasar a ``done`` lo terminado en los dos modos;
caducar entradas de la lista; abrir ofertas de Aforo cuando hay sitio.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.streams import reservations_cron
from nexus_worker.streams.reservations_cron import process_tenant

from nexus_api.db.models import (
    Reservation,
    ReservationOffer,
    ReservationOfferCandidate,
    ReservationOutbox,
    ReservationSettings,
    ReservationWaitlist,
)
from nexus_api.services.reservations import automation, core, waitlist
from tests.conftest import future_day, make_reservas
from tests.integration.reservas._worker import (
    book,
    events,
    local,
    outbox,
    reservation,
    scoped,
    set_status,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def salon(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


@pytest.fixture
async def resto(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], mode="capacity"
    )


async def _tick(tenant_id, now) -> Any:
    async with scoped(tenant_id) as s:
        return await process_tenant(s, tenant_id, now)


async def _settings(tenant_id, **values: Any) -> None:
    async with scoped(tenant_id) as s:
        await s.execute(
            sa.update(ReservationSettings)
            .where(ReservationSettings.tenant_id == tenant_id)
            .values(**values)
        )


async def _join(tenant_id, **entry: Any) -> ReservationWaitlist:
    async with scoped(tenant_id) as s:
        ctx = await core.load_ctx(s, tenant_id)
        assert ctx is not None
        return await waitlist.join(
            s,
            ctx,
            waitlist.NewEntry(
                contact_name=entry.pop("name", "Bea"),
                contact_phone=entry.pop("phone", "+56933334444"),
                joined_by_kind="person",
                **entry,
            ),
        )


async def _offers(tenant_id) -> list[ReservationOffer]:
    async with scoped(tenant_id) as s:
        rows = await s.execute(sa.select(ReservationOffer).order_by(ReservationOffer.starts_at))
        return list(rows.scalars())


# ── pedir confirmación y recordar ───────────────────────────────────────────


async def test_services_asks_for_confirmation_24h_before_and_only_once(salon) -> None:
    tid = salon["tenant_id"]
    day = future_day(3)
    rid = await book(
        tid, day=day, at="12:00", status="pending", staff=salon["marcos"], service=salon["corte"]
    )
    start = local(day, "12:00")

    await _tick(tid, start - timedelta(hours=24, minutes=1))
    assert await outbox(tid) == []

    asked_at = start - timedelta(hours=23, minutes=59)
    await _tick(tid, asked_at)
    await _tick(tid, asked_at + timedelta(minutes=1))
    await _tick(tid, asked_at + timedelta(hours=2))

    rows = await outbox(tid)
    assert [(r.kind, r.dedupe_key, r.status) for r in rows] == [
        ("ask_confirmation", f"ask:{rid}:auto", "pending")
    ]
    assert rows[0].reservation_id == rid
    res = await reservation(tid, rid)
    assert res.status == "pending"
    assert res.confirmation_requested_at == asked_at
    asks = [e for e in await events(tid, rid) if e[0] == "confirmation_requested"]
    assert len(asks) == 1
    assert asks[0][1] == "system"
    # La clave que el cron busca en SQL es la misma que escribe: lo ya
    # preguntado ni se vuelve a mirar.
    async with scoped(tid) as s:
        for kind in ("ask_confirmation", "reminder"):
            rendered = await s.scalar(
                sa.select(automation._automatic_key_sql(kind)).where(Reservation.id == rid)
            )
            assert rendered == automation.automatic_key(kind, rid)


async def test_services_reminds_the_confirmed_ones_and_when_confirmation_is_off(salon) -> None:
    tid = salon["tenant_id"]
    day = future_day(3)
    confirmed = await book(tid, day=day, at="12:00", staff=salon["marcos"], service=salon["corte"])
    pending = await book(
        tid, day=day, at="13:00", status="pending", staff=salon["marcos"], service=salon["corte"]
    )
    await _settings(tid, confirm_enabled=False)

    now = local(day, "13:00") - timedelta(hours=23)
    await _tick(tid, now)
    await _tick(tid, now + timedelta(minutes=5))

    rows = sorted((r.dedupe_key, r.kind) for r in await outbox(tid))
    assert rows == sorted(
        [(f"reminder:{confirmed}", "reminder"), (f"reminder:{pending}", "reminder")]
    )
    # El recordatorio no es una petición de confirmación: el historial no la
    # apunta (el «recordatorio enviado» lo escribe el envío).
    assert not [e for e in await events(tid, confirmed) if e[0] == "confirmation_requested"]
    assert (await reservation(tid, pending)).confirmation_requested_at is None


async def test_services_without_reminders_nor_confirmation_sends_nothing(salon) -> None:
    tid = salon["tenant_id"]
    day = future_day(3)
    await book(tid, day=day, at="12:00", staff=salon["marcos"], service=salon["corte"])
    await _settings(tid, confirm_enabled=False, reminder_enabled=False)
    await _tick(tid, local(day, "12:00") - timedelta(hours=1))
    assert await outbox(tid) == []


async def test_nobody_to_write_to_is_not_asked(salon) -> None:
    tid = salon["tenant_id"]
    day = future_day(3)
    await book(
        tid,
        day=day,
        at="12:00",
        status="pending",
        phone=None,
        staff=salon["marcos"],
        service=salon["corte"],
    )
    await _tick(tid, local(day, "12:00") - timedelta(hours=2))
    assert await outbox(tid) == []


async def test_a_booking_made_inside_the_window_is_not_asked_again(salon) -> None:
    """Quien reservó hace un rato acaba de hablar con el negocio: la pregunta
    automática es para las reservas que ya existían cuando tocaba hacerla."""
    tid = salon["tenant_id"]
    day = future_day(3)
    start = local(day, "12:00")
    rid = await book(
        tid, day=day, at="12:00", status="pending", staff=salon["marcos"], service=salon["corte"]
    )
    async with scoped(tid) as s:
        await s.execute(
            sa.update(Reservation)
            .where(Reservation.id == rid)
            .values(created_at=start - timedelta(hours=10))
        )
    await _tick(tid, start - timedelta(hours=5))
    assert await outbox(tid) == []


@pytest.mark.parametrize(
    ("confirm_when", "before", "after"),
    [
        ("24h", "-24:01", "-23:59"),
        ("same_day_12", "11:59", "12:00"),
        ("3h", "15:59", "16:00"),
    ],
)
async def test_capacity_asks_when_the_business_said(
    resto, confirm_when: str, before: str, after: str
) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    rid = await book(tid, day=day, at="19:00", status="pending", party=4)
    await _settings(tid, confirm_when=confirm_when)
    start = local(day, "19:00")

    def at(raw: str):
        if raw.startswith("-"):
            h, m = raw[1:].split(":")
            return start - timedelta(hours=int(h), minutes=int(m))
        return local(day, raw)

    await _tick(tid, at(before))
    assert await outbox(tid) == []
    await _tick(tid, at(after))
    await _tick(tid, at(after) + timedelta(minutes=1))
    rows = await outbox(tid)
    assert [(r.kind, r.dedupe_key) for r in rows] == [("ask_confirmation", f"ask:{rid}:auto")]


async def test_capacity_does_not_remind_confirmed_bookings(resto) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    await book(tid, day=day, at="19:00", party=4)
    await _tick(tid, local(day, "19:00") - timedelta(hours=2))
    assert await outbox(tid) == []


# ── liberar (Aforo) ─────────────────────────────────────────────────────────


async def _mark_sent(tenant_id, res_id) -> None:
    async with scoped(tenant_id) as s:
        await s.execute(
            sa.update(ReservationOutbox)
            .where(
                ReservationOutbox.reservation_id == res_id,
                ReservationOutbox.kind == "ask_confirmation",
            )
            .values(status="sent")
        )


async def test_capacity_releases_the_unconfirmed_one_hour_before(resto) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    start = local(day, "19:00")
    asked = await book(tid, day=day, at="19:00", status="pending", party=54)
    never_asked = await book(
        tid, day=day, at="19:00", status="pending", party=2, phone="+56955556666", name="Carla"
    )
    await _tick(tid, start - timedelta(hours=23))
    await _mark_sent(tid, asked)
    # Lo de Carla no salió (nadie le preguntó de verdad): no se libera.
    async with scoped(tid) as s:
        await s.execute(
            sa.update(ReservationOutbox)
            .where(ReservationOutbox.reservation_id == never_asked)
            .values(status="skipped", skip_reason="no_template")
        )
    await _settings(tid, waitlist_lead_minutes=60)
    # Alguien espera a las 20:00 y hoy no cabe: 54 siguen dentro.
    await _join(tid, party_size=6, desired_day=day, desired_time=local(day, "20:00").time())

    await _tick(tid, start - timedelta(minutes=61))
    assert (await reservation(tid, asked)).status == "pending"
    assert await _offers(tid) == []

    await _tick(tid, start - timedelta(minutes=59))
    res = await reservation(tid, asked)
    assert res.status == "cancelled"
    assert res.cancelled_by == "system"
    assert res.cancel_cause == "release_unconfirmed"
    kinds = [(k, a) for k, a, _ in await events(tid, asked)]
    assert ("cancelled", "system") in kinds
    assert ("released", "system") in kinds
    assert f"cancelled:{asked}" in {r.dedupe_key for r in await outbox(tid)}
    assert (await reservation(tid, never_asked)).status == "pending"
    # El sitio que deja vuelve a la lista: a las 20:00 ya caben los 6.
    offers = await _offers(tid)
    assert [(o.status, o.starts_at) for o in offers] == [("running", local(day, "20:00"))]

    # Una segunda pasada no hace nada más.
    await _tick(tid, start - timedelta(minutes=58))
    assert [k for k, _, _ in await events(tid, asked)].count("released") == 1


async def test_capacity_keeps_unconfirmed_bookings_when_release_is_off(resto) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    start = local(day, "19:00")
    rid = await book(tid, day=day, at="19:00", status="pending", party=4)
    await _tick(tid, start - timedelta(hours=23))
    await _mark_sent(tid, rid)
    await _settings(tid, release_unconfirmed=False)
    await _tick(tid, start - timedelta(minutes=30))
    assert (await reservation(tid, rid)).status == "pending"


# ── terminar ────────────────────────────────────────────────────────────────


async def test_services_marks_done_what_ended(salon) -> None:
    tid = salon["tenant_id"]
    day = future_day(3)
    ended_pending = await book(
        tid, day=day, at="12:00", status="pending", staff=salon["marcos"], service=salon["corte"]
    )
    ended_confirmed = await book(
        tid, day=day, at="12:00", staff=salon["lucia"], service=salon["corte"]
    )
    running = await book(tid, day=day, at="12:30", staff=salon["marcos"], service=salon["corte"])
    cancelled = await book(tid, day=day, at="11:00", staff=salon["marcos"], service=salon["corte"])
    await set_status(tid, cancelled, "cancelled")

    await _tick(tid, local(day, "12:30"))

    assert (await reservation(tid, ended_pending)).status == "done"
    assert (await reservation(tid, ended_confirmed)).status == "done"
    assert (await reservation(tid, running)).status == "confirmed"
    assert (await reservation(tid, cancelled)).status == "cancelled"
    assert ("done", "system", {}) in await events(tid, ended_pending)
    assert (await reservation(tid, ended_pending)).version == 2


async def test_capacity_marks_done_only_who_arrived(resto) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    arrived = await book(tid, day=day, at="12:00", party=2)
    await set_status(tid, arrived, "arrived")
    never_came = await book(tid, day=day, at="12:00", party=2, phone="+56955556666")

    await _tick(tid, local(day, "13:29"))
    assert (await reservation(tid, arrived)).status == "arrived"

    await _tick(tid, local(day, "13:30"))
    assert (await reservation(tid, arrived)).status == "done"
    # La confirmada que nunca llegó no se marca sola: el «No vino» es del negocio.
    assert (await reservation(tid, never_came)).status == "confirmed"


# ── lista de espera ─────────────────────────────────────────────────────────


async def test_waitlist_entries_expire_when_their_day_passed(resto) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    old = await _join(tid, party_size=2, desired_day=day, desired_time=local(day, "19:00").time())
    # Más allá de mañana: el cron no le abre oferta y sigue esperando.
    later = await _join(
        tid,
        party_size=2,
        desired_day=day + timedelta(days=3),
        desired_time=local(day, "19:00").time(),
    )

    await _tick(tid, local(day + timedelta(days=1), "10:00"))

    async with scoped(tid) as s:
        status = dict(
            (await s.execute(sa.select(ReservationWaitlist.id, ReservationWaitlist.status))).all()
        )
    assert status[old.id] == "expired"
    assert status[later.id] == "waiting"


async def test_capacity_opens_one_offer_per_slot_with_fifteen_minutes(resto) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    at = local(day, "19:00").time()
    first = await _join(tid, party_size=4, desired_day=day, desired_time=at, name="Bea")
    second = await _join(
        tid, party_size=2, desired_day=day, desired_time=at, name="Dani", phone="+56977778888"
    )
    now = local(day, "08:00")

    await _tick(tid, now)
    await _tick(tid, now + timedelta(minutes=1))

    offers = await _offers(tid)
    assert len(offers) == 1
    offer = offers[0]
    assert offer.status == "running"
    assert offer.starts_at == local(day, "19:00")
    assert offer.window_minutes == 15
    async with scoped(tid) as s:
        cands = (
            (
                await s.execute(
                    sa.select(ReservationOfferCandidate).order_by(
                        ReservationOfferCandidate.position
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [(c.waitlist_id, c.status) for c in cands] == [
        (first.id, "waiting"),
        (second.id, "queued"),
    ]
    assert cands[0].deadline_at == now + timedelta(minutes=15)
    assert [r.kind for r in await outbox(tid)] == ["offer"]


async def test_capacity_does_not_offer_inside_the_lead_time(resto) -> None:
    tid = resto["tenant_id"]
    day = future_day(3)
    await _join(tid, party_size=2, desired_day=day, desired_time=local(day, "19:00").time())
    await _tick(tid, local(day, "17:30"))  # faltan 90 min; la antelación es de 120
    assert await _offers(tid) == []
    await _join(
        tid,
        party_size=2,
        desired_day=day,
        desired_time=local(day, "19:30").time(),
        phone="+56977778888",
    )
    await _tick(tid, local(day, "17:30"))  # 120 min justos: sí
    assert [o.starts_at for o in await _offers(tid)] == [local(day, "19:30")]


# ── a quién recorre el cron ─────────────────────────────────────────────────


async def test_cron_pass_covers_clients_with_reservas_settings(db_session, console_world) -> None:
    """Un cliente con ajustes y sin el módulo sigue recibiendo lo comprometido
    (sus reservas futuras se recuerdan) pero no se le abren ofertas nuevas; un
    cliente sin Reservas no se toca."""
    a = console_world["a"]
    w = await make_reservas(
        db_session,
        partner_id=a["partner_id"],
        tenant_id=a["tenant_id"],
        mode="capacity",
        modules=("panel", "inbox", "usage"),
    )
    tid = w["tenant_id"]
    day = future_day(3)
    rid = await book(tid, day=day, at="19:00", status="pending", party=4)
    await _join(
        tid,
        party_size=2,
        desired_day=day,
        desired_time=local(day, "19:30").time(),
        phone="+56977778888",
    )

    await reservations_cron.cron_pass(now=local(day, "08:00"))

    assert [r.dedupe_key for r in await outbox(tid)] == [f"ask:{rid}:auto"]
    assert await _offers(tid) == []
    assert await outbox(console_world["b"]["tenant_id"]) == []
