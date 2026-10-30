"""El mundo simulado del playground y de las pruebas — spec 047, T085 (requisitos 20.1 a 20.4).

Un borrador se prueba con el mismo grafo que atiende el canal, pero contra un
mundo que no es el de verdad:

- **la hora simulada**: por defecto la actual, en la zona del negocio, y se
  puede cambiar (20.2);
- **la agenda simulada**, sembrada desde la ficha (horario, fechas especiales y
  servicios del agente), que las acciones del agente modifican (20.2);
- **lo que habría hecho**: cada herramienta con efecto queda apuntada en el
  lenguaje del negocio (20.3), y nada sale del mundo (20.1).

Es un dato puro y serializable (``to_dict``/``from_dict``): una sesión del
playground vive entre peticiones y una prueba lo inspecciona al final para
comprobar el estado (requisito 21.3: «que la cita existe»).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from nexus_api.services.business.hours import Hours, Shift, SpecialDay, Week, intervals_on

#: Cada cuánto se ofrecen huecos si el servicio no dice su duración.
SLOT_STEP_MIN = 30


@dataclass
class SimService:
    id: str
    name: str
    duration_min: int | None
    bookable: bool
    price: str | None = None


@dataclass
class SimBooking:
    id: str
    service_id: str | None
    service_name: str
    starts_at: str  # ISO, UTC
    duration_min: int
    status: str = "confirmed"  # confirmed | cancelled


@dataclass
class Action:
    """«Lo que habría hecho»: la herramienta, la frase y en qué orden."""

    tool: str
    phrase: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class World:
    timezone: str
    now: str  # ISO, UTC
    week: list[list[list[int]]] | None  # 7 días, cada uno con sus turnos [abre, cierra] en minutos
    specials: list[dict[str, Any]] = field(default_factory=list)
    services: list[SimService] = field(default_factory=list)
    bookings: list[SimBooking] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    bubbles: list[str] = field(default_factory=list)
    escalated: bool = False

    # ── la hora ────────────────────────────────────────────────────────────

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def now_at(self) -> datetime:
        return datetime.fromisoformat(self.now).astimezone(UTC)

    def local_now(self) -> datetime:
        return self.now_at.astimezone(self.tz)

    def set_now(self, at: datetime) -> None:
        if at.tzinfo is None:
            at = at.replace(tzinfo=self.tz)
        self.now = at.astimezone(UTC).isoformat()

    # ── el horario ─────────────────────────────────────────────────────────

    def hours(self) -> Hours:
        week = (
            Week(
                layout="daily",
                days=tuple(tuple(Shift(a, b) for a, b in day) for day in self.week),
            )
            if self.week is not None
            else None
        )
        specials = tuple(
            SpecialDay(
                date_from=date.fromisoformat(s["from"]),
                date_to=date.fromisoformat(s["to"]),
                closed=bool(s["closed"]),
                shifts=tuple(Shift(a, b) for a, b in s.get("shifts") or []),
            )
            for s in self.specials
        )
        return Hours(week=week, specials=specials, timezone=self.timezone)

    # ── la agenda ──────────────────────────────────────────────────────────

    def service(
        self, *, service_id: str | None = None, name: str | None = None
    ) -> SimService | None:
        for svc in self.services:
            if service_id and svc.id == service_id:
                return svc
        if name:
            wanted = name.strip().lower()
            for svc in self.services:
                if svc.name.lower() == wanted or wanted in svc.name.lower():
                    return svc
        return None

    def _taken(self, start: datetime, end: datetime) -> bool:
        for b in self.bookings:
            if b.status != "confirmed":
                continue
            bs = datetime.fromisoformat(b.starts_at)
            be = bs + timedelta(minutes=b.duration_min)
            if start < be and bs < end:
                return True
        return False

    def slots(self, day: date, duration_min: int | None) -> list[str]:
        """Los huecos libres de ``day`` (hora local ``HH:MM``), desde ahora."""
        length = timedelta(minutes=duration_min or SLOT_STEP_MIN)
        step = timedelta(minutes=SLOT_STEP_MIN)
        out: list[str] = []
        for start, end in intervals_on(self.hours(), day):
            at = start
            while at + length <= end:
                if at >= self.now_at and not self._taken(at, at + length):
                    out.append(at.astimezone(self.tz).strftime("%H:%M"))
                at += step
        return out

    def book(
        self, *, day: date, at: str, service: SimService | None, duration_min: int | None
    ) -> SimBooking | None:
        """Reserva si el hueco existe y está libre; ``None`` si no."""
        length = duration_min or (service.duration_min if service else None) or SLOT_STEP_MIN
        if at not in self.slots(day, length):
            return None
        local = datetime.combine(day, time.fromisoformat(at), tzinfo=self.tz)
        booking = SimBooking(
            id=str(uuid.uuid4()),
            service_id=service.id if service else None,
            service_name=service.name if service else "Cita",
            starts_at=local.astimezone(UTC).isoformat(),
            duration_min=length,
        )
        self.bookings.append(booking)
        return booking

    def booking(self, booking_id: str | None) -> SimBooking | None:
        return next((b for b in self.bookings if b.id == booking_id), None)

    def when(self, booking: SimBooking) -> str:
        local = datetime.fromisoformat(booking.starts_at).astimezone(self.tz)
        return f"{local:%d/%m/%Y} a las {local:%H:%M}"

    def agenda(self) -> list[dict[str, Any]]:
        return [
            {
                "id": b.id,
                "service": b.service_name,
                "when": self.when(b),
                "status": b.status,
            }
            for b in self.bookings
        ]

    # ── lo que habría hecho ────────────────────────────────────────────────

    def did(self, tool: str, phrase: str, args: dict[str, Any] | None = None) -> None:
        self.actions.append(Action(tool=tool, phrase=phrase, args=dict(args or {})))

    def final_state(self) -> dict[str, Any]:
        """Lo que una prueba comprueba al final (requisitos 21.3 y 61.4): las citas
        que quedan en la agenda simulada de Reservas (servicio, día y hora en la zona
        del negocio), el escalado (a quién y por qué) y si se pidió un pago."""
        confirmed = [b for b in self.bookings if b.status == "confirmed"]
        items = []
        for b in confirmed:
            local = datetime.fromisoformat(b.starts_at).astimezone(self.tz)
            items.append(
                {
                    "service": b.service_name,
                    "service_id": b.service_id,
                    "date": local.date().isoformat(),
                    "time": local.strftime("%H:%M"),
                }
            )
        handoffs = [a for a in self.actions if a.tool == "escalate.escalate_to_human"]
        reason = next(
            (str(a.args.get("reason")) for a in reversed(handoffs) if a.args.get("reason")),
            None,
        )
        state: dict[str, Any] = {
            "booking": {"created": bool(confirmed), "count": len(confirmed), "items": items},
            "escalated": self.escalated,
            "actions": [a.tool for a in self.actions],
            "payment": {"requested": any(a.tool.startswith("payments.") for a in self.actions)},
        }
        if self.escalated or handoffs:
            # Las pruebas no tienen destinatarios: el escalado va «al equipo» del
            # canal (requisito 33); el motivo es el que dio el agente.
            state["escalation"] = {"to": "team", "reason": reason}
        return state

    # ── serializar ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> World:
        return cls(
            timezone=raw["timezone"],
            now=raw["now"],
            week=raw.get("week"),
            specials=list(raw.get("specials") or []),
            services=[SimService(**s) for s in raw.get("services") or []],
            bookings=[SimBooking(**b) for b in raw.get("bookings") or []],
            actions=[Action(**a) for a in raw.get("actions") or []],
            bubbles=list(raw.get("bubbles") or []),
            escalated=bool(raw.get("escalated")),
        )


async def seed_world(session: Any, agent_id: uuid.UUID, *, now: datetime | None = None) -> World:
    """El mundo de un agente, sembrado desde la ficha de su cliente (el de la
    sesión, con su RLS): su horario, sus fechas especiales y **sus** servicios
    (garantía 9)."""
    from nexus_api.services.business import hours as hours_service
    from nexus_api.services.business import services_catalog

    business = await hours_service.load_hours(session)
    week = (
        [[[s.open_min, s.close_min] for s in day] for day in business.week.days]
        if business.week is not None
        else None
    )
    specials = [
        {
            "from": sp.date_from.isoformat(),
            "to": sp.date_to.isoformat(),
            "closed": sp.closed,
            "shifts": [[s.open_min, s.close_min] for s in sp.shifts],
        }
        for sp in business.specials
    ]
    services = []
    for svc in await services_catalog.services_for_agent(session, agent_id):
        kind = services_catalog.price_kind_of(svc)
        price = (
            services_catalog.format_amount(int(svc.price_minor or 0), svc.currency)
            if kind == "amount"
            else ("gratis" if kind == "free" else None)
        )
        services.append(
            SimService(
                id=str(svc.id),
                name=svc.name,
                duration_min=svc.duration_minutes,
                bookable=bool(svc.bookable),
                price=price,
            )
        )
    world = World(
        timezone=business.timezone or "UTC",
        now=(now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        week=week,
        specials=specials,
        services=services,
    )
    return world


__all__ = ["SLOT_STEP_MIN", "Action", "SimBooking", "SimService", "World", "seed_world"]
