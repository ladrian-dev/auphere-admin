"""El horario del negocio: una forma canónica y un lector para las que hay.

``tenants.business_hours`` es un JSONB que nadie obligó a tener forma, y cada
pieza que lo tocó eligió la suya (bug ``horario-del-negocio-en-tres-formas``):

- el asistente del panel de operador: ``{"monday": "09:00-18:00" | "closed"}``;
- la semilla de Boreal: ``{"monday": {"open", "close"} | None}``;
- lo que esperaba la disponibilidad del agente: ``{"monday": {"start", "end"}}``;
- la consola (spec 019) en memoria: ``{"monday": {"from", "to"} | None}``.

**La forma canónica** admite partir el día (comida y cena) y nombra siempre los
siete días::

    {"monday": [{"from": "09:00", "to": "14:00"}, {"from": "15:00", "to": "19:00"}],
     ...,
     "sunday": []}

Lista vacía = cerrado. Es lo que la API guarda desde el arreglo; el lector sigue
entendiendo las demás porque puede quedar alguna fila sin migrar o sembrada a
mano.

Dos reglas que no se negocian, porque el agente ofrece huecos con esto:

- **un día que no se entiende es cerrado**, nunca 10 a 19: no se ofrece lo que no
  se puede justificar;
- **un día que no aparece en un horario configurado es cerrado**: configurar el
  lunes no abre el domingo.

Puro: sin base de datos ni zona horaria. Las horas son locales del negocio.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, time
from itertools import pairwise
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS: Final = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

Range = tuple[time, time]
WeeklyHours = dict[str, list[Range]]

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_STRING_RANGE = re.compile(r"^\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*$")
_CLOSED_STRINGS = frozenset({"", "closed", "cerrado"})
# Las parejas de claves que alguna pieza escribió para un tramo.
_PAIRS: Final = (("from", "to"), ("start", "end"), ("open", "close"))


class BusinessHoursError(ValueError):
    """Un horario que no se puede guardar: la API responde 422 con esto."""


def _hhmm(raw: object) -> time | None:
    if not isinstance(raw, str):
        return None
    m = _HHMM.match(raw.strip())
    if m is None:
        return None
    return time(int(m.group(1)), int(m.group(2)))


def _one_range(raw: object) -> Range | None:
    """Un tramo en cualquiera de sus formas, o ``None`` si no se entiende."""
    start: time | None = None
    end: time | None = None
    if isinstance(raw, str):
        m = _STRING_RANGE.match(raw)
        if m is None:
            return None
        start, end = _hhmm(m.group(1)), _hhmm(m.group(2))
    elif isinstance(raw, Mapping):
        for a, b in _PAIRS:
            if a in raw or b in raw:
                start, end = _hhmm(raw.get(a)), _hhmm(raw.get(b))
                break
    if start is None or end is None or end <= start:
        return None
    return (start, end)


def _is_closed(raw: object) -> bool:
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in _CLOSED_STRINGS
    return isinstance(raw, list | tuple) and len(raw) == 0


def _day(raw: object) -> list[Range] | None:
    """Los tramos de un día, ordenados; ``[]`` cerrado; ``None`` ilegible."""
    if _is_closed(raw):
        return []
    items: list[object] = list(raw) if isinstance(raw, list | tuple) else [raw]
    ranges: list[Range] = []
    for item in items:
        r = _one_range(item)
        if r is None:
            return None
        ranges.append(r)
    ranges.sort()
    for prev, nxt in pairwise(ranges):
        if nxt[0] < prev[1]:
            return None  # dos tramos que se pisan no dicen nada claro
    return ranges


def _configured(raw: object) -> bool:
    return isinstance(raw, Mapping) and any(d in raw for d in WEEKDAYS)


def parse_business_hours(raw: object) -> WeeklyHours | None:
    """Lee el horario guardado, en la forma que sea.

    Devuelve ``None`` si el tenant **no tiene horario** (nada guardado, o un
    dict sin ningún día, como ``{"label": "…"}``): qué hacer entonces lo decide
    el llamante. Si lo tiene, devuelve los siete días; un día ausente o
    ilegible sale cerrado.
    """
    if not _configured(raw):
        return None
    assert isinstance(raw, Mapping)
    out: WeeklyHours = {}
    for d in WEEKDAYS:
        ranges = _day(raw.get(d))
        out[d] = ranges if ranges is not None else []
    return out


def canonical_business_hours(raw: object) -> dict[str, Any]:
    """La forma que se guarda. Estricta: lo que no entiende lo rechaza.

    Acepta cualquiera de las formas que existen (para que el asistente del admin
    y las semillas sigan funcionando) y devuelve la canónica. Una clave que no
    es un día de la semana, un tramo ilegible o dos que se pisan levantan
    :class:`BusinessHoursError`.

    ``label`` (la etiqueta del prompt que lee ``agent_configs``) se conserva. Sin
    ningún día es «sin horario», no siete días cerrados: se guarda solo la
    etiqueta (``fix.md``, desviaciones).
    """
    if not isinstance(raw, Mapping):
        raise BusinessHoursError("business_hours must be an object keyed by weekday")
    unknown = sorted(str(k) for k in raw if k not in WEEKDAYS and k != "label")
    if unknown:
        raise BusinessHoursError(f"unknown weekday keys: {', '.join(unknown)}")
    label = raw.get("label")
    if label is not None and not isinstance(label, str):
        raise BusinessHoursError("label must be a string")
    if not any(k in WEEKDAYS for k in raw):
        return {"label": label} if label is not None else {}
    out: dict[str, Any] = {}
    for d in WEEKDAYS:
        ranges = _day(raw.get(d))
        if ranges is None:
            raise BusinessHoursError(f"{d}: unreadable or overlapping hours")
        out[d] = [{"from": a.strftime("%H:%M"), "to": b.strftime("%H:%M")} for a, b in ranges]
    if label is not None:
        out["label"] = label
    return out


def week_of(stored: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Los siete días de una forma canónica, sin la etiqueta."""
    return {d: list(stored.get(d) or []) for d in WEEKDAYS}


