"""Spec 083 (T002) — ``GET /console/clients/{ref}/report?from=&to=``.

Una siembra que fija cada bloque del informe de un cliente de Caracas:

- **conversaciones**: ciclos con mensaje del contacto, por su día local; ni el
  Playground, ni lo importado, ni un ciclo que empezó antes del periodo, ni un
  aviso que nadie contestó;
- **con persona**, por historial: Bandeja (evento y auditoría, una vez), panel de
  operador, eco de coexistencia, escalado del agente, puerta y freno;
- **primera respuesta**: hasta que el proveedor aceptó el envío del agente;
- **incidencias**: el freno que pasó la conversación es una, y el texto del
  agente nunca sale;
- **agenda**, **recordatorios** y **gasto**.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    ClientAccess,
    ClientWallet,
    ClientWalletEntry,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Reservation,
    ReservationEvent,
    ReservationOutbox,
    ReservationSettings,
)
from nexus_api.services.console_traffic import QA_PLAYGROUND_PROVIDER
from nexus_api.services.wallet.bags import as_client

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CARACAS = ZoneInfo("America/Caracas")
CANARY = "CANARY-Roxana-no-me-gusta"
TODAY = datetime.now(CARACAS).date()
BASE = TODAY - timedelta(days=10)
#: Mediodía del día base en Caracas.
T = datetime(BASE.year, BASE.month, BASE.day, 12, 0, tzinfo=CARACAS).astimezone(UTC)
DAY_FROM = BASE - timedelta(days=3)
DAY_TO = BASE + timedelta(days=3)
SINCE = datetime(DAY_FROM.year, DAY_FROM.month, DAY_FROM.day, tzinfo=CARACAS).astimezone(UTC)
UNIT = 1_000_000


def s(seconds: float) -> timedelta:
    return timedelta(seconds=seconds)


def m(minutes: float) -> timedelta:
    return timedelta(minutes=minutes)


def h(hours: float) -> timedelta:
    return timedelta(hours=hours)


async def _scoped(db: Any, tenant_id: uuid.UUID) -> None:
    await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
    await db.execute(text("SET LOCAL ROLE nexus_app"))


class Pilot:
    """Un cliente de Caracas con su número de WhatsApp y su Playground."""

    def __init__(self, db: Any, tenant_id: uuid.UUID, partner_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.partner_id = partner_id
        self.channel_id = uuid.uuid4()
        self.playground_id = uuid.uuid4()

    async def setup(self, *, zone: str = "America/Caracas") -> Pilot:
        async with self.db.begin():
            await self.db.execute(
                text("UPDATE tenants SET timezone = :z WHERE id = :t"),
                {"z": zone, "t": str(self.tenant_id)},
            )
            await _scoped(self.db, self.tenant_id)
            for cid, provider in (
                (self.channel_id, "meta"),
                (self.playground_id, QA_PLAYGROUND_PROVIDER),
            ):
                self.db.add(
                    Channel(
                        id=cid,
                        tenant_id=self.tenant_id,
                        type=ChannelType.WHATSAPP,
                        provider=provider,
                        provider_identifier=f"+5699{uuid.uuid4().int % 10**7:07d}",
                        status=ChannelStatus.ACTIVE,
                        config={"phone_number_id": "PN"},
                    )
                )
        return self

    async def conversation(self, created: datetime, *, playground: bool = False) -> uuid.UUID:
        customer, conv = uuid.uuid4(), uuid.uuid4()
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                Customer(
                    id=customer,
                    tenant_id=self.tenant_id,
                    identifier=f"+5691{uuid.uuid4().int % 10**7:07d}",
                    name="Ana Pérez",
                )
            )
            await self.db.flush()
            self.db.add(
                Conversation(
                    id=conv,
                    tenant_id=self.tenant_id,
                    channel_id=self.playground_id if playground else self.channel_id,
                    customer_id=customer,
                    status=ConversationStatus.OPEN,
                    created_at=created,
                )
            )
        return conv

    async def msg(
        self,
        conv: uuid.UUID,
        at: datetime,
        *,
        out: bool = False,
        actor: str | None = None,
        origin: str | None = None,
        status: MessageStatus = MessageStatus.SENT,
        latency_ms: int | None = None,
    ) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                Message(
                    tenant_id=self.tenant_id,
                    conversation_id=conv,
                    direction=MessageDirection.OUTBOUND if out else MessageDirection.INBOUND,
                    status=status,
                    content=f"{CANARY} mensaje",
                    tool_calls=[],
                    actor_kind=actor,
                    origin=origin,
                    latency_ms=latency_ms,
                    created_at=at,
                )
            )

    async def contact(self, conv: uuid.UUID, at: datetime) -> None:
        await self.msg(conv, at)

    async def agent(self, conv: uuid.UUID, at: datetime, **kw: Any) -> None:
        await self.msg(conv, at, out=True, actor="agent", origin="agent", **kw)

    async def event(
        self,
        conv: uuid.UUID,
        kind: str,
        actor: str,
        at: datetime,
        payload: dict[str, Any] | None = None,
    ) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                ConversationEvent(
                    tenant_id=self.tenant_id,
                    conversation_id=conv,
                    kind=kind,
                    actor=actor,
                    payload=payload or {},
                    created_at=at,
                )
            )

    async def audit(
        self, conv: uuid.UUID, action: str, at: datetime, after: dict[str, Any] | None = None
    ) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                AuditLog(
                    tenant_id=self.tenant_id,
                    actor="system:worker",
                    action=action,
                    target=f"conversation:{conv}",
                    after_json=after,
                    created_at=at,
                )
            )

    async def reservas(self) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(ReservationSettings(tenant_id=self.tenant_id, mode="services"))

    async def reservation(self) -> uuid.UUID:
        rid = uuid.uuid4()
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                Reservation(
                    id=rid,
                    tenant_id=self.tenant_id,
                    # Aforo: una reserva de servicios exige su servicio y su profesional.
                    mode="capacity",
                    status="confirmed",
                    starts_at=T + timedelta(days=2),
                    ends_at=T + timedelta(days=2, hours=1),
                    origin="agent",
                    channel="whatsapp",
                    created_by_kind="agent",
                    contact_name="Ana Pérez",
                    created_at=T,
                )
            )
        return rid

    async def booking_event(
        self, rid: uuid.UUID, kind: str, actor: str, at: datetime, name: str | None = None
    ) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                ReservationEvent(
                    tenant_id=self.tenant_id,
                    reservation_id=rid,
                    kind=kind,
                    actor_kind=actor,
                    actor_name=name,
                    data={},
                    created_at=at,
                )
            )

    async def notice(
        self, rid: uuid.UUID, kind: str, status: str, at: datetime, skip: str | None = None
    ) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                ReservationOutbox(
                    tenant_id=self.tenant_id,
                    reservation_id=rid,
                    kind=kind,
                    dedupe_key=f"{kind}:{uuid.uuid4().hex}",
                    status=status,
                    skip_reason=skip,
                    created_at=at - m(1),
                    updated_at=at,
                )
            )

    async def spent(self, kind: str, amount: int, at: datetime) -> None:
        async with self.db.begin():
            await apply_partner_to_session(self.db, self.partner_id)
            await as_client(self.db, self.tenant_id)
            if await self.db.get(ClientWallet, self.tenant_id) is None:
                self.db.add(
                    ClientWallet(
                        tenant_id=self.tenant_id,
                        partner_id=self.partner_id,
                        currency="USD",
                        balance_micros=100 * UNIT,
                        month=TODAY.replace(day=1),
                    )
                )
                await self.db.flush()
            self.db.add(
                ClientWalletEntry(
                    tenant_id=self.tenant_id,
                    partner_id=self.partner_id,
                    kind=kind,
                    amount_micros=-amount,
                    balance_after_micros=50 * UNIT,
                    currency="USD",
                    usage_ref=f"channel:{uuid.uuid4().hex[:8]}",
                    created_at=at,
                )
            )


async def _report(
    client: Any, w: dict[str, Any], day_from: date = DAY_FROM, day_to: date = DAY_TO
) -> Any:
    return await client.get(
        f"/console/clients/{w['ref']}/report",
        params={"from": day_from.isoformat(), "to": day_to.isoformat()},
        headers=w["headers"](),
    )


def _walk_keys(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _walk_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _walk_keys(v)}
    return set()


async def _seed(p: Pilot) -> None:
    # A — dos ciclos sin persona: resuelto por inactividad y vuelve al día siguiente.
    a = await p.conversation(T)
    await p.contact(a, T)
    await p.agent(a, T + s(5))
    await p.event(a, "resolved", "system", T + h(1), {"reason": "inactivity"})
    await p.event(a, "reopened", "contact", T + timedelta(days=1))
    await p.contact(a, T + timedelta(days=1))
    await p.agent(a, T + timedelta(days=1) + s(55), latency_ms=15_000)  # 70 s
    # B — tomada desde la Bandeja (evento + auditoría) y devuelta: con persona, una vez.
    b = await p.conversation(T + m(1))
    await p.contact(b, T + m(1))
    await p.agent(b, T + m(1) + s(3))
    await p.event(b, "takeover", "client:ana@example.com", T + m(10))
    await p.audit(b, "inbox.takeover", T + m(10))
    await p.event(b, "released", "client:ana@example.com", T + m(20))
    # C — tomada desde el panel de operador; el envío del agente falló.
    c = await p.conversation(T + h(2))
    await p.contact(c, T + h(2))
    await p.agent(c, T + h(2) + s(2), status=MessageStatus.FAILED)
    await p.audit(c, "conversation.takeover", T + h(2) + m(5))
    # D — una persona contestó desde la app de WhatsApp Business (coexistencia).
    d = await p.conversation(T + h(3))
    await p.contact(d, T + h(3))
    await p.agent(d, T + h(3) + s(4))
    await p.msg(d, T + h(3) + m(1), out=True, origin="business_app_echo")
    # E — el agente pidió una persona con texto libre; se resolvió.
    e = await p.conversation(T + h(4))
    await p.contact(e, T + h(4))
    await p.agent(e, T + h(4) + s(6))
    await p.event(e, "escalated", "agent", T + h(4) + m(1), {"reason": CANARY})
    await p.event(e, "resolved", "client:ana@example.com", T + h(5))
    # F — sin saldo: la puerta no dejó contestar.
    f = await p.conversation(T + h(6))
    await p.contact(f, T + h(6))
    await p.event(f, "escalated", "system", T + h(6), {"reason": "no_balance"})
    # G — el freno paró una respuesta y el agente la rehízo.
    g = await p.conversation(T + h(7))
    await p.contact(g, T + h(7))
    await p.audit(g, "agent.booking_brake", T + h(7) + s(7), {"outcome": "retried"})
    await p.agent(g, T + h(7) + s(8))
    # H — el freno pasó la conversación: auditoría + escalado booking_unbacked.
    hh = await p.conversation(T + h(8))
    await p.contact(hh, T + h(8))
    await p.audit(hh, "agent.booking_brake", T + h(8) + s(9), {"outcome": "handed_off"})
    await p.event(hh, "escalated", "system", T + h(8) + s(9), {"reason": "booking_unbacked"})
    # I — el ciclo empezó antes del periodo: no es del periodo.
    i = await p.conversation(SINCE - timedelta(days=2))
    await p.contact(i, SINCE - timedelta(days=2))
    await p.contact(i, T + h(9))
    # J — un aviso la reabrió y nadie contestó: no es una conversación.
    j = await p.conversation(SINCE - timedelta(days=5))
    await p.contact(j, SINCE - timedelta(days=5))
    await p.event(j, "resolved", "system", SINCE - timedelta(days=4))
    await p.event(j, "reopened", "system", T + h(10))
    await p.msg(j, T + h(10), out=True, actor="system", origin="system")
    # K — 23:30 en Caracas: cuenta en su día local.
    late = datetime(BASE.year, BASE.month, BASE.day, 23, 30, tzinfo=CARACAS).astimezone(UTC)
    k = await p.conversation(late)
    await p.contact(k, late)
    await p.agent(k, late + s(4))
    # Playground e importado: no cuentan.
    pg = await p.conversation(T, playground=True)
    await p.contact(pg, T)
    imp = await p.conversation(T + h(11))
    await p.msg(imp, T + h(11), origin="history_import")


async def test_the_report_of_a_pilot(client, db_session, console_world) -> None:
    w = console_world["a"]
    p = await Pilot(db_session, w["tenant_id"], w["partner_id"]).setup()
    await _seed(p)

    r = await _report(client, w)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timezone"] == "America/Caracas"
    assert body["from"] == DAY_FROM.isoformat() and body["to"] == DAY_TO.isoformat()
    assert body["targets"] == {
        "without_person_pct": 70,
        "first_response_pct": 95,
        "first_response_seconds": 60,
    }

    conv = body["conversations"]
    assert (conv["total"], conv["without_person"], conv["with_person"]) == (10, 3, 7)
    assert conv["without_person_pct"] == 30.0
    series = {row["day"]: row for row in conv["series"]}
    assert len(series) == 7
    assert series[BASE.isoformat()] == {
        "day": BASE.isoformat(),
        "without_person": 2,
        "with_person": 7,
    }
    nxt = (BASE + timedelta(days=1)).isoformat()
    assert series[nxt] == {"day": nxt, "without_person": 1, "with_person": 0}

    first = body["first_response"]
    assert first == {
        "answered": 7,
        "within_target": 6,
        "within_target_pct": 85.7,
        "median_seconds": 5,
        "p90_seconds": 70,
        "unanswered": 3,
    }

    inc = body["incidents"]
    assert (inc["total"], inc["resolved"], inc["open"]) == (4, 1, 3)
    assert [(c["cause"], c["total"], c["resolved"]) for c in inc["by_cause"]] == [
        ("booking_brake", 1, 0),
        ("booking_unbacked", 1, 0),
        ("escalated", 1, 1),
        ("no_balance", 1, 0),
    ]
    assert [i["cause"] for i in inc["items"]] == [
        "booking_unbacked",
        "booking_brake",
        "no_balance",
        "escalated",
    ]
    assert inc["items"][-1]["resolved_at"] is not None and inc["truncated"] is False
    assert body["booking_brake"] == {"stopped": 2, "corrected": 1, "handed_over": 1}

    # Sin Reservas no hay agenda; sin bolsa, el gasto es cero, no «no se pudo leer».
    assert body["agenda"] is None
    assert body["spend"]["total"] == {"amount_micros": 0, "currency": "USD"}
    # Ni palabras, ni el motivo libre del agente, ni datos del contacto.
    assert CANARY not in r.text and "Ana" not in r.text
    assert not _walk_keys(body) & {"content", "text", "reason", "name", "phone", "identifier"}


async def test_agenda_reminders_and_spend(client, db_session, console_world) -> None:
    w = console_world["a"]
    p = await Pilot(db_session, w["tenant_id"], w["partner_id"]).setup()
    conv = await p.conversation(T)
    await p.contact(conv, T)
    await p.reservas()
    r1, r2, r3 = await p.reservation(), await p.reservation(), await p.reservation()
    await p.booking_event(r1, "created", "agent", T)
    await p.booking_event(r2, "created", "person", T, "Ana")
    await p.booking_event(r3, "created", "system", T, "Paso a Reservas")
    await p.booking_event(r1, "moved", "agent", T + h(1))
    # El agente canceló: antes de la 080 se graba como «customer».
    await p.booking_event(r1, "cancelled", "customer", T + h(2))
    # El cliente dijo «no» a la confirmación: los dos eventos, a la misma hora.
    await p.booking_event(r2, "replied_no", "customer", T + h(3))
    await p.booking_event(r2, "cancelled", "customer", T + h(3))
    await p.booking_event(r3, "cancelled", "system", T + h(4))
    # Fuera del periodo: no cuenta.
    await p.booking_event(r1, "created", "agent", SINCE - h(1))
    for status in ("sent", "sent", "failed"):
        await p.notice(r1, "reminder", status, T + h(5))
    await p.notice(r1, "reminder", "pending", T + h(5))
    await p.notice(r2, "ask_confirmation", "skipped", T + h(5), "no_window")
    await p.notice(r2, "ask_confirmation", "skipped", T + h(5), "stale")
    await p.spent("debit_turn", 2_500_000, T)
    await p.spent("debit_tests", 500_000, T + h(1))
    await p.spent("debit_turn", 9_000_000, SINCE - h(1))

    r = await _report(client, w)
    assert r.status_code == 200, r.text
    body = r.json()
    agenda = body["agenda"]
    assert agenda["created"] == {"agent": 1, "person": 1, "customer": 0, "total": 2}
    assert agenda["moved"] == {"agent": 1, "person": 0, "customer": 0, "total": 1}
    assert agenda["cancelled"] == {"agent": 1, "person": 0, "customer": 1, "total": 2}
    assert agenda["released"] == 1
    assert agenda["reminders"] == [
        {"kind": "reminder", "sent": 2, "failed": 1, "skipped": 0},
        {"kind": "ask_confirmation", "sent": 0, "failed": 0, "skipped": 1},
    ]
    spend = body["spend"]
    assert spend["currency"] == "USD"
    assert spend["total"]["amount_micros"] == 3_000_000
    assert spend["conversations"]["amount_micros"] == 2_500_000
    assert spend["client_tests"]["amount_micros"] == 500_000
    assert spend["per_conversation"]["amount_micros"] == 3_000_000
    assert spend["approx"] is False


async def test_spend_that_cannot_be_read_is_partial(
    client, db_session, console_world, monkeypatch
) -> None:
    from nexus_api.services import client_report

    async def broken(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("ledger down")

    monkeypatch.setattr(client_report.usage_lines, "spend", broken)
    w = console_world["a"]
    p = await Pilot(db_session, w["tenant_id"], w["partner_id"]).setup()
    conv = await p.conversation(T)
    await p.contact(conv, T)
    r = await _report(client, w)
    assert r.status_code == 200, r.text
    assert r.json()["spend"] is None
    assert r.json()["conversations"]["total"] == 1


async def test_an_empty_period(client, console_world) -> None:
    r = await _report(client, console_world["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversations"]["total"] == 0
    assert body["conversations"]["without_person_pct"] is None
    assert body["first_response"]["within_target_pct"] is None
    assert body["first_response"]["median_seconds"] is None
    assert body["incidents"]["total"] == 0 and body["incidents"]["items"] == []
    assert body["spend"]["per_conversation"] is None
    assert body["autoclose"] is False
    assert body["timezone"] == "UTC"


async def test_today_runs_until_now(client, console_world) -> None:
    r = await _report(client, console_world["a"], TODAY - timedelta(days=1), TODAY)
    assert r.status_code == 200, r.text
    until = datetime.fromisoformat(r.json()["until"])
    assert until <= datetime.now(UTC)


@pytest.mark.parametrize(
    ("day_from", "day_to", "code"),
    [
        (BASE, BASE - timedelta(days=1), "range_reversed"),
        (BASE - timedelta(days=92), BASE, "range_too_long"),
        (TODAY, TODAY + timedelta(days=2), "range_in_future"),
    ],
)
async def test_impossible_periods(client, console_world, day_from, day_to, code) -> None:
    r = await _report(client, console_world["a"], day_from, day_to)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == {"code": code}


async def test_ninety_two_days_is_allowed(client, console_world) -> None:
    r = await _report(client, console_world["a"], BASE - timedelta(days=91), BASE)
    assert r.status_code == 200, r.text
    assert len(r.json()["conversations"]["series"]) == 92


@pytest.mark.parametrize(("role", "status"), [("billing", 403), ("analyst", 200)])
async def test_who_can_read_it(client, db_session, console_world, role, status) -> None:
    """``conversations:read`` y ``usage:read``: billing no tiene el primero."""
    from tests.conftest import add_console_member

    w = console_world["a"]
    member = await add_console_member(db_session, partner_id=w["partner_id"], role=role)
    r = await client.get(
        f"/console/clients/{w['ref']}/report",
        params={"from": BASE.isoformat(), "to": BASE.isoformat()},
        headers=member["headers"](),
    )
    assert r.status_code == status, r.text


async def test_an_echo_that_opened_the_conversation_counts_as_a_person(
    client, db_session, console_world
) -> None:
    """D15: la persona escribió desde la app del negocio a un contacto nuevo. El eco
    lleva la hora de Meta, segundos antes de la fila que crea; el contacto contesta."""
    w = console_world["a"]
    p = await Pilot(db_session, w["tenant_id"], w["partner_id"]).setup()
    conv = await p.conversation(T)
    await p.msg(conv, T - s(3), out=True, origin="business_app_echo")
    await p.contact(conv, T + m(2))
    await p.agent(conv, T + m(2) + s(4))
    r = await _report(client, w)
    assert r.status_code == 200, r.text
    got = r.json()["conversations"]
    assert (got["total"], got["with_person"]) == (1, 1)


async def test_the_report_says_when_the_client_closes_idle_conversations(
    client, db_session, console_world
) -> None:
    """Historia 2, escenario 2: la página avisa si el cliente **no** cierra por
    inactividad; la API dice si lo hace, con la misma regla que el cron (spec 064)."""
    w = console_world["a"]
    assert (await _report(client, w)).json()["autoclose"] is False
    db_session.add(
        ClientAccess(
            tenant_id=w["tenant_id"],
            partner_id=w["partner_id"],
            enabled=True,
            modules=["inbox"],
            inbox_autoclose_hours=72,
            updated_by="operator:tests",
        )
    )
    await db_session.commit()
    assert (await _report(client, w)).json()["autoclose"] is True


async def test_spend_is_the_clients_row_in_consumo(client, db_session, console_world) -> None:
    """D12: la misma cifra que la fila del cliente en Consumo para el mismo tramo
    (un cliente en UTC y el mes en curso, que es lo que suma Consumo)."""
    w = console_world["a"]
    p = Pilot(db_session, w["tenant_id"], w["partner_id"])
    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    at = max(month_start + s(1), now - s(30))
    await p.spent("debit_turn", 1_250_000, at)
    await p.spent("debit_tests", 250_000, at)
    await p.spent("debit_turn", 7_000_000, month_start - h(1))

    r = await _report(client, w, month_start.date(), now.date())
    assert r.status_code == 200, r.text
    summary = await client.get("/console/usage/summary", headers=w["headers"]())
    assert summary.status_code == 200, summary.text
    (row,) = [c for c in summary.json()["clients"] if c["ref"] == w["ref"]]
    assert r.json()["spend"]["total"] == row["month_spent"]
    assert r.json()["spend"]["total"]["amount_micros"] == 1_500_000
