"""Cuándo se gradúa un turno en el momento (WP-21).

Esta decisión es literalmente dónde se gasta el dinero del grader, así
que lo que se fija aquí es que los turnos que pueden hacer daño NUNCA se
muestrean, y que el ahorro sale de los que no.

El fallo que se previene no da excepción: si el muestreo dejara pasar un
turno que acaba de reservar, la respuesta mala se envía y el veredicto
llega cuando ya da igual.
"""

from __future__ import annotations

from nexus_worker.runtime.grading_policy import decide, turn_writes

READ_ONLY = frozenset({"kg.query", "catalog.search", "availability.list"})


def _decide(**kw):
    base = dict(
        grader_enabled=True,
        grader_mode="sampled",
        sample_rate=0.0,  # nada entra por muestreo salvo que se diga
        intent="info",
        wrote=False,
        turn_key="t-1",
    )
    base.update(kw)
    return decide(**base)


def test_the_master_switch_wins_over_the_mode() -> None:
    """Un agente con el grader apagado no gradúa ni difiere nada — ni
    siquiera en un turno de reserva."""
    d = _decide(grader_enabled=False, grader_mode="sync", intent="book")
    assert d.mode == "off"


def test_sync_mode_grades_everything() -> None:
    assert _decide(grader_mode="sync").is_sync


def test_risky_intents_are_never_sampled_out() -> None:
    """Reservar y escalar tienen efectos fuera del chat: con muestreo al
    0% siguen graduándose."""
    for intent in ("book", "escalate"):
        d = _decide(intent=intent)
        assert d.is_sync, intent
        assert d.reason == f"risky_intent:{intent}"


def test_a_turn_that_wrote_is_never_sampled_out() -> None:
    d = _decide(wrote=True)
    assert d.is_sync
    assert d.reason == "write_tool"


def test_a_low_risk_turn_is_deferred_when_it_misses_the_sample() -> None:
    d = _decide(sample_rate=0.0)
    assert d.is_deferred
    assert d.reason == "sampled_out"


def test_the_sampling_decision_is_stable_for_the_same_turn() -> None:
    """Un reintento del mismo turno no puede cambiar de opinión: si lo
    hiciera, reintentar gastaría LLM que ya se había decidido no gastar,
    y el coste dejaría de ser predecible."""
    first = _decide(sample_rate=0.5, turn_key="turno-abc")
    for _ in range(20):
        assert _decide(sample_rate=0.5, turn_key="turno-abc").mode == first.mode


def test_the_sample_rate_is_roughly_honoured() -> None:
    """Sin esto, un muestreo determinista podría estar sesgado y graduar
    el 0% o el 100% sin que nadie lo notara — solo se vería en la
    factura."""
    sampled = sum(1 for i in range(2000) if _decide(sample_rate=0.10, turn_key=f"k{i}").is_sync)
    assert 150 <= sampled <= 250, f"{sampled}/2000 fuera del 10% esperado"


def test_rate_one_grades_everything_and_rate_zero_grades_nothing() -> None:
    assert _decide(sample_rate=1.0).is_sync
    assert _decide(sample_rate=0.0).is_deferred


# ── clasificación de herramientas ─────────────────────────────────────


def test_a_read_only_turn_does_not_count_as_a_write() -> None:
    calls = [{"tool": "kg.query", "status": "ok"}, {"tool": "catalog.search", "status": "ok"}]
    assert turn_writes(calls, READ_ONLY) is False


def test_an_unknown_tool_counts_as_a_write() -> None:
    """Fail-safe deliberado: una herramienta nueva sin clasificar debe
    salir cara, no invisible. El error contrario —tratar como inocuo un
    turno que acaba de cobrar— es el que no se puede permitir."""
    assert turn_writes([{"tool": "payments.charge", "status": "ok"}], READ_ONLY) is True


def test_a_failed_write_does_not_make_the_turn_risky() -> None:
    """Si la herramienta falló no cambió nada fuera, así que el turno no
    necesita el trato caro por ella."""
    calls = [{"tool": "booking.create", "status": "error"}]
    assert turn_writes(calls, READ_ONLY) is False


def test_an_empty_catalog_makes_every_tool_a_write() -> None:
    """Es lo que pasa si la consulta del catálogo falla. Se gradúa de
    más, que es el lado correcto en el que equivocarse."""
    assert turn_writes([{"tool": "kg.query", "status": "ok"}], frozenset()) is True
