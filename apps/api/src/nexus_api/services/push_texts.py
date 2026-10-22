"""El texto de cada aviso al teléfono — spec 031, R8.1, R8.11, R9 (contracts/push.md).

Avisos normales: viajan con título y texto, en el idioma del teléfono, y el
sistema los muestra tal cual. Lo que viaja por Apple y Google es **lo mínimo
que el aviso enseña** (R9.2) y nada más:

- el nombre del contacto, o «Un contacto» si no tiene un nombre de verdad —
  **nunca** su número, ni aunque el nombre guardado sea un número;
- el motivo del agente o el principio del mensaje, cortado a 100 caracteres;
  un archivo se dice por su tipo, nunca por su nombre;
- el estado del saldo.

Funciones puras: el reparto lee los datos y se los pasa. Así lo que sale hacia
fuera se puede probar sin base de datos (``test_push_texts``) y barrer
(``test_push_payload_no_customer_content``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

#: Lo más largo que viaja de un texto libre (R9.2).
MAX_TEXT = 100

_PHONE_LIKE = re.compile(r"^[\s+()\-.\d]*$")
#: Una secuencia con forma de teléfono dentro de un texto libre (siete dígitos o
#: más, con los separadores habituales). El motivo del agente y el mensaje del
#: contacto son texto libre y pueden traer uno escrito: no viaja (R9.2).
_PHONE_IN_TEXT = re.compile(r"\+?\d[\d\s().\-]{5,}\d")


@dataclass(frozen=True)
class NoticeText:
    title: str
    body: str


def _lang(locale: str) -> str:
    return "en" if locale == "en" else "es"


def scrub(text: str) -> str:
    """Tapa los números con forma de teléfono que traiga un texto libre."""
    return _PHONE_IN_TEXT.sub(
        lambda m: "•••" if sum(c.isdigit() for c in m.group(0)) >= 7 else m.group(0), text
    )


def cut(text: str, limit: int = MAX_TEXT) -> str:
    """Una línea, sin espacios de sobra, sin teléfonos y como mucho ``limit``
    caracteres."""
    flat = scrub(" ".join((text or "").split()))
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def contact_label(name: str | None, locale: str) -> str:
    """El nombre del contacto, o «Un contacto». Un «nombre» que solo tiene
    dígitos y signos de teléfono es un número, y un número no viaja."""
    clean = " ".join((name or "").split())
    if not clean or (_PHONE_LIKE.match(clean) and sum(c.isdigit() for c in clean) >= 5):
        return "A contact" if _lang(locale) == "en" else "Un contacto"
    return cut(clean, 60)


def waiting(*, contact: str | None, reason: str | None, locale: str) -> NoticeText:
    who = contact_label(contact, locale)
    if _lang(locale) == "en":
        title = f"{who} is waiting for a person"
        fallback = "Open the conversation to see what they need."
    else:
        title = f"{who} espera a una persona"
        fallback = "Abre la conversación para ver qué necesita."
    body = cut(reason or "") or fallback
    return NoticeText(title=cut(title), body=body)


_MEDIA = {
    "image": ("Foto", "Photo"),
    "document": ("Documento", "Document"),
    "audio": ("Nota de voz", "Voice note"),
    "video": ("Vídeo", "Video"),
    "sticker": ("Sticker", "Sticker"),
}


def message(
    *, contact: str | None, content: str | None, media_kind: str | None, locale: str
) -> NoticeText:
    who = contact_label(contact, locale)
    body = cut(content or "")
    if not body and media_kind:
        es, en = _MEDIA.get(media_kind, ("Archivo", "File"))
        body = en if _lang(locale) == "en" else es
    if not body:
        body = "New message" if _lang(locale) == "en" else "Mensaje nuevo"
    return NoticeText(title=who, body=body)


def balance(*, kind: str, days_left: int | None, contact: str, locale: str) -> NoticeText:
    en = _lang(locale) == "en"
    who = cut(contact, 60)
    if kind == "client.balance_out":
        return NoticeText(
            title="You're out of balance" if en else "Te quedaste sin saldo",
            body=f"Ask {who} for more balance." if en else f"Pide más saldo a {who}.",
        )
    title = "Your balance is running low" if en else "Tu saldo se está agotando"
    if days_left is None:
        body = "Check your usage." if en else "Revisa tu consumo."
    elif days_left <= 1:
        body = "Enough for one more day." if en else "Te alcanza para un día más."
    else:
        body = (
            f"Enough for about {days_left} days."
            if en
            else f"Te alcanza para unos {days_left} días."
        )
    return NoticeText(title=title, body=body)


_DAYS = {
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}


def reservas(
    *, kind: str, at: datetime, party: int | None, changed: bool, locale: str
) -> NoticeText:
    """Spec 043: los avisos de Reservas. La hora y, en Aforo, cuántos; **nunca**
    el nombre del cliente final ni la nota (R9.2 de la 031)."""
    lang = _lang(locale)
    en = lang == "en"
    day = _DAYS[lang][at.weekday()]
    hour = at.strftime("%H:%M")
    people = ""
    if party is not None:
        people = f" · {party} people" if en else f" · {party} personas"
    if kind == "reservas.agent_change":
        title = (
            ("Booking changed" if en else "Reserva cambiada")
            if changed
            else ("New booking" if en else "Reserva nueva")
        )
        body = (
            f"The agent booked {day} {at.day} at {hour}{people}"
            if en
            else f"El agente reservó para el {day} {at.day} a las {hour}{people}"
        )
        return NoticeText(title=title, body=body)
    if kind == "reservas.cancelled_today":
        return NoticeText(
            title="Today's cancellation" if en else "Cancelación de hoy",
            body=f"The {hour} booking is free again{people}"
            if en
            else f"Se liberó la reserva de las {hour}{people}",
        )
    return NoticeText(
        title="Waitlist" if en else "Lista de espera",
        body=f"Someone took the {hour} slot" if en else f"Alguien aceptó el hueco de las {hour}",
    )


__all__ = [
    "MAX_TEXT",
    "NoticeText",
    "balance",
    "contact_label",
    "cut",
    "message",
    "reservas",
    "scrub",
    "waiting",
]
