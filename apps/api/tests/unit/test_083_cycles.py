"""Spec 083 (T001) — el constructor de ciclos y sus piezas puras.

Una fila de ``conversations`` es un contacto en un número y se reabre: contar
filas no es contar conversaciones. Aquí, sin base, las reglas de ``research.md``
R1 a R4: dónde empieza y acaba un ciclo (D3), qué ciclo es del periodo (D2), su
día en la zona del cliente, si fue con persona, su primera respuesta (D8) y el
motivo de una incidencia como código (D7).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from nexus_api.services.client_report import AgendaEvent, agenda_counts
from nexus_api.services.improvement.performance import (
    Send,
    Span,
    assemble_cycles,
    assemble_incidents,
    build_spans,
    escalation_cause,
    local_day,
)

T0 = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
CARACAS = ZoneInfo("America/Caracas")


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


# ── build_spans (R1, D3) ───────────────────────────────────────────────────


def test_a_row_without_events_is_one_open_cycle() -> None:
    assert build_spans(T0, []) == [Span(T0, None)]


def test_resolve_and_the_contact_writes_again_are_two_cycles() -> None:
    spans = build_spans(T0, [(at(10), "resolved", "system"), (at(60), "reopened", "contact")])
    assert spans == [Span(T0, at(10)), Span(at(60), None)]


def test_a_notice_that_reopens_starts_a_cycle_too() -> None:
    spans = build_spans(T0, [(at(10), "resolved", "client:ana@x"), (at(60), "reopened", "system")])
    assert spans == [Span(T0, at(10)), Span(at(60), None)]


def test_a_person_who_reopens_undoes_the_resolution() -> None:
    """Spec 064 (4.4): reabrir a mano deshace la resolución, así que es el mismo ciclo."""
    spans = build_spans(
        T0, [(at(10), "resolved", "client:ana@x"), (at(12), "reopened", "client:ana@x")]
    )
    assert spans == [Span(T0, None)]


def test_two_resolutions_in_a_row_close_once() -> None:
    spans = build_spans(T0, [(at(10), "resolved", "system"), (at(20), "resolved", "system")])
    assert spans == [Span(T0, at(10))]


def test_a_reopen_without_a_resolution_still_starts_a_cycle() -> None:
    assert build_spans(T0, [(at(30), "reopened", "contact")]) == [
        Span(T0, at(30)),
        Span(at(30), None),
    ]


def test_the_order_of_the_input_does_not_matter() -> None:
    events = [(at(60), "reopened", "contact"), (at(10), "resolved", "system")]
    assert build_spans(T0, events) == [Span(T0, at(10)), Span(at(60), None)]


# ── el día local ───────────────────────────────────────────────────────────


def test_half_past_eleven_at_night_in_caracas_is_that_day() -> None:
    # 23:30 del 12 en Caracas (UTC-4) son las 03:30 UTC del 13.
    late = datetime(2026, 11, 13, 3, 30, tzinfo=UTC)
    assert local_day(late, CARACAS) == date(2026, 11, 12)
    assert local_day(late, ZoneInfo("UTC")) == date(2026, 11, 13)


# ── assemble_cycles (R2, R3, D2, D8, D9) ───────────────────────────────────


def _cycles(**kw):
    conv = kw.pop("conv")
    defaults = {
        "spans": {conv: [Span(T0, None)]},
        "contact_times": {conv: [at(1)]},
        "contact_before": {},
        "agent_sends": {},
        "person_signals": {},
        "zone": CARACAS,
    }
    defaults.update(kw)
    return assemble_cycles(**defaults)


def test_a_cycle_counts_on_the_local_day_of_its_first_contact_message() -> None:
    conv = uuid.uuid4()
    late = datetime(2026, 11, 13, 3, 30, tzinfo=UTC)
    (cycle,) = _cycles(conv=conv, spans={conv: [Span(late, None)]}, contact_times={conv: [late]})
    assert cycle.day == date(2026, 11, 12)
    assert cycle.first_contact_at == late


def test_a_cycle_where_the_contact_never_wrote_is_not_a_conversation() -> None:
    conv = uuid.uuid4()
    assert _cycles(conv=conv, contact_times={conv: []}) == []


def test_a_cycle_that_began_before_the_period_is_not_of_the_period() -> None:
    """D2: el primer mensaje del contacto en el ciclo es anterior al periodo."""
    conv = uuid.uuid4()
    assert (
        _cycles(
            conv=conv,
            contact_before={conv: T0 - timedelta(days=2)},
            spans={conv: [Span(T0 - timedelta(days=3), None)]},
        )
        == []
    )


def test_a_message_before_the_period_but_in_an_older_cycle_does_not_count() -> None:
    conv = uuid.uuid4()
    spans = {conv: [Span(T0 - timedelta(days=3), T0 - timedelta(days=2)), Span(T0, None)]}
    (cycle,) = _cycles(
        conv=conv, spans=spans, contact_before={conv: T0 - timedelta(days=2, hours=1)}
    )
    assert cycle.start == T0


def test_each_cycle_with_a_contact_message_counts_once() -> None:
    conv = uuid.uuid4()
    spans = {conv: [Span(T0, at(30)), Span(at(60), None)]}
    cycles = _cycles(conv=conv, spans=spans, contact_times={conv: [at(1), at(5), at(61)]})
    assert [c.first_contact_at for c in cycles] == [at(1), at(61)]


def test_the_first_reply_runs_to_when_the_provider_took_the_agents_message() -> None:
    """D8: la hora de creación más ``latency_ms``; mide desde el primer mensaje."""
    conv = uuid.uuid4()
    sends = {conv: [Send(at(1) + timedelta(seconds=55), timedelta(seconds=15))]}
    (cycle,) = _cycles(conv=conv, agent_sends=sends, contact_times={conv: [at(1), at(1.2)]})
    assert cycle.first_reply_seconds == 70


def test_a_reply_from_another_cycle_is_not_this_ones() -> None:
    conv = uuid.uuid4()
    spans = {conv: [Span(T0, at(30)), Span(at(60), None)]}
    sends = {conv: [Send(at(2), timedelta(0))]}
    cycles = _cycles(
        conv=conv, spans=spans, contact_times={conv: [at(1), at(61)]}, agent_sends=sends
    )
    assert [c.first_reply_seconds for c in cycles] == [60, None]


def test_with_person_is_any_signal_inside_the_cycle() -> None:
    conv = uuid.uuid4()
    spans = {conv: [Span(T0, at(30)), Span(at(60), None)]}
    cycles = _cycles(
        conv=conv,
        spans=spans,
        contact_times={conv: [at(1), at(61)]},
        person_signals={conv: [at(10)]},
    )
    assert [c.with_person for c in cycles] == [True, False]


# ── el motivo (R4, D7) ─────────────────────────────────────────────────────


def test_the_cause_is_a_code_never_the_agents_words() -> None:
    assert escalation_cause("agent", "El cliente dice que Roxana lo trató mal") == "escalated"
    assert escalation_cause("system", "escalated") == "escalated"
    assert escalation_cause("system", "no_balance") == "no_balance"
    assert escalation_cause("system", "booking_unbacked") == "booking_unbacked"
    assert escalation_cause("system", "something_new") == "other"
    assert escalation_cause("system", None) == "other"


def test_the_brake_that_hands_over_is_one_incident() -> None:
    """D6: el freno ``handed_off`` ya es el escalado ``booking_unbacked``."""
    conv = uuid.uuid4()
    incidents = assemble_incidents(
        escalations=[(conv, at(5), "system", "booking_unbacked")],
        brakes=[(conv, at(5), "handed_off"), (conv, at(20), "retried")],
        spans={conv: [Span(T0, at(40)), Span(at(60), None)]},
    )
    assert [(i.cause, i.resolved_at) for i in incidents] == [
        ("booking_brake", at(40)),
        ("booking_unbacked", at(40)),
    ]


def test_an_incident_of_an_open_cycle_is_open() -> None:
    conv = uuid.uuid4()
    (incident,) = assemble_incidents(
        escalations=[(conv, at(65), "agent", "texto libre")],
        brakes=[],
        spans={conv: [Span(T0, at(40)), Span(at(60), None)]},
    )
    assert incident.cause == "escalated" and incident.resolved_at is None


# ── la agenda (R5, D10, D11) ───────────────────────────────────────────────


def test_who_did_what_in_the_agenda() -> None:
    r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    events = [
        AgendaEvent(r1, "created", "agent", None, at(0)),
        AgendaEvent(r2, "created", "person", "Ana", at(0)),
        AgendaEvent(r3, "created", "system", "Paso a Reservas", at(0)),
        AgendaEvent(r1, "moved", "agent", None, at(5)),
        # El agente canceló: hoy se graba como «customer» (``tools.py:696``).
        AgendaEvent(r1, "cancelled", "customer", None, at(10)),
        # El cliente dijo «no» a la confirmación: el ``replied_no`` va en la misma transacción.
        AgendaEvent(r2, "cancelled", "customer", None, at(20)),
        AgendaEvent(r3, "cancelled", "system", None, at(30)),
    ]
    counts = agenda_counts(events, replied_no={r2: [at(20)]})
    assert counts.created == {"agent": 1, "person": 1, "customer": 0, "total": 2}
    assert counts.moved == {"agent": 1, "person": 0, "customer": 0, "total": 1}
    assert counts.cancelled == {"agent": 1, "person": 0, "customer": 1, "total": 2}
    assert counts.released == 1


# ── D15: el eco lleva la hora de Meta ──────────────────────────────────────


def test_an_echo_stamped_just_before_its_cycle_opened_belongs_to_it() -> None:
    """D15: el eco de la app del negocio guarda la hora de Meta, y la fila (o la
    reapertura) que provoca lleva la de la plataforma, unos segundos después. La
    persona escribió en ese ciclo."""
    conv = uuid.uuid4()
    opened = T0 + timedelta(seconds=4)
    (cycle,) = _cycles(
        conv=conv,
        spans={conv: [Span(opened, None)]},
        contact_times={conv: [at(3)]},
        person_signals={conv: [T0]},
    )
    assert cycle.with_person is True


def test_an_echo_after_a_resolution_counts_for_the_cycle_it_reopened() -> None:
    conv = uuid.uuid4()
    spans = {conv: [Span(T0, at(30)), Span(at(60), None)]}
    cycles = _cycles(
        conv=conv,
        spans=spans,
        contact_times={conv: [at(1), at(62)]},
        person_signals={conv: [at(60) - timedelta(seconds=5)]},
    )
    assert [c.with_person for c in cycles] == [False, True]


def test_a_signal_long_before_a_cycle_is_not_of_it() -> None:
    """Un takeover sobre una conversación resuelta que el contacto reabre días
    después: la reapertura devuelve la conversación al agente."""
    conv = uuid.uuid4()
    spans = {conv: [Span(T0, at(30)), Span(at(60 * 24 * 3), None)]}
    cycles = _cycles(
        conv=conv,
        spans=spans,
        contact_times={conv: [at(1), at(60 * 24 * 3 + 1)]},
        person_signals={conv: [at(45)]},
    )
    assert [c.with_person for c in cycles] == [False, False]


def test_a_signal_just_before_a_cycle_but_inside_the_previous_one_is_the_previous() -> None:
    conv = uuid.uuid4()
    spans = {conv: [Span(T0, at(60)), Span(at(60), None)]}
    cycles = _cycles(
        conv=conv,
        spans=spans,
        contact_times={conv: [at(1), at(61)]},
        person_signals={conv: [at(59)]},
    )
    assert [c.with_person for c in cycles] == [True, False]


# ── el vocabulario de la API ───────────────────────────────────────────────


def test_every_cause_the_report_can_give_is_in_the_api_contract() -> None:
    """Un código que la API no declara sería un 500: lo que da ``escalation_cause``
    (y el freno) cabe entero en el ``Literal`` de la ruta."""
    from typing import get_args

    from nexus_api.api.console.client_report import Cause
    from nexus_api.services.improvement.performance import GATE_CAUSES

    assert set(get_args(Cause)) == GATE_CAUSES | {"escalated", "booking_brake", "other"}
