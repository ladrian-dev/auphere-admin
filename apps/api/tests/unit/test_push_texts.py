"""Spec 031 · R8.1, R8.11, R9.1, R9.2 — el texto de cada aviso (T084).

Avisos normales: el aviso viaja con su título y su texto, compuestos en el
servidor en el idioma del teléfono, y el sistema los muestra tal cual. Por el
camino de Apple y Google va **solo lo mínimo** (R9.2):

- el nombre del contacto, y si no tiene nombre «Un contacto», **nunca** su
  número;
- el motivo del agente o el principio del mensaje, en 100 caracteres como
  mucho;
- el estado del saldo.

Las funciones de aquí son puras: el reparto les pasa los datos ya leídos.
"""

from __future__ import annotations

import pytest

from nexus_api.services import push_texts as pt


@pytest.mark.parametrize("locale", ["es", "en"])
def test_waiting_names_the_contact_and_the_reason(locale: str) -> None:
    text = pt.waiting(
        contact="Martín Ruiz", reason="Pide un reembolso por el pedido #4821.", locale=locale
    )

    assert "Martín Ruiz" in text.title
    assert text.body == "Pide un reembolso por el pedido #4821."
    assert text.title == (
        "Martín Ruiz espera a una persona"
        if locale == "es"
        else "Martín Ruiz is waiting for a person"
    )


def test_waiting_without_reason_still_says_what_to_do() -> None:
    text = pt.waiting(contact="Martín Ruiz", reason="", locale="es")
    assert text.body == "Abre la conversación para ver qué necesita."


@pytest.mark.parametrize(
    "name", [None, "", "   ", "+34 600 123 456", "34600123456", "+54 9 11 6120-3381"]
)
def test_a_contact_without_a_real_name_is_never_its_number(name: str | None) -> None:
    text = pt.waiting(contact=name, reason="x", locale="es")
    assert text.title == "Un contacto espera a una persona"
    for digits in ("600", "6120", "3381"):
        assert digits not in text.title


def test_long_texts_are_cut_at_100_characters() -> None:
    reason = "palabra " * 40
    text = pt.waiting(contact="Ana", reason=reason, locale="es")
    assert len(text.body) <= 100
    assert text.body.endswith("…")


def test_a_message_preview_is_its_start() -> None:
    text = pt.message(
        contact="Lucía", content="Hola, ¿mañana abren a las 9?", media_kind=None, locale="es"
    )
    assert text.title == "Lucía"
    assert text.body == "Hola, ¿mañana abren a las 9?"


@pytest.mark.parametrize(
    ("media", "es", "en"),
    [
        ("image", "Foto", "Photo"),
        ("document", "Documento", "Document"),
        ("audio", "Nota de voz", "Voice note"),
    ],
)
def test_a_file_says_what_it_is_never_its_name(media: str, es: str, en: str) -> None:
    assert pt.message(contact="Lucía", content="", media_kind=media, locale="es").body == es
    assert pt.message(contact="Lucía", content="", media_kind=media, locale="en").body == en


def test_a_file_with_a_caption_shows_the_caption() -> None:
    text = pt.message(contact="Lucía", content="Así llegó", media_kind="image", locale="es")
    assert text.body == "Así llegó"


def test_balance_low_says_how_many_days() -> None:
    text = pt.balance(kind="client.balance_low", days_left=3, contact="Auphere", locale="es")
    assert text.title == "Tu saldo se está agotando"
    assert text.body == "Te alcanza para unos 3 días."


def test_balance_out_says_who_to_ask() -> None:
    es = pt.balance(kind="client.balance_out", days_left=None, contact="Demo Partner", locale="es")
    en = pt.balance(kind="client.balance_out", days_left=None, contact="Demo Partner", locale="en")
    assert es.title == "Te quedaste sin saldo"
    assert es.body == "Pide más saldo a Demo Partner."
    assert en.title == "You're out of balance"
    assert en.body == "Ask Demo Partner for more balance."


def test_one_day_is_singular() -> None:
    assert pt.balance(kind="client.balance_low", days_left=1, contact="x", locale="es").body == (
        "Te alcanza para un día más."
    )
    assert pt.balance(kind="client.balance_low", days_left=1, contact="x", locale="en").body == (
        "Enough for one more day."
    )


def test_an_unknown_locale_falls_back_to_spanish() -> None:
    assert pt.waiting(contact="Ana", reason="x", locale="pt").title == "Ana espera a una persona"


@pytest.mark.parametrize(
    "text",
    [
        "Llamar al +34 611 222 333 mañana",
        "Mi número es 611222333",
        "WhatsApp: (11) 6120-3381",
        "+54 9 11 6120-3381 urgente",
    ],
)
def test_a_phone_written_inside_a_free_text_never_travels(text: str) -> None:
    for body in (
        pt.waiting(contact="Ana", reason=text, locale="es").body,
        pt.message(contact="Ana", content=text, media_kind=None, locale="es").body,
    ):
        assert "•••" in body
        assert sum(c.isdigit() for c in body) < 7


def test_short_numbers_are_kept() -> None:
    body = pt.waiting(contact="Ana", reason="Pedido #4821 del día 12", locale="es").body
    assert body == "Pedido #4821 del día 12"
