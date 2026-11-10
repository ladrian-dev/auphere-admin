"""El freno de citas, en funciones puras (spec 056, T012 · requisitos 1.1 y 1.3).

Dos preguntas, sin modelo ni base:

- **¿Puede ser una afirmación?** Un filtro de palabras, sin tildes, en es, en y
  pt. Lo que no pasa el filtro sale sin llamar a nadie. Lo que lo pasa no es aún
  una afirmación: lo decide el clasificador (``test_pipeline_booking_brake.py``).
- **¿La respalda algo de este turno?** Por herramienta, con la tabla de
  ``research.md`` R1. ``reservas.create`` y ``reservas.reschedule`` contestan
  ``status: ok`` también cuando rechazan: solo respalda la reserva devuelta sin
  ``refused``. El enlace de un solo uso de Calendly no respalda: con él reserva
  el cliente.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_worker.runtime import booking_brake

# ── el filtro ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Listo, tu cita quedó confirmada para el viernes a las 10.",
        "Te he reservado el sábado a las 11:00.",
        "Perfecto, ya está agendado con Lucía.",
        "Te apunté para el martes.",
        "He cambiado la hora: ahora es a las 12.",
        "Reprogramada para el lunes a las 9.",
        "Te esperamos el jueves.",
        "Está CONFIRMADA, gracias.",
        "Your appointment is booked for Friday at 10.",
        "Done, it's confirmed.",
        "Your visit is scheduled for 3 pm.",
        "Seu horário está marcado para sexta.",
        "Pronto, está confirmado!",
        "Agendado para amanhã às 10h.",
    ],
)
def test_the_filter_catches_a_booking_taken_for_granted(text: str) -> None:
    assert booking_brake.might_claim(text)


@pytest.mark.parametrize(
    "text",
    [
        "¿Quieres que te reserve?",
        "No pude reservar.",
        "¿Qué día te viene bien?",
        "Abrimos de 10 a 14.",
        "Hola, ¿en qué te ayudo?",
        "Do you want me to book it?",
        "Quer que eu reserve?",
        "",
    ],
)
def test_the_filter_lets_an_offer_a_question_or_a_failure_through(text: str) -> None:
    assert not booking_brake.might_claim(text)


def test_the_filter_reads_the_buttons_and_the_body_of_an_interactive_reply() -> None:
    """La afirmación puede ir en el componente y no en el texto."""
    interactive = {
        "body": "Elige una opción",
        "buttons": [{"id": "ok", "title": "Cita confirmada"}, {"id": "no", "title": "Cambiar"}],
    }
    draft = booking_brake.draft_text("", interactive)
    assert "Elige una opción" in draft and "Cita confirmada" in draft
    assert booking_brake.might_claim(draft)
    listed = {
        "body": "Estos son tus datos",
        "list": {
            "button": "Ver",
            "sections": [{"title": "Hoy", "rows": [{"id": "1", "title": "Te esperamos a las 10"}]}],
        },
    }
    assert booking_brake.might_claim(booking_brake.draft_text("Hola", listed))


# ── el respaldo, por herramienta (research R1) ─────────────────────────────

BRIEF = {"id": "7f0c", "date": "2026-11-13", "start": "10:00", "end": "10:30"}


def _env(tool: str, status: str = "ok", **result: Any) -> dict[str, Any]:
    return {"tool": tool, "status": status, "result": dict(result)}


BACKS: list[tuple[str, dict[str, Any]]] = [
    ("reservas.create con reserva", _env("reservas.create", booking=BRIEF, refused=None)),
    ("reservas.reschedule con reserva", _env("reservas.reschedule", booking=BRIEF)),
    ("reservas.answer_offer booked", _env("reservas.answer_offer", result="booked", booking=BRIEF)),
    ("booking.create_appointment ok", _env("booking.create_appointment", appointment_id="a1")),
    ("booking.modify_appointment ok", _env("booking.modify_appointment", appointment_id="a1")),
    ("Google Calendar, crear", _env("GOOGLECALENDAR_CREATE_EVENT", data={"id": "e"}, error=None)),
    ("Google Calendar, rápido", _env("GOOGLECALENDAR_QUICK_ADD", data={"id": "e"}, error=None)),
    ("Google Calendar, cambiar", _env("GOOGLECALENDAR_UPDATE_EVENT", data={"id": "e"})),
    ("Calendly, reservar", _env("CALENDLY_POST_INVITEE", data={"uri": "u"}, error=None)),
    ("cita mantenida, list_mine", _env("reservas.list_mine", bookings=[BRIEF])),
    ("cita mantenida, confirm_attendance", _env("reservas.confirm_attendance", booking=BRIEF)),
    ("Playground", _env("reservas.create", "skipped:dry_run", ok=True, blocked_by="dry_run")),
    (
        "reintento del turno",
        {**_env("reservas.create", booking=BRIEF, refused=None), "replayed": True},
    ),
    (
        "reintento a medias",
        {**_env("reservas.create", "skipped:already_attempted", note="x"), "replayed": True},
    ),
]

DOES_NOT_BACK: list[tuple[str, dict[str, Any]]] = [
    (
        "reservas.create rechazada con status ok",
        _env("reservas.create", booking=None, refused="hours_missing", first_fit=None),
    ),
    ("reservas.create, reserva y rechazo", _env("reservas.create", booking=BRIEF, refused="x")),
    ("reservas.reschedule rechazada", _env("reservas.reschedule", booking=None, refused="closed")),
    # Fallo ``la-reserva-del-turno-siguiente-pierde-los-ids``: un servicio o una persona
    # que no se resuelve es un rechazo con opciones, nunca una reserva.
    (
        "reservas.create con un servicio desconocido",
        _env(
            "reservas.create",
            booking=None,
            refused="unknown_service",
            services=[{"id": "s1", "name": "Corte"}],
        ),
    ),
    (
        "reservas.reschedule con una persona ambigua",
        _env(
            "reservas.reschedule",
            booking=None,
            refused="ambiguous_staff",
            staff=[{"id": "p1", "name": "Lucía"}, {"id": "p2", "name": "Lucas"}],
        ),
    ),
    ("answer_offer late_taken", _env("reservas.answer_offer", result="late_taken", booking=None)),
    ("answer_offer declined", _env("reservas.answer_offer", result="declined", booking=None)),
    ("booking.create_appointment error", _env("booking.create_appointment", "error")),
    ("error de Composio", _env("GOOGLECALENDAR_CREATE_EVENT", "error", data={}, error="boom")),
    (
        "enlace de un solo uso de Calendly",
        _env("CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK", data={"booking_url": "https://x"}),
    ),
    ("list_mine sin reservas", _env("reservas.list_mine", bookings=[])),
    ("pendiente de aprobación", _env("reservas.create", "approval_requested", message="x")),
    ("aprobación denegada", _env("reservas.create", "approval_denied", message="x")),
    ("fuera de la lista", _env("reservas.create", "skipped:not_in_whitelist")),
    (
        "reintento de un rechazo",
        {**_env("reservas.create", booking=None, refused="slot_taken"), "replayed": True},
    ),
    ("cancelar", _env("reservas.cancel", booking=BRIEF, offered_to_waitlist=False)),
    ("otra herramienta", _env("client.get_history", visits=2)),
]


@pytest.mark.parametrize(("case", "envelope"), BACKS, ids=[c for c, _ in BACKS])
def test_a_booking_that_was_made_backs_the_reply(case: str, envelope: dict[str, Any]) -> None:
    assert booking_brake.backs(envelope), case
    assert booking_brake.is_backed([_env("client.get_history"), envelope])


@pytest.mark.parametrize(("case", "envelope"), DOES_NOT_BACK, ids=[c for c, _ in DOES_NOT_BACK])
def test_a_refusal_an_error_or_a_link_does_not_back_the_reply(
    case: str, envelope: dict[str, Any]
) -> None:
    assert not booking_brake.backs(envelope), case
    assert not booking_brake.is_backed([envelope])


def test_nothing_backs_an_empty_turn() -> None:
    assert not booking_brake.is_backed([])
    assert not booking_brake.attempted([])


def test_a_booking_attempt_that_failed_is_told_apart_from_no_attempt() -> None:
    """Una reserva intentada y rechazada en este turno no la cubre una reserva
    de antes: la respuesta puede estar dando por hecha la nueva."""
    refused = _env("reservas.create", booking=None, refused="hours_missing")
    assert booking_brake.attempted([refused])
    assert booking_brake.attempted([_env("GOOGLECALENDAR_CREATE_EVENT", "error", error="x")])
    assert not booking_brake.attempted([_env("reservas.list_mine", bookings=[])])
    assert not booking_brake.attempted([_env("client.get_history")])
    assert not booking_brake.attempted([refused, _env("reservas.create", booking=BRIEF)]), (
        "si el segundo intento reservó, ya no es un intento fallido"
    )


def test_an_unknown_service_is_a_failed_attempt_and_never_backs() -> None:
    """Con la salida de verdad de ``reservas.create``: ``unknown_service`` trae las
    opciones para reintentar, no respalda «te reservé» y cuenta como intento
    fallido, así que una reserva de antes no lo cubre."""
    import uuid

    from nexus_mcp.servers.reservas.schemas import CreateOutput, ServiceRef

    out = CreateOutput(
        refused="unknown_service", services=[ServiceRef(id=uuid.uuid4(), name="Corte")]
    )
    envelope = {"tool": "reservas.create", "status": "ok", "result": out.model_dump(mode="json")}
    assert envelope["result"]["booking"] is None
    assert not booking_brake.backs(envelope)
    assert booking_brake.attempted([envelope])
    retried = _env("reservas.create", booking=BRIEF, refused=None)
    assert not booking_brake.attempted([envelope, retried]), "el reintento con la opción reservó"
    assert booking_brake.is_backed([envelope, retried])


def test_the_booking_tools_come_from_the_actions_of_capability_names() -> None:
    """La lista sale de ``TOOL_ACTIONS`` (reservar o cambiar una cita), sin las
    cancelaciones y sin el enlace de Calendly. Google Calendar reserva también
    con el alta rápida y cambia con la edición del evento (T016)."""
    assert booking_brake.booking_tools() == frozenset(
        {
            "reservas.create",
            "reservas.reschedule",
            "reservas.answer_offer",
            "booking.create_appointment",
            "booking.modify_appointment",
            "CALENDLY_POST_INVITEE",
            "GOOGLECALENDAR_CREATE_EVENT",
            "GOOGLECALENDAR_QUICK_ADD",
            "GOOGLECALENDAR_UPDATE_EVENT",
        }
    )


def test_the_history_of_the_conversation_counts_only_the_connectors_and_the_old_tools() -> None:
    """De los turnos de antes manda la agenda: una reserva de Reservas respalda
    si sigue viva en ``reservations``, no porque un sobre viejo dijera ``ok``
    (pudo cancelarse después)."""
    old_reservas = _env("reservas.create", booking=BRIEF, refused=None)
    old_calendar = _env("GOOGLECALENDAR_CREATE_EVENT", data={"id": "e"}, error=None)
    assert not booking_brake.history_backed([old_reservas])
    assert booking_brake.history_backed([old_calendar])
    assert booking_brake.history_backed([{"not": "an envelope"}, old_calendar])
    assert not booking_brake.history_backed(["garbage", None])  # type: ignore[list-item]


def test_the_brake_note_says_it_was_not_sent_and_what_to_do() -> None:
    note = booking_brake.BOOKING_BRAKE_NOTE
    assert "no se envió" in note.lower()
    assert "herramienta" in note and "verdad" in note
    # Constitución §III: una instrucción de la plataforma va como ``system``, nunca
    # con forma de cliente. Y sin el borrador: como ``assistant``, el hilo acabaría
    # en él (LiteLLM sube todo ``system`` a la cabecera de Anthropic).
    assert booking_brake.retry_messages() == [{"role": "system", "content": note}]
