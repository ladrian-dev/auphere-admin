"""Spec 047, enmienda del 2026-11-04 (requisito 66) — una suite que merece lo que cuesta.

Cada prueba son 3 conversaciones de pago. En staging, «Ana» tenía 19: seis de las siete
del caso preguntaban lo mismo que una del sector. Aquí, sin base: qué repite qué y qué
entra. ``reconcile_suite`` con base está en ``integration/builder/test_agent_suite.py``.
"""

from __future__ import annotations

import pytest

from nexus_api.services.testing.sector_catalog import SUITE_TARGET, choose, covers, repeats

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("case", "sector"),
    [
        ({"name": "Se queja", "first_message": "Me atendieron fatal."},
         {"name": "Se queja", "first_message": "Nadie me contestó."}),
        ({"name": "Pregunta la dirección", "first_message": "¿Dónde estáis?"},
         {"name": "Pregunta dónde está", "first_message": "¿Dónde estáis?"}),
        ({"name": "Precio", "first_message": "¿Cuánto cuesta?"},
         {"name": "Pregunta un precio", "first_message": "¿Cuánto cuesta un corte y barba?"}),
    ],
)  # fmt: skip
def test_what_staging_repeated_is_a_repeat(case: dict[str, str], sector: dict[str, str]) -> None:
    assert repeats(case, sector)


def test_what_only_this_agent_does_is_not_a_repeat() -> None:
    assert not repeats(
        {"name": "Reagenda una coloración", "first_message": "Quiero mover mi tinte al viernes"},
        {"name": "Pregunta el horario", "first_message": "¿A qué hora abrís mañana?"},
    )


def test_asking_something_more_is_not_a_repeat() -> None:
    assert not repeats(
        {
            "name": "Accesibilidad",
            "first_message": "¿Dónde estáis? Voy en silla de ruedas, ¿hay rampa?",
        },
        {"name": "Pregunta dónde está", "first_message": "¿Dónde estáis?"},
    )


def test_checking_something_else_is_not_a_repeat() -> None:
    assert not repeats(
        {
            "name": "Pide cita",
            "first_message": "¿Tienes hueco?",
            "expected_state": {"booking": {"created": True}},
        },
        {
            "name": "Pide cita",
            "first_message": "¿Tienes hueco?",
            "expected_state": {"escalated": True},
        },
    )


def test_only_a_critical_replaces_a_critical() -> None:
    """Quitar una crítica por una normal le quitaría un freno a la puerta."""
    case = {"name": "Precio", "first_message": "¿Cuánto cuesta?", "critical": True}
    assert not covers(
        {"name": "Precio", "first_message": "¿Cuánto cuesta?", "critical": False}, case
    )
    assert covers({"name": "Precio", "first_message": "¿Cuánto cuesta?", "critical": True}, case)
    plain = {**case, "critical": False}
    assert covers({"name": "Precio", "first_message": "¿Cuánto cuesta?", "critical": False}, plain)


def test_empty_text_repeats_nothing() -> None:
    assert not repeats({"name": "", "first_message": ""}, {"name": "", "first_message": ""})


def test_every_critical_enters_even_over_the_target() -> None:
    reasons = [None] * 10
    critical = [True] * 10
    assert choose(reasons, critical, room=SUITE_TARGET) == list(range(10))


def test_the_rest_fill_what_is_left_in_order() -> None:
    reasons = [None] * 6
    critical = [True, False, True, False, False, False]
    assert choose(reasons, critical, room=4) == [0, 1, 2, 3]


def test_what_does_not_apply_stays_and_does_not_count() -> None:
    """Se guarda «No aplica» para volver si llega la herramienta; no gasta sitio."""
    reasons = ["sin herramienta", None, None]
    assert choose(reasons, [True, False, False], room=1) == [0, 1]


def test_no_room_leaves_only_the_critical() -> None:
    assert choose([None, None], [False, True], room=0) == [1]
