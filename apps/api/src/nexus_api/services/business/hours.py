"""El horario del negocio — spec 047, T056 (requisito 10, research D15).

**Un solo horario** responde «¿abierto ahora?», da la frase «Así lo dirá el
agente» y da las horas de cada día que usa Reservas. Vive en la ficha
(``business_schedules`` y ``business_shifts``, uno del negocio y uno por sede, y
``business_special_dates``); las copias de antes (``tenants.business_hours``, la
etiqueta del prompt y ``policies.console.schedule``) dejan de ser fuentes:
``tenants.business_hours`` se escribe como **proyección** en la misma
transacción, para los lectores que aún no leen la ficha.

Dos partes:

**El motor**, puro (sin base ni reloj):

- los turnos se guardan en minutos desde la medianoche del día que abren; un
  cierre por encima de 1.440 cae al día siguiente y de 0 a 1.440 es «24 horas»;
- la API habla ``HH:MM``, y un cierre igual o anterior a la apertura significa
  «día siguiente» (:func:`parse_shift`);
- por bloques (lunes a viernes, sábado y domingo) o día por día, con hasta 6
  turnos por día;
- las fechas especiales (cerrado o con turnos propios, de un día o un rango)
  mandan **desde la apertura del turno de ese día**: el turno nocturno de la
  víspera sigue hasta su cierre;
- las horas son de reloj, en la zona del negocio y en la fecha local real:
  el día del cambio de hora un turno nocturno dura una hora menos o más, y la
  frase no cambia.

**El repositorio**: leer y escribir el horario del cliente del contexto, dentro
de la transacción del llamante (RLS), y la proyección.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Tenant
from nexus_api.db.models.business import (
    MAX_SHIFTS_PER_DAY,
    MINUTES_PER_DAY,
    SCHEDULE_LAYOUTS,
    BusinessLocation,
    BusinessProfile,
    BusinessSchedule,
    BusinessShift,
    BusinessSpecialDate,
    BusinessSpecialShift,
)
from nexus_api.services.business import section_write, writes
from nexus_api.services.business.profile import business_language
from nexus_api.services.business.section_write import LEGACY_NICHE, SYSTEM, ensure_profile
from nexus_api.services.business.sections import Actor
from nexus_api.services.business_hours import WEEKDAYS as LEGACY_DAYS
from nexus_api.services.business_hours import parse_business_hours

#: Los días del ClientSpec, lunes primero (``weekday`` 0 = lunes).
DAY_KEYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
#: Los bloques de «Por bloques»: lunes a viernes, sábado y domingo.
BLOCKS: Final[tuple[tuple[int, ...], ...]] = ((0, 1, 2, 3, 4), (5,), (6,))
#: El final del día en Reservas: un tramo que llega a medianoche.
END_OF_DAY: Final = time.max
#: Lo más lejos que se busca la próxima apertura.
LOOKAHEAD_DAYS: Final = 14

Layout = Literal["blocks", "daily"]


class HoursError(ValueError):
    """Un horario que no se puede guardar. La API responde ``422`` con ``code``."""

    def __init__(self, code: str, message: str, *, day: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.day = day


# ── turnos ──────────────────────────────────────────────────────────────────


def _minutes(raw: object, *, field_name: str) -> int:
    if not isinstance(raw, str) or len(raw) != 5 or raw[2] != ":":
        raise HoursError("invalid_time", f"{field_name}: expected HH:MM, got {raw!r}")
    hh, mm = raw[:2], raw[3:]
    if not (hh.isdigit() and mm.isdigit()):
        raise HoursError("invalid_time", f"{field_name}: expected HH:MM, got {raw!r}")
    h, m = int(hh), int(mm)
    if raw == "24:00":
        return MINUTES_PER_DAY
    if h > 23 or m > 59:
        raise HoursError("invalid_time", f"{field_name}: out of range: {raw!r}")
    return h * 60 + m


def _fmt(minutes: int) -> str:
    m = minutes % MINUTES_PER_DAY
    return f"{m // 60:02d}:{m % 60:02d}"


def _time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


@dataclass(frozen=True, order=True)
class Shift:
    """Un turno, en minutos desde la medianoche del día que abre."""

    open_min: int
    close_min: int

    def __post_init__(self) -> None:
        if not 0 <= self.open_min < MINUTES_PER_DAY:
            raise HoursError("invalid_shift", f"opening out of range: {self.open_min}")
        if not self.open_min < self.close_min <= self.open_min + MINUTES_PER_DAY:
            raise HoursError(
                "invalid_shift", f"closing out of range: {self.open_min}-{self.close_min}"
            )

    @property
    def overnight(self) -> bool:
        """«Nocturno · cierra al día siguiente»."""
        return self.close_min > MINUTES_PER_DAY

    @property
    def all_day(self) -> bool:
        return self.open_min == 0 and self.close_min == MINUTES_PER_DAY

    def hhmm(self) -> tuple[str, str]:
        close = "24:00" if self.all_day else _fmt(self.close_min)
        return _fmt(self.open_min), close


def parse_shift(open_: str, close: str) -> Shift:
    """``HH:MM`` → turno. Un cierre igual o anterior a la apertura es del día
    siguiente (requisito 10.2); de ``00:00`` a ``24:00`` (o a ``00:00``) son 24 horas."""
    o = _minutes(open_, field_name="open")
    if o >= MINUTES_PER_DAY:
        raise HoursError("invalid_time", "open: 24:00 is only a closing time")
    c = _minutes(close, field_name="close")
    if c == MINUTES_PER_DAY:
        return Shift(o, MINUTES_PER_DAY)
    return Shift(o, c + MINUTES_PER_DAY if c <= o else c)


def _check_day(shifts: Sequence[Shift], *, day: str | None) -> tuple[Shift, ...]:
    ordered = tuple(sorted(shifts))
    if len(ordered) > MAX_SHIFTS_PER_DAY:
        raise HoursError("too_many_shifts", f"at most {MAX_SHIFTS_PER_DAY} shifts a day", day=day)
    for prev, nxt in pairwise(ordered):
        if nxt.open_min < prev.close_min:
            raise HoursError("overlap", "two shifts overlap", day=day)
    return ordered


# ── la semana ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Week:
    """El horario semanal: ``days[0]`` es el lunes. Lista vacía = cerrado."""

    layout: str
    days: tuple[tuple[Shift, ...], ...]

    def __post_init__(self) -> None:
        if self.layout not in SCHEDULE_LAYOUTS:
            raise HoursError("invalid_layout", f"unknown layout: {self.layout!r}")
        if len(self.days) != 7:
            raise HoursError("invalid_week", "a week has seven days")
        for i, shifts in enumerate(self.days):
            if tuple(sorted(shifts)) != tuple(shifts):
                raise HoursError("invalid_week", "shifts must be in order", day=DAY_KEYS[i])
            _check_day(shifts, day=DAY_KEYS[i])
        for i, shifts in enumerate(self.days):
            spill = max((s.close_min - MINUTES_PER_DAY for s in shifts if s.overnight), default=0)
            nxt = self.days[(i + 1) % 7]
            if spill and nxt and nxt[0].open_min < spill:
                raise HoursError(
                    "overlap_next_day",
                    "a night shift runs into the next day's first shift",
                    day=DAY_KEYS[i],
                )
        if self.layout == "blocks" and any(d != self.days[0] for d in self.days[1:5]):
            raise HoursError("blocks_differ", "by blocks, Monday to Friday share the same shifts")


def make_week(layout: str, days: Sequence[Iterable[Shift]]) -> Week:
    return Week(layout=layout, days=tuple(_check_day(list(d), day=None) for d in days))


def week_from_days(layout: str, days: Mapping[str, Sequence[Mapping[str, Any]]]) -> Week:
    """La forma del ClientSpec (``weekSchedule``) → :class:`Week`."""
    unknown = sorted(str(k) for k in days if k not in DAY_KEYS)
    if unknown:
        raise HoursError("unknown_day", f"unknown days: {', '.join(unknown)}")
    out: list[tuple[Shift, ...]] = []
    for key in DAY_KEYS:
        raw = days.get(key) or []
        shifts = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise HoursError("invalid_shift", "a shift is {open, close}", day=key)
            try:
                shifts.append(parse_shift(item.get("open"), item.get("close")))  # type: ignore[arg-type]
            except HoursError as exc:
                raise HoursError(exc.code, str(exc), day=key) from None
        out.append(_check_day(shifts, day=key))
    return Week(layout=layout, days=tuple(out))


def week_to_days(week: Week) -> dict[str, list[dict[str, Any]]]:
    """:class:`Week` → la forma del ClientSpec, con ``overnight`` para el rótulo."""
    return {
        key: [
            {"open": s.hhmm()[0], "close": s.hhmm()[1], "overnight": s.overnight}
            for s in week.days[i]
        ]
        for i, key in enumerate(DAY_KEYS)
    }


def blocks_loss(week: Week) -> list[str]:
    """Los días de lunes a viernes que no tienen los turnos del lunes: lo que se
    perdería al pasar a «Por bloques» (requisito 10.6)."""
    return [DAY_KEYS[i] for i in range(1, 5) if week.days[i] != week.days[0]]


def to_blocks(week: Week) -> Week:
    """«Por bloques»: de lunes a viernes, los turnos del lunes."""
    return Week(layout="blocks", days=(week.days[0],) * 5 + week.days[5:])


# ── fechas especiales ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class SpecialDay:
    """Una fecha especial: cerrado o con turnos propios, de un día o de un rango."""

    date_from: date
    date_to: date
    closed: bool
    shifts: tuple[Shift, ...] = ()
    name: str = ""
    id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.date_to < self.date_from:
            raise HoursError("date_range", "the range ends before it starts")
        if len(self.name) > 80:
            raise HoursError("name_too_long", "80 characters at most")
        if self.closed and self.shifts:
            raise HoursError("closed_with_shifts", "a closed date has no shifts")
        if not self.closed and not self.shifts:
            raise HoursError("no_shifts", "an open special date needs its shifts")
        if tuple(sorted(self.shifts)) != tuple(self.shifts):
            raise HoursError("invalid_week", "shifts must be in order")
        _check_day(self.shifts, day=None)

    def covers(self, day: date) -> bool:
        return self.date_from <= day <= self.date_to


# ── el horario de un negocio (o de una sede) ────────────────────────────────


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@dataclass(frozen=True)
class Hours:
    """Lo que el motor necesita: la semana (``None`` = sin horario), las fechas
    especiales que aplican y la zona IANA del negocio."""

    week: Week | None
    specials: tuple[SpecialDay, ...] = ()
    timezone: str = "UTC"

    @property
    def known(self) -> bool:
        return self.week is not None

    @property
    def tz(self) -> ZoneInfo:
        return zone(self.timezone)


def special_on(hours: Hours, day: date) -> SpecialDay | None:
    """La fecha especial de ``day``: si se pisan dos, la del rango más corto."""
    found: SpecialDay | None = None
    for sp in hours.specials:
        if sp.covers(day) and (
            found is None or (sp.date_to - sp.date_from) <= (found.date_to - found.date_from)
        ):
            found = sp
    return found


def shifts_on(hours: Hours, day: date) -> tuple[Shift, ...] | None:
    """Los turnos que **abren** ``day``; ``None`` si el negocio no tiene horario."""
    if hours.week is None:
        return None
    sp = special_on(hours, day)
    if sp is not None:
        return () if sp.closed else sp.shifts
    return hours.week.days[day.weekday()]


def _wall(day: date, minutes: int, tz: ZoneInfo) -> datetime:
    """La hora de reloj ``minutes`` después de la medianoche de ``day``, en UTC."""
    d = day + timedelta(days=minutes // MINUTES_PER_DAY)
    local = datetime.combine(d, _time(minutes % MINUTES_PER_DAY), tzinfo=tz)
    return local.astimezone(UTC)


def intervals_on(hours: Hours, day: date) -> list[tuple[datetime, datetime]]:
    """Los turnos que abren ``day``, como instantes UTC ``[apertura, cierre)``."""
    tz = hours.tz
    return [
        (_wall(day, s.open_min, tz), _wall(day, s.close_min, tz))
        for s in (shifts_on(hours, day) or ())
    ]


@dataclass(frozen=True)
class OpenState:
    """«¿Está abierto ahora?». ``known`` falso: el negocio no tiene horario y
    nadie debe decir ni que sí ni que no (requisito 10.7)."""

    known: bool
    open: bool
    #: Cuándo cierra, en la hora local del negocio, si está abierto.
    until: datetime | None = None
    #: La próxima apertura, en la hora local, si está cerrado.
    next_open: datetime | None = None
    #: La fecha especial que manda ahora, si la hay.
    special: SpecialDay | None = None


def open_state(hours: Hours, at: datetime) -> OpenState:
    if hours.week is None:
        return OpenState(known=False, open=False)
    tz = hours.tz
    now = at.astimezone(UTC)
    today = now.astimezone(tz).date()
    for day in (today - timedelta(days=1), today):
        for start, end in intervals_on(hours, day):
            if start <= now < end:
                until = end
                # 24 hours every day (or back-to-back shifts) keep going.
                for _ in range(LOOKAHEAD_DAYS):
                    after = until.astimezone(tz).date()
                    nxt = [
                        e
                        for d in (after - timedelta(days=1), after)
                        for s, e in intervals_on(hours, d)
                        if s == until
                    ]
                    if not nxt:
                        break
                    until = nxt[0]
                return OpenState(
                    known=True,
                    open=True,
                    until=until.astimezone(tz),
                    special=special_on(hours, day),
                )
    upcoming = sorted(
        start
        for offset in range(LOOKAHEAD_DAYS + 1)
        for start, _end in intervals_on(hours, today + timedelta(days=offset))
        if start > now
    )
    return OpenState(
        known=True,
        open=False,
        next_open=upcoming[0].astimezone(tz) if upcoming else None,
        special=special_on(hours, today),
    )


def day_ranges(hours: Hours, day: date) -> list[tuple[time, time]]:
    """Las horas de reloj de ``day`` en que el negocio está abierto, para
    Reservas: lo que queda del turno nocturno de la víspera y los turnos que
    abren ese día. Un tramo que llega a medianoche termina en :data:`END_OF_DAY`."""
    if hours.week is None:
        return []
    spans: list[tuple[int, int]] = [
        (0, s.close_min - MINUTES_PER_DAY)
        for s in (shifts_on(hours, day - timedelta(days=1)) or ())
        if s.overnight
    ]
    spans.extend(
        (s.open_min, min(s.close_min, MINUTES_PER_DAY)) for s in (shifts_on(hours, day) or ())
    )
    merged: list[list[int]] = []
    for lo, hi in sorted(spans):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [(_time(lo), END_OF_DAY if hi >= MINUTES_PER_DAY else _time(hi)) for lo, hi in merged]


# ── la frase «Así lo dirá el agente» ────────────────────────────────────────

_WORDS: Final[dict[str, dict[str, Any]]] = {
    "es": {
        "one": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
        "many": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"),
        "to": "a",
        "and": "y",
        "open": "Abrimos {}.",
        "closed": "Cerramos {}.",
        "every_day": "todos los días",
        "all_closed": "Cerramos todos los días.",
        "all_day_every_day": "Abrimos las 24 horas, todos los días.",
        "all_day": "las 24 horas",
        "shift": "de {} a {}",
        "next_day": " del día siguiente",
    },
    "en": {
        "one": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        "many": (
            "Mondays",
            "Tuesdays",
            "Wednesdays",
            "Thursdays",
            "Fridays",
            "Saturdays",
            "Sundays",
        ),
        "to": "to",
        "and": "and",
        "open": "We are open {}.",
        "closed": "Closed on {}.",
        "every_day": "every day",
        "all_closed": "Closed every day.",
        "all_day_every_day": "We are open 24 hours, every day.",
        "all_day": "24 hours",
        "shift": "from {} to {}",
        "next_day": " (next day)",
    },
}


def _locale(locale: str | None) -> dict[str, Any]:
    return _WORDS["en"] if (locale or "").lower().startswith("en") else _WORDS["es"]


def _runs(days: tuple[tuple[Shift, ...], ...]) -> list[tuple[int, int, tuple[Shift, ...]]]:
    """Los días seguidos (lunes a domingo) con los mismos turnos."""
    out: list[tuple[int, int, tuple[Shift, ...]]] = []
    for i, shifts in enumerate(days):
        if out and out[-1][2] == shifts and out[-1][1] == i - 1:
            out[-1] = (out[-1][0], i, shifts)
        else:
            out.append((i, i, shifts))
    return out


def _days_text(first: int, last: int, w: dict[str, Any]) -> str:
    if last - first >= 2:
        return f"{w['one'][first]} {w['to']} {w['one'][last]}"
    if last == first + 1:
        return f"{w['many'][first]} {w['and']} {w['many'][last]}"
    return str(w["many"][first])


def _shifts_text(shifts: tuple[Shift, ...], w: dict[str, Any]) -> str:
    if len(shifts) == 1 and shifts[0].all_day:
        return str(w["all_day"])
    parts = []
    for s in shifts:
        text = w["shift"].format(_fmt(s.open_min), _fmt(s.close_min))
        parts.append(text + (w["next_day"] if s.overnight else ""))
    return f" {w['and']} ".join(parts)


def shifts_text(shifts: Sequence[Shift], *, locale: str | None = "es") -> str:
    """«de 10:00 a 14:00 y de 16:00 a 20:00», como en la frase."""
    return _shifts_text(tuple(shifts), _locale(locale))


def _join(items: list[str], w: dict[str, Any]) -> str:
    if len(items) == 1:
        return items[0]
    glue = f" {w['and']} "
    last = f", {w['and']} " if any(glue in item for item in items) else glue
    return ", ".join(items[:-1]) + last + items[-1]


def phrase(week: Week | None, *, locale: str | None = "es") -> str | None:
    """La frase del horario (requisito 10.5). Determinista: depende solo de la
    semana. ``None`` sin horario."""
    if week is None:
        return None
    w = _locale(locale)
    days = week.days
    if not any(days):
        return str(w["all_closed"])
    if all(d == days[0] for d in days):
        if len(days[0]) == 1 and days[0][0].all_day:
            return str(w["all_day_every_day"])
        return str(w["open"].format(f"{w['every_day']} {_shifts_text(days[0], w)}"))
    runs = _runs(days)
    opened = [f"{_days_text(a, b, w)} {_shifts_text(s, w)}" for a, b, s in runs if s]
    closed = [_days_text(a, b, w) for a, b, s in runs if not s]
    out = str(w["open"].format(_join(opened, w)))
    if closed:
        out += " " + str(w["closed"].format(_join(closed, w)))
    return out


# ── la proyección para los lectores de antes ────────────────────────────────


def legacy_projection(week: Week | None, *, locale: str | None = "es") -> dict[str, Any] | None:
    """``tenants.business_hours`` en su forma canónica de antes (``{"monday":
    [{"from", "to"}]…, "label"}``). No admite nocturnos: se parten a medianoche, y
    lo que llega a las 24:00 queda en 23:59. Las fechas especiales no caben: solo
    las ve quien lee la ficha."""
    if week is None:
        return None
    out: dict[str, Any] = {}
    for i, key in enumerate(LEGACY_DAYS):
        spans = [(0, s.close_min - MINUTES_PER_DAY) for s in week.days[(i - 1) % 7] if s.overnight]
        spans.extend((s.open_min, min(s.close_min, MINUTES_PER_DAY - 1)) for s in week.days[i])
        merged: list[list[int]] = []
        for lo, hi in sorted(spans):
            if hi <= lo:
                continue
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        out[key] = [{"from": _fmt(lo), "to": _fmt(hi)} for lo, hi in merged]
    out["label"] = phrase(week, locale=locale)
    return out


def week_from_legacy(raw: object) -> Week | None:
    """Cualquiera de las formas que ``tenants.business_hours`` llegó a guardar →
    :class:`Week` (``None``: sin horario). Lo lee el lector tolerante de
    ``business_hours``: un día ilegible sale cerrado."""
    parsed = parse_business_hours(raw)
    if parsed is None:
        return None
    days = tuple(
        tuple(Shift(a.hour * 60 + a.minute, b.hour * 60 + b.minute) for a, b in parsed[key])
        for key in LEGACY_DAYS
    )
    layout = "blocks" if all(d == days[0] for d in days[1:5]) else "daily"
    return Week(layout=layout, days=days)


# ── el repositorio ──────────────────────────────────────────────────────────
#
# Todo corre en la transacción del llamante, con el cliente puesto (RLS), y
# filtra además por ``tenant_id``: la garantía nunca descansa en una sola capa.

#: Donde viaja el horario de la ficha en el ``AgentBundle`` del worker.
RUNTIME_KEY: Final = "_business_hours"


async def business_locale(session: AsyncSession, tenant_id: uuid.UUID | None = None) -> str:
    """El idioma de la frase: el del país del negocio."""
    profile = await session.get(BusinessProfile, tenant_id or require_current_tenant())
    return business_language(profile.country if profile else None)


def _owner(location_id: uuid.UUID | None) -> Any:
    if location_id is None:
        return BusinessSchedule.location_id.is_(None)
    return BusinessSchedule.location_id == location_id


async def _schedule(
    session: AsyncSession, tenant_id: uuid.UUID, location_id: uuid.UUID | None
) -> BusinessSchedule | None:
    row: BusinessSchedule | None = await session.scalar(
        sa.select(BusinessSchedule).where(
            BusinessSchedule.tenant_id == tenant_id, _owner(location_id)
        )
    )
    return row


async def load_week(
    session: AsyncSession,
    *,
    location_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> Week | None:
    """El horario propio del negocio (o de la sede), sin heredar nada."""
    tid = tenant_id or require_current_tenant()
    row = await _schedule(session, tid, location_id)
    if row is None:
        return None
    rows = await session.execute(
        sa.select(BusinessShift.weekday, BusinessShift.open_min, BusinessShift.close_min)
        .where(BusinessShift.tenant_id == tid, BusinessShift.schedule_id == row.id)
        .order_by(BusinessShift.weekday, BusinessShift.open_min)
    )
    days: list[list[Shift]] = [[] for _ in DAY_KEYS]
    for weekday, open_min, close_min in rows.all():
        days[int(weekday)].append(Shift(int(open_min), int(close_min)))
    return Week(layout=row.layout, days=tuple(tuple(d) for d in days))


async def load_specials(
    session: AsyncSession,
    *,
    location_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> list[SpecialDay]:
    """Las fechas especiales vigentes que mandan sobre el negocio (las de todo el
    negocio) o sobre una sede (las de todo el negocio y las suyas)."""
    tid = tenant_id or require_current_tenant()
    owner = (
        BusinessSpecialDate.location_id.is_(None)
        if location_id is None
        else sa.or_(
            BusinessSpecialDate.location_id.is_(None),
            BusinessSpecialDate.location_id == location_id,
        )
    )
    dates = (
        await session.scalars(
            sa.select(BusinessSpecialDate)
            .where(
                BusinessSpecialDate.tenant_id == tid,
                BusinessSpecialDate.archived_at.is_(None),
                owner,
            )
            .order_by(BusinessSpecialDate.date_from, BusinessSpecialDate.created_at)
        )
    ).all()
    return await specials_of(session, list(dates), tenant_id=tid)


async def specials_of(
    session: AsyncSession, dates: Sequence[BusinessSpecialDate], *, tenant_id: uuid.UUID
) -> list[SpecialDay]:
    """Las filas de fechas especiales → :class:`SpecialDay`, con sus turnos."""
    if not dates:
        return []
    shifts: dict[uuid.UUID, list[Shift]] = {}
    rows = await session.execute(
        sa.select(
            BusinessSpecialShift.special_date_id,
            BusinessSpecialShift.open_min,
            BusinessSpecialShift.close_min,
        ).where(
            BusinessSpecialShift.tenant_id == tenant_id,
            BusinessSpecialShift.special_date_id.in_([d.id for d in dates]),
        )
    )
    for special_id, open_min, close_min in rows.all():
        shifts.setdefault(special_id, []).append(Shift(int(open_min), int(close_min)))
    out: list[SpecialDay] = []
    for row in dates:
        try:
            out.append(
                SpecialDay(
                    date_from=row.date_from,
                    date_to=row.date_to,
                    closed=row.closed,
                    shifts=tuple(sorted(shifts.get(row.id, []))),
                    name=row.name or "",
                    id=row.id,
                    location_id=row.location_id,
                )
            )
        except HoursError:  # pragma: no cover - the service validates on write
            continue
    return out


async def load_hours(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    legacy: bool = True,
) -> Hours:
    """El horario que vale para el negocio o para una sede: el suyo; una sede
    sin horario propio, el del negocio (requisito 9.2). Un cliente que aún no
    tiene el horario en la ficha (de antes de la 0184) se lee de
    ``tenants.business_hours`` (``legacy``), con el mismo lector tolerante."""
    tid = tenant_id or require_current_tenant()
    profile = await session.get(BusinessProfile, tid)
    tenant = await session.get(Tenant, tid)
    # ``tenants.timezone`` is written by every writer of the zone (the ficha's
    # basics, the client's edit modal, the admin): the projection is never stale.
    tz = (tenant.timezone if tenant else None) or (profile.timezone if profile else None)
    week = await load_week(session, location_id=location_id, tenant_id=tid)
    if week is None and location_id is not None:
        week = await load_week(session, tenant_id=tid)
    if week is None and legacy and tenant is not None:
        week = week_from_legacy(tenant.business_hours)
    specials = await load_specials(session, location_id=location_id, tenant_id=tid)
    return Hours(week=week, specials=tuple(specials), timezone=tz or "UTC")


def week_view(week: Week | None, *, locale: str | None = "es") -> dict[str, Any] | None:
    """El horario en la forma del ClientSpec (``weekSchedule``): lo que guarda el
    historial como antes y después."""
    if week is None:
        return None
    return {
        "layout": week.layout,
        "days": {
            key: [{"open": s.hhmm()[0], "close": s.hhmm()[1]} for s in week.days[i]]
            for i, key in enumerate(DAY_KEYS)
        },
        "label": phrase(week, locale=locale),
    }


def special_view(sp: SpecialDay) -> dict[str, Any]:
    """Una fecha especial en la forma del ClientSpec."""
    out: dict[str, Any] = {
        "from": sp.date_from.isoformat(),
        "to": sp.date_to.isoformat(),
        "closed": sp.closed,
        "shifts": [{"open": s.hhmm()[0], "close": s.hhmm()[1]} for s in sp.shifts],
        "location_id": str(sp.location_id) if sp.location_id else None,
    }
    if sp.id is not None:
        out["id"] = str(sp.id)
    if sp.name:
        out["name"] = sp.name
    return out


async def _replace_rows(
    session: AsyncSession, tid: uuid.UUID, week: Week | None, location_id: uuid.UUID | None
) -> None:
    row = await _schedule(session, tid, location_id)
    if row is not None:
        await session.execute(
            sa.delete(BusinessShift).where(
                BusinessShift.tenant_id == tid, BusinessShift.schedule_id == row.id
            )
        )
    if week is None:
        if row is not None:
            await session.delete(row)
        return
    if row is None:
        row = BusinessSchedule(tenant_id=tid, location_id=location_id, layout=week.layout)
        session.add(row)
        await session.flush()
    else:
        row.layout = week.layout
    for weekday, day_shifts in enumerate(week.days):
        for s in day_shifts:
            session.add(
                BusinessShift(
                    tenant_id=tid,
                    schedule_id=row.id,
                    weekday=weekday,
                    open_min=s.open_min,
                    close_min=s.close_min,
                )
            )


async def save_week(
    session: AsyncSession,
    week: Week | None,
    *,
    actor: Actor,
    location_id: uuid.UUID | None = None,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
    state: str | None = None,
) -> writes.SectionWritten | None:
    """Escribe el horario del negocio (o el propio de una sede; ``None`` lo
    quita) y lo anota con :func:`writes.write_section`: historial, procedencia,
    revisión de la sección (``hours``, o ``locations`` para una sede) y la
    recompilación de los agentes. El del negocio deja además su proyección en
    ``tenants.business_hours`` (con la frase como ``label``), en la misma
    transacción.

    Todo va en un *savepoint*: si la revisión leída ya no es la de la sección,
    no queda nada escrito y sale :class:`writes.SectionRevisionConflict`.
    ``None``: no había nada que cambiar."""
    tid = require_current_tenant()
    write = section_write.context(actor, ctx)
    profile = await section_write.ensure_profile(session, tid)
    locale = business_language(profile.country)

    async def change() -> None:
        await _replace_rows(session, tid, week, location_id)
        await session.flush()
        if location_id is None:
            tenant = await session.get(Tenant, tid)
            assert tenant is not None
            tenant.business_hours = legacy_projection(week, locale=locale)

    if state is None and location_id is None and write.review != "pending":
        state = "complete" if week is not None else "pending"
    return await section_write.guarded_write(
        session,
        "hours" if location_id is None else "locations",
        ctx=write,
        change=change,
        pointers=["/hours" if location_id is None else f"/locations/{location_id}/hours"],
        expected_revision=expected_revision,
        state=state,
    )


def week_of_view(view: Mapping[str, Any] | None) -> Week | None:
    """La vista ``weekSchedule`` del ClientSpec (con su clave ``hours`` o sin
    ella) → :class:`Week`. ``None``: sin horario."""
    inner = view.get("hours", view) if isinstance(view, Mapping) else None
    if not isinstance(inner, Mapping) or "days" not in inner:
        return None
    week = week_from_days("daily", inner.get("days") or {})
    return to_blocks(week) if inner.get("layout") == "blocks" else week


async def _restore(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: writes.WriteContext
) -> writes.SectionWritten:
    written = await save_week(session, week_of_view(view), actor=ctx.actor, ctx=ctx)
    if written is None:
        raise writes.NothingWritten
    return written


async def _apply(
    session: AsyncSession, ops: Sequence[writes.Op], ctx: writes.WriteContext
) -> writes.SectionWritten:
    week: Week | None = None
    for op in ops:
        if op.path != "/hours" or op.op not in ("add", "replace"):
            raise HoursError("invalid_pointer", f"not an hours pointer: {op.path}")
        week = week_of_view({"hours": op.value})
    written = await save_week(session, week, actor=ctx.actor, ctx=ctx)
    if written is None:
        raise writes.NothingWritten
    return written


writes.register_section_adapter("hours", restore=_restore, apply=_apply)

# ── lo que lleva el worker en cada turno ────────────────────────────────────


def dump_hours(hours: Hours) -> dict[str, Any]:
    """:class:`Hours` en JSON: viaja en el ``AgentBundle`` (cacheado e
    invalidado con la recompilación) para calcular «¿abierto ahora?» en el turno."""
    week: dict[str, Any] | None = None
    if hours.week is not None:
        week = {
            "layout": hours.week.layout,
            "days": [[[s.open_min, s.close_min] for s in d] for d in hours.week.days],
        }
    return {
        "timezone": hours.timezone,
        "week": week,
        "specials": [
            {
                "from": sp.date_from.isoformat(),
                "to": sp.date_to.isoformat(),
                "closed": sp.closed,
                "shifts": [[s.open_min, s.close_min] for s in sp.shifts],
                "name": sp.name,
            }
            for sp in hours.specials
        ],
    }


def load_dumped(raw: Mapping[str, Any]) -> Hours:
    """Lo contrario de :func:`dump_hours`."""
    week_raw = raw.get("week")
    week = (
        None
        if not isinstance(week_raw, Mapping)
        else Week(
            layout=str(week_raw["layout"]),
            days=tuple(tuple(Shift(int(a), int(b)) for a, b in d) for d in week_raw["days"]),
        )
    )
    specials = tuple(
        SpecialDay(
            date_from=date.fromisoformat(str(sp["from"])),
            date_to=date.fromisoformat(str(sp["to"])),
            closed=bool(sp["closed"]),
            shifts=tuple(Shift(int(a), int(b)) for a, b in sp.get("shifts") or ()),
            name=str(sp.get("name") or ""),
        )
        for sp in raw.get("specials") or ()
    )
    return Hours(week=week, specials=specials, timezone=str(raw.get("timezone") or "UTC"))


async def runtime_snapshot(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any]:
    """El horario del negocio y el de cada sede con horario propio, para el turno."""
    hours = await load_hours(session, tenant_id=tenant_id)
    locations = (
        await session.execute(
            sa.select(BusinessLocation.id, BusinessLocation.name)
            .join(
                BusinessSchedule,
                sa.and_(
                    BusinessSchedule.tenant_id == BusinessLocation.tenant_id,
                    BusinessSchedule.location_id == BusinessLocation.id,
                ),
            )
            .where(BusinessLocation.tenant_id == tenant_id, BusinessLocation.archived_at.is_(None))
            .order_by(BusinessLocation.position, BusinessLocation.created_at)
        )
    ).all()
    own = [
        {
            "name": name,
            "hours": dump_hours(await load_hours(session, tenant_id=tenant_id, location_id=loc_id)),
        }
        for loc_id, name in locations
    ]
    return {
        **dump_hours(hours),
        "locale": await business_locale(session, tenant_id),
        "locations": own,
    }


__all__ = [
    "BLOCKS",
    "DAY_KEYS",
    "END_OF_DAY",
    "LEGACY_NICHE",
    "RUNTIME_KEY",
    "SYSTEM",
    "Hours",
    "HoursError",
    "OpenState",
    "Shift",
    "SpecialDay",
    "Week",
    "blocks_loss",
    "business_locale",
    "day_ranges",
    "dump_hours",
    "ensure_profile",
    "intervals_on",
    "legacy_projection",
    "load_dumped",
    "load_hours",
    "load_specials",
    "load_week",
    "make_week",
    "open_state",
    "parse_shift",
    "phrase",
    "runtime_snapshot",
    "save_week",
    "shifts_on",
    "shifts_text",
    "special_on",
    "special_view",
    "specials_of",
    "to_blocks",
    "week_from_days",
    "week_from_legacy",
    "week_to_days",
    "week_view",
    "zone",
]
