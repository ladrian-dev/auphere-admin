"""El motor de disponibilidad de Reservas — spec 043 (Requisito 4). Puro.

Lo usan por igual la API de la consola, las herramientas del agente y el worker:
si aquí cabe, cabe en todas partes, y si no, todas dicen lo mismo y por qué.
Sin base de datos ni reloj: quien llama le pasa el «ahora».

**Aforo** (``fits``/``presIn`` del diseño):

- las **franjas** son las horas de llegada de un turno (``Comida de 13:00 a 15:00
  cada 30``) o de la franja del día (``de 12:00 a 23:00 cada 60``), con la
  última incluida, y solo en un día que abre según el horario del negocio;
- **presencia** a la hora ``t``: la suma de personas de las reservas vivas con
  ``inicio <= t < fin`` (cada reserva ocupa su estancia);
- un grupo de ``n`` **cabe** a la hora ``t`` si ``t`` es una franja, no está
  bloqueada, no es pasado (salvo una llegada sin reserva) y en cada franja de
  ``[t, t + estancia)`` queda ``aforo - guardadas - presencia >= n``; la llegada
  sin reserva usa el aforo entero.

**Servicios** (``freeSlots`` de la consola): candidatos cada ``step`` desde el
inicio de cada tramo del horario del negocio ∩ el de la persona, que caben
enteros, no antes de ``not_before`` y sin pisar nada ocupado.

Las horas son conscientes de zona (``tzinfo`` del negocio); se comparan bien
con instantes UTC.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from nexus_api.db.models.reservation import LIVE_STATUSES

Range = tuple[time, time]
Span = tuple[datetime, datetime]


# ── franjas ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Slot:
    at: datetime
    shift: str | None


def _t(raw: Any) -> time:
    h, m = str(raw).split(":")
    return time(int(h), int(m))


def _spans(schedule: dict[str, Any]) -> list[tuple[str | None, time, time]]:
    if schedule.get("model") == "slots":
        return [(None, _t(schedule["from"]), _t(schedule["to"]))]
    return [(s.get("name"), _t(s["from"]), _t(s["to"])) for s in schedule.get("shifts", [])]


def day_slots(
    schedule: dict[str, Any] | None, day: date, tz: ZoneInfo, business: Sequence[Range]
) -> list[Slot]:
    """Las horas de llegada del día, en orden. Un día que el horario del
    negocio cierra no tiene ninguna; una franja fuera del horario, tampoco."""
    if not schedule or not business:
        return []
    step = timedelta(minutes=int(schedule.get("step_minutes") or 30))
    opens, closes = min(r[0] for r in business), max(r[1] for r in business)
    out: list[Slot] = []
    for name, first, last in _spans(schedule):
        cursor = datetime.combine(day, first, tzinfo=tz)
        end = datetime.combine(day, last, tzinfo=tz)
        while cursor <= end:
            local = cursor.timetz().replace(tzinfo=None)
            if opens <= local <= closes:
                out.append(Slot(at=cursor, shift=name))
            cursor += step
    out.sort(key=lambda s: s.at)
    return out


# ── Aforo ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CapacityRules:
    seats: int
    hold: int
    stay: timedelta
    max_party: int


@dataclass(frozen=True)
class Occupant:
    start: datetime
    end: datetime
    size: int
    status: str
    id: Any = None


@dataclass(frozen=True)
class Fit:
    fits: bool
    left: int
    why: str | None  # closed | blocked | block_overlap | past | full


def presence(people: Iterable[Occupant], at: datetime, *, exclude: Any = None) -> int:
    return sum(
        p.size
        for p in people
        if p.status in LIVE_STATUSES
        and p.start <= at < p.end
        and (exclude is None or p.id != exclude)
    )


def capacity_fit(
    slots: Sequence[Slot],
    blocked: set[datetime],
    people: Sequence[Occupant],
    rules: CapacityRules,
    at: datetime,
    n: int,
    *,
    now: datetime,
    walkin: bool = False,
    exclude: Any = None,
) -> Fit:
    times = [s.at for s in slots]
    if at not in times:
        return Fit(False, 0, "closed")
    if at in blocked:
        return Fit(False, 0, "blocked")
    if at < now and not walkin:
        return Fit(False, 0, "past")
    hold = 0 if walkin else rules.hold
    window = [t for t in times if at <= t < at + rules.stay]
    if any(t in blocked for t in window):
        return Fit(False, 0, "block_overlap")
    left = min(rules.seats - hold - presence(people, t, exclude=exclude) for t in window)
    left = max(left, 0)
    return Fit(left >= n, left, None if left >= n else "full")


def first_fit(
    slots: Sequence[Slot],
    blocked: set[datetime],
    people: Sequence[Occupant],
    rules: CapacityRules,
    n: int,
    *,
    now: datetime,
    after: datetime | None = None,
    walkin: bool = False,
    exclude: Any = None,
) -> datetime | None:
    """La primera franja del día, desde ``after``, en la que cabe ``n``."""
    for s in slots:
        if after is not None and s.at < after:
            continue
        if capacity_fit(
            slots, blocked, people, rules, s.at, n, now=now, walkin=walkin, exclude=exclude
        ).fits:
            return s.at
    return None


def current_slot(slots: Sequence[Slot], now: datetime) -> datetime | None:
    """La franja en curso: la última que ya empezó, dentro del servicio."""
    started = [s.at for s in slots if s.at <= now]
    return started[-1] if started else None


# ── Servicios ───────────────────────────────────────────────────────────────


def intersect(a: Sequence[Range], b: Sequence[Range]) -> list[Range]:
    out: list[Range] = []
    for a0, a1 in a:
        for b0, b1 in b:
            lo, hi = max(a0, b0), min(a1, b1)
            if lo < hi:
                out.append((lo, hi))
    return sorted(out)


def services_slots(
    *,
    day: date,
    tz: ZoneInfo,
    business: Sequence[Range],
    staff: Sequence[Range],
    duration: timedelta,
    step: timedelta,
    busy: Sequence[Span],
    not_before: datetime,
) -> list[datetime]:
    out: list[datetime] = []
    for lo, hi in intersect(business, staff):
        cursor = datetime.combine(day, lo, tzinfo=tz)
        end = datetime.combine(day, hi, tzinfo=tz)
        while cursor + duration <= end:
            slot_end = cursor + duration
            if cursor >= not_before and not any(b0 < slot_end and cursor < b1 for b0, b1 in busy):
                out.append(cursor)
            cursor += step
    return out


__all__ = [
    "CapacityRules",
    "Fit",
    "Occupant",
    "Slot",
    "capacity_fit",
    "current_slot",
    "day_slots",
    "first_fit",
    "intersect",
    "presence",
    "services_slots",
]
