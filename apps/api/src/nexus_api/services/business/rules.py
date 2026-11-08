"""Las reglas del horario y de los servicios — spec 056 (requisito 5, research R5).

La ficha del partner y los Ajustes de Reservas del cliente aceptan y rechazan
**los mismos** valores, los edite quien los edite (5.1, 5.2). Los límites y los
chequeos viven aquí; los esquemas de las dos superficies
(``api/console/schemas_business_sections.py`` y
``api/console/lite/reservas_schemas.py``) los leen de este módulo.

| Dato | Regla |
|---|---|
| Turnos por día | de 0 a 6 (``MAX_SHIFTS_PER_DAY``); sin turnos, cerrado |
| Horas | ``HH:MM`` en pasos de 5 minutos; ``24:00`` solo como cierre |
| Nocturnos | un cierre igual o anterior a la apertura es del día siguiente; sin solapes, tampoco con el día siguiente |
| Duración | de 5 a 480 minutos, en pasos de 5 |
| Precio | ``none``, ``free`` o ``amount`` (``PRICE_KINDS``); «Gratis» no guarda importe |
| Importe | entero en unidades menores, de 0 a 10¹² |
| Categoría | 40 caracteres como máximo, con los espacios colapsados |
| Nombre | de 1 a 120 caracteres, con los espacios colapsados |

Puro (sin base ni reloj) y **solo depende de los modelos**, para que lo importe
cualquiera (esquemas, ``services_catalog``, ``hours``) sin ciclos. Las constantes
de los modelos se reexportan, no se copian.

Espejo de la consola: ``apps/console/src/lib/business-rules.ts``. Un cambio aquí
va con el suyo allí en el mismo commit; las dos pruebas fijan los mismos casos
(``tests/unit/test_business_rules.py`` y
``apps/console/src/lib/__tests__/business-rules.test.ts``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Final

from nexus_api.db.models.business import MAX_SHIFTS_PER_DAY, MINUTES_PER_DAY
from nexus_api.db.models.reservation import PRICE_KINDS

#: Los días de la semana, lunes primero (los de ``hours.DAY_KEYS``).
WEEK_DAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
#: Las horas van en pasos de 5 minutos (la API aceptaba cualquiera: 5.5).
TIME_STEP: Final = 5
DURATION_MIN: Final = 5
DURATION_MAX: Final = 480
DURATION_STEP: Final = 5
#: Con 10⁹, diez millones de pesos colombianos (en céntimos) serían el tope.
AMOUNT_MAX_MINOR: Final = 10**12
#: La columna ``reservation_services.category`` es ``String(40)``.
CATEGORY_MAX: Final = 40
NAME_MIN: Final = 1
#: La columna ``reservation_services.name`` es ``String(120)``.
NAME_MAX: Final = 120

_HHMM: Final = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")
#: El cierre de medianoche: el final del día que abre.
_END_OF_DAY: Final = "24:00"

Shift = tuple[int, int]


class RuleError(ValueError):
    """Un valor que no cumple las reglas. La API responde ``422 {code, field, day}``."""

    def __init__(self, code: str, field: str, *, day: str | None = None) -> None:
        super().__init__(f"{field}: {code}" + (f" ({day})" if day else ""))
        self.code = code
        self.field = field
        self.day = day


# ── las horas ───────────────────────────────────────────────────────────────


def on_step(minutes: int) -> bool:
    """¿Cae en el paso de 5 minutos? Lo que no, se enseña marcado «Revísalo» (5.5)."""
    return minutes % TIME_STEP == 0


def time_minutes(raw: object, *, closing: bool = False, day: str | None = None) -> int:
    """``HH:MM`` → minutos desde la medianoche. ``24:00`` solo vale como cierre."""
    field = "close" if closing else "open"
    if closing and raw == _END_OF_DAY:
        return MINUTES_PER_DAY
    match = _HHMM.fullmatch(raw) if isinstance(raw, str) else None
    if match is None:
        raise RuleError("invalid_time", field, day=day)
    minutes = int(match[1]) * 60 + int(match[2])
    if not on_step(minutes):
        raise RuleError("bad_step", field, day=day)
    return minutes


def shift_minutes(open_: object, close: object, *, day: str | None = None) -> Shift:
    """Un turno en minutos desde la medianoche del día que abre. Un cierre igual o
    anterior a la apertura es del día siguiente; de ``00:00`` a ``24:00`` (o a
    ``00:00``), 24 horas. La misma regla que ``hours.parse_shift``."""
    o = time_minutes(open_, day=day)
    c = time_minutes(close, closing=True, day=day)
    if c == MINUTES_PER_DAY:
        return (o, c)
    return (o, c + MINUTES_PER_DAY if c <= o else c)


def check_day(shifts: Sequence[tuple[object, object]], *, day: str | None = None) -> list[Shift]:
    """Los turnos de un día (``(apertura, cierre)``), en orden. De 0 a 6, sin solapes;
    que uno empiece cuando cierra el anterior sí vale."""
    if len(shifts) > MAX_SHIFTS_PER_DAY:
        raise RuleError("too_many_shifts", "shifts", day=day)
    ordered = sorted(shift_minutes(o, c, day=day) for o, c in shifts)
    for prev, nxt in pairwise(ordered):
        if nxt[0] < prev[1]:
            raise RuleError("overlap", "shifts", day=day)
    return ordered


def check_week(days: Mapping[str, Sequence[tuple[object, object]]]) -> dict[str, list[Shift]]:
    """La semana entera (un día que no está, cerrado). Además de cada día, un turno
    nocturno no puede pisar el primero del día siguiente; el domingo sigue en el lunes."""
    for key in days:
        if key not in WEEK_DAYS:
            raise RuleError("invalid_day", "days", day=key)
    week = {key: check_day(days.get(key, ()), day=key) for key in WEEK_DAYS}
    for i, key in enumerate(WEEK_DAYS):
        spill = max((c - MINUTES_PER_DAY for _, c in week[key] if c > MINUTES_PER_DAY), default=0)
        nxt = week[WEEK_DAYS[(i + 1) % len(WEEK_DAYS)]]
        if spill and nxt and nxt[0][0] < spill:
            raise RuleError("overlap_next_day", "shifts", day=key)
    return week


# ── los servicios ───────────────────────────────────────────────────────────


def duration_ok(minutes: int) -> bool:
    return DURATION_MIN <= minutes <= DURATION_MAX and minutes % DURATION_STEP == 0


def check_duration(minutes: int) -> int:
    if not duration_ok(minutes):
        raise RuleError("bad_duration", "duration_min")
    return minutes


def check_price(kind: str, amount_minor: int | None) -> int | None:
    """El importe que se guarda: solo con ``amount``. «Gratis» y «Sin precio» no
    guardan importe (CHECK ``ck_reservation_services_price_kind``)."""
    if kind not in PRICE_KINDS:
        raise RuleError("price_invalid", "price")
    if kind != "amount":
        return None
    if amount_minor is None:
        raise RuleError("price_amount_required", "price")
    if amount_minor < 0:
        raise RuleError("price_invalid", "price")
    if amount_minor > AMOUNT_MAX_MINOR:
        raise RuleError("amount_too_large", "price")
    return int(amount_minor)


def _collapsed(value: str | None) -> str:
    return " ".join((value or "").split())


def check_category(value: str | None) -> str | None:
    """Recortada y con los espacios de dentro colapsados; vacía es ninguna."""
    category = _collapsed(value) or None
    if category and len(category) > CATEGORY_MAX:
        raise RuleError("category_too_long", "category")
    return category


def check_name(value: str | None) -> str:
    name = _collapsed(value)
    if len(name) < NAME_MIN:
        raise RuleError("name_required", "name")
    if len(name) > NAME_MAX:
        raise RuleError("name_too_long", "name")
    return name


__all__ = [
    "AMOUNT_MAX_MINOR",
    "CATEGORY_MAX",
    "DURATION_MAX",
    "DURATION_MIN",
    "DURATION_STEP",
    "MAX_SHIFTS_PER_DAY",
    "MINUTES_PER_DAY",
    "NAME_MAX",
    "NAME_MIN",
    "PRICE_KINDS",
    "TIME_STEP",
    "WEEK_DAYS",
    "RuleError",
    "Shift",
    "check_category",
    "check_day",
    "check_duration",
    "check_name",
    "check_price",
    "check_week",
    "duration_ok",
    "on_step",
    "shift_minutes",
    "time_minutes",
]
