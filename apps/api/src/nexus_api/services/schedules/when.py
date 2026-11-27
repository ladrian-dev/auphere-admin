"""Cuándo le toca a una rutina — spec 082, T008 (requisitos 3.2, 3.4, 3.5, 3.7).

Función pura: ni base de datos, ni reloj escondido. Recibe la periodicidad, la
hora **local del negocio** y su zona, y devuelve las próximas ejecuciones en
absoluto. El disparador la usa para materializar ``next_run_at``, y el alta la
usa para enseñar las próximas antes de guardar.

Por qué la hora se guarda local y no en UTC: las nueve de la mañana en Santiago
no son la misma hora UTC en enero que en julio. Guardada en UTC, la rutina se
correría una hora en cada cambio de reloj, y nadie la movería de vuelta.

Los dos días raros del año, que son los que rompen esto si no se miran:

- **La hora que no existe.** El reloj se adelanta y las 02:30 no ocurren. La
  rutina se corre a la primera hora que sí existe ese día, en vez de perderse.
- **La hora que ocurre dos veces.** El reloj se atrasa y las 02:30 pasan dos
  veces. Se ejecuta una sola vez, la primera.

La convención de los días de la semana es la de Python: **lunes 0, domingo 6**,
la misma que ``datetime.weekday()`` y que ``WEEKDAYS`` en
``services/business_hours.py``. La consola traduce, porque en JavaScript el
domingo es 0.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Las cuatro periodicidades, y ninguna más.
CADENCES: Final[frozenset[str]] = frozenset({"daily", "weekly", "monthly", "once"})
#: Hasta dónde se busca antes de rendirse. Una semanal con un solo día necesita
#: siete vueltas, no cuatrocientas, pero una rutina de un día que no llega nunca
#: tiene que parar en algún sitio.
_MAX_DAYS: Final = 400
_MAX_MONTHS: Final = 24
#: Lo que puede durar el salto de un cambio de hora. Dos horas es más de lo que
#: usa ninguna zona, y acota la búsqueda de la primera hora que existe.
_MAX_GAP_MINUTES: Final = 120


def zone(name: str) -> ZoneInfo:
    """La zona del negocio. Una zona que no existe es un error, no un UTC
    silencioso: una rutina que se ejecuta a la hora equivocada sin avisar es
    peor que una que no se deja guardar."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"zona horaria desconocida: {name}") from exc


def _exists(naive: datetime, tz: ZoneInfo) -> bool:
    """``False`` si esa hora local no ocurre ese día (el reloj se adelantó)."""
    attached = naive.replace(tzinfo=tz)
    return attached.astimezone(UTC).astimezone(tz).replace(tzinfo=None) == naive


def _ambiguous(naive: datetime, tz: ZoneInfo) -> bool:
    """``True`` si esa hora local ocurre dos veces (el reloj se atrasó)."""
    first = naive.replace(tzinfo=tz, fold=0)
    second = naive.replace(tzinfo=tz, fold=1)
    return first.utcoffset() != second.utcoffset()


def resolve(day: date, local_time: time, tz: ZoneInfo) -> datetime:
    """El instante absoluto de esa hora local ese día, resueltos los dos casos
    del cambio de hora. Siempre devuelve algo: un día tiene al menos una hora."""
    naive = datetime.combine(day, local_time)
    if not _exists(naive, tz):
        # El reloj se adelantó: busca la primera hora que sí existe.
        for minutes in range(1, _MAX_GAP_MINUTES + 1):
            candidate = naive + timedelta(minutes=minutes)
            if candidate.date() == day and _exists(candidate, tz):
                naive = candidate
                break
        else:  # pragma: no cover — ninguna zona salta dos horas enteras
            naive = datetime.combine(day, time(0, 0))
    # Si ocurre dos veces, la primera (``fold=0``): una ejecución, no dos.
    return naive.replace(tzinfo=tz, fold=0).astimezone(UTC)


def _candidate_days(
    *,
    cadence: str,
    start: date,
    weekdays: list[int] | None,
    day_of_month: int | None,
    run_date: date | None,
):
    if cadence == "once":
        if run_date is not None:
            yield run_date
        return
    if cadence == "monthly":
        target = day_of_month or 1
        year, month = start.year, start.month
        for _ in range(_MAX_MONTHS):
            yield date(year, month, target)
            month += 1
            if month > 12:
                month, year = 1, year + 1
        return
    wanted = set(weekdays or []) if cadence == "weekly" else set(range(7))
    if not wanted:
        return
    for offset in range(_MAX_DAYS):
        day = start + timedelta(days=offset)
        if day.weekday() in wanted:
            yield day


def next_runs(
    *,
    cadence: str,
    local_time: time,
    timezone: str,
    weekdays: list[int] | None = None,
    day_of_month: int | None = None,
    run_date: date | None = None,
    after: datetime | None = None,
    count: int = 3,
) -> list[datetime]:
    """Las próximas ``count`` ejecuciones, en UTC y estrictamente después de
    ``after``. Una lista vacía significa que no hay próxima: una rutina de una
    sola vez ya pasada, o una semanal sin ningún día marcado."""
    if cadence not in CADENCES:
        raise ValueError(f"periodicidad desconocida: {cadence}")
    tz = zone(timezone)
    cut = (after or datetime.now(UTC)).astimezone(UTC)
    # Se empieza por el día local de ``cut``, no por el siguiente: si la hora
    # de hoy aún no ha pasado, hoy cuenta.
    start = cut.astimezone(tz).date()

    out: list[datetime] = []
    for day in _candidate_days(
        cadence=cadence,
        start=start,
        weekdays=weekdays,
        day_of_month=day_of_month,
        run_date=run_date,
    ):
        moment = resolve(day, local_time, tz)
        if moment > cut:
            out.append(moment)
            if len(out) >= count:
                break
    return out


def next_run(**kwargs: object) -> datetime | None:
    """La siguiente, o ``None``. Es lo que se materializa en ``next_run_at``."""
    runs = next_runs(**kwargs, count=1)  # type: ignore[arg-type]
    return runs[0] if runs else None


__all__ = ["CADENCES", "next_run", "next_runs", "resolve", "zone"]
