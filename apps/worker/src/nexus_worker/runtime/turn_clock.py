"""Qué hora es, dicho al modelo — spec 015, Requisito 5.

Vivía dentro de ``pipeline.py``, que es el grafo entero del agente de canal, y
**lo usan dos agentes**: el de canal desde 2026-08-19 y el teammate desde la
spec 015. Se movió aquí en vez de copiarse: una tercera copia del mismo texto es
exactamente el defecto que la 015 viene a cerrar, y ``pipeline`` lo sigue
re-exportando para que nadie de fuera se entere del cambio.

**Por qué existe, con su fecha.** Sin esto el modelo no sabe qué día es y
contesta a las preguntas de fecha desde lo que aprendió al entrenarse. No es
teórico: el 2026-08-19 el agente de cobranza ofreció ``(ejemplo: 2025-08-30)``
como formato de vencimiento, quien administraba copió el ejemplo, y se creó una
cuenta real **con un año de retraso** — lo que además dejó sus ventanas de
recordatorio permanentemente en el pasado.

**La zona importa y no es UTC.** Es la única forma de que «hoy», «mañana» o «el
viernes» signifiquen lo que quiso decir quien los escribió. Para un negocio en
``America/Caracas``, la fecha UTC ya es mañana a partir de las 20:00 locales.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog

log = structlog.get_logger(__name__)

_WEEKDAYS_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

#: De quién es la zona horaria, en genitivo y dentro de la frase.
#:
#: El agente de canal trabaja para un negocio y el teammate para una persona, y
#: decir «la zona horaria del negocio» a quien está hablando con su teammate
#: sería mentir por descuido. El valor por defecto es el del canal **para que su
#: texto siga siendo byte a byte el de antes del movimiento**.
OWNER_BUSINESS = "del negocio"
OWNER_PERSON = "de la persona con la que hablas"


def now_note(
    timezone_name: str,
    *,
    now: datetime | None = None,
    owner: str = OWNER_BUSINESS,
) -> str:
    """Una instrucción de sistema que dice qué día y qué hora es.

    Pura: misma zona y mismo ``now`` producen siempre el mismo texto. Eso
    importa más de lo que parece — dos representaciones distintas del mismo
    instante serían dos entradas de caché distintas para nada.
    """
    # Una cadena vacía **no lanza**: `ZoneInfo("" or "UTC")` resuelve a UTC sin
    # error, y el nombre se quedaba vacío — la nota decía «en la zona horaria
    # de la persona ():». Se normaliza antes, para que el repliegue quede
    # marcado igual que cuando la zona es inválida.
    timezone_name = (timezone_name or "").strip() or "UTC"
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        # Una zona malformada no puede matar el turno. UTC **con marca
        # visible** es mejor que fingir en silencio que sabemos la local.
        log.warning("pipeline.now_note.unknown_timezone", timezone=timezone_name)
        tz = ZoneInfo("UTC")
        timezone_name = "UTC"
    local = (now or datetime.now(UTC)).astimezone(tz)
    weekday = _WEEKDAYS_ES[local.weekday()]
    return (
        "Fecha y hora actuales en la zona horaria "
        f"{owner} ({timezone_name}): {weekday} {local.strftime('%d/%m/%Y')}, "
        f"{local.strftime('%H:%M')}. En formato ISO, hoy es "
        f"{local.date().isoformat()}.\n"
        "Usa SIEMPRE esta fecha para resolver referencias relativas ('hoy', "
        "'mañana', 'el viernes', 'fin de mes', 'en 15 días') y para decidir si "
        "algo está vencido. NUNCA deduzcas el año ni la fecha de tu propio "
        "conocimiento: la de arriba es la única correcta."
    )


def turn_environment(
    *,
    timezone_name: str | None,
    machine_present: bool,
    client_timezone: str | None = None,
    now: datetime | None = None,
) -> str:
    """El bloque de entorno de un turno de teammate — spec 015, Requisito 5.

    Va **lo último antes del mensaje de la persona**, no junto a la identidad:
    cambia cada minuto, y arriba invalidaría el punto de corte del caché en
    cada turno.

    ``timezone_name`` es la de **la persona que escribe**, que la manda la
    aplicación. Se eligió así porque el partner no tiene columna de zona
    horaria y la persona tampoco: la única que existe en la base es la del
    cliente final, y «el viernes» lo dice quien escribe, no el negocio del que
    se habla.

    ``client_timezone`` se nombra **además**, cuando el turno va de un cliente
    concreto, y nunca en lugar de la otra: son dos datos distintos y el
    requisito pide los dos.
    """
    partes = [now_note(timezone_name or "", now=now, owner=OWNER_PERSON)]
    if client_timezone and client_timezone != timezone_name:
        partes.append(
            f"El cliente del que estáis hablando opera en {client_timezone}; "
            "tenlo en cuenta al hablar de sus horarios, sin cambiar la tuya."
        )
    partes.append(
        "Tu máquina está conectada: puedes ejecutar ahora."
        if machine_present
        else "Tu máquina no está conectada ahora mismo, así que no puedes "
        "ejecutar nada en ella. Sigue con lo que no la necesite y dilo."
    )
    return "\n".join(partes)


__all__ = ["OWNER_BUSINESS", "OWNER_PERSON", "now_note", "turn_environment"]