def to_canonical(hours: WeeklyHours) -> dict[str, list[dict[str, str]]]:
    """Lo leído (tolerante) en la forma canónica, para devolverlo por la API."""
    return {
        d: [{"from": a.strftime("%H:%M"), "to": b.strftime("%H:%M")} for a, b in hours[d]]
        for d in WEEKDAYS
    }


def maybe_canonical(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """``None`` se queda en ``None`` (sin horario); lo demás, canónico."""
    if raw is None:
        return None
    return canonical_business_hours(raw)


# ── spec 045: la frase y «¿abierto ahora?» ───────────────────────────────────

_DASH = "\u2013"
_NAMES: Final = {
    "es": ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}
_PLURALS: Final = {
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"),
    "en": ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"),
}
_WORDS: Final = {
    "es": {"every": "Todos los días", "to": "a", "and": "y"},
    "en": {"every": "Every day", "to": "to", "and": "and"},
}


def _ranges_text(ranges: list[Range], locale: str) -> str:
    parts = [f"{a.strftime('%H:%M')}{_DASH}{b.strftime('%H:%M')}" for a, b in ranges]
    return f" {_WORDS[locale]['and']} ".join(parts)


def business_hours_label(hours: WeeklyHours, locale: str) -> str | None:
    """La frase del horario, agrupando los días seguidos que abren igual.

    Espejo de ``hoursLabel`` de la consola (spec 019) para quien no tiene la
    consola delante: la app (spec 045). ``None`` si no abre ningún día."""
    loc = locale if locale in _NAMES else "es"
    names, plurals, words = _NAMES[loc], _PLURALS[loc], _WORDS[loc]
    open_days = [i for i, d in enumerate(WEEKDAYS) if hours.get(d)]
    if not open_days:
        return None
    first = hours[WEEKDAYS[open_days[0]]]
    if len(open_days) == len(WEEKDAYS) and all(hours[d] == first for d in WEEKDAYS):
        return f"{words['every']} {_ranges_text(first, loc)}"
    chunks: list[str] = []
    i = 0
    while i < len(WEEKDAYS):
        ranges = hours[WEEKDAYS[i]]
        if not ranges:
            i += 1
            continue
        j = i
        while j + 1 < len(WEEKDAYS) and hours[WEEKDAYS[j + 1]] == ranges:
            j += 1
        head = names[i] if not chunks else plurals[i]
        if j == i:
            chunks.append(f"{head} {_ranges_text(ranges, loc)}")
        else:
            last = names[j] if loc == "en" else names[j].lower()
            chunks.append(f"{head} {words['to']} {last} {_ranges_text(ranges, loc)}")
        i = j + 1
    return ", ".join(chunks)


def _zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def is_open_at(hours: WeeklyHours, tz_name: str | None, at: datetime) -> bool:
    """¿Está abierto el negocio en el instante ``at``? La hora de cierre ya es
    fuera."""
    local = at.astimezone(_zone(tz_name))
    now_t = local.time().replace(tzinfo=None)
    return any(a <= now_t < b for a, b in hours[WEEKDAYS[local.weekday()]])
