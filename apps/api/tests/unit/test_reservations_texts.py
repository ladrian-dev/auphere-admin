"""Spec 043 — los textos de los avisos al cliente final se leen bien.

El texto libre (dentro de la ventana de 24 h) y la plantilla que aprueba Meta
dicen lo mismo. «de {{cuando}}» con «el jueves…» da «de el jueves»: el texto
libre lo arreglaba al vuelo, pero una plantilla aprobada no se arregla, así que
la de partida no lo lleva.
"""

from __future__ import annotations

import pytest

from nexus_api.services.reservations.automation import TEMPLATES, TEXTS, render_text

VARS = {
    "nombre": "Ana",
    "negocio": "La Fonda",
    "cuando": "el jueves 23 a las 20:30",
    "detalle": "4 comensales",
    "minutos": "15",
}


@pytest.mark.parametrize("kind", sorted(k for k, t in TEMPLATES.items() if t))
def test_no_template_says_de_el(kind: str) -> None:
    """Lo que sale como plantilla aprobada no pasa por ningún arreglo."""
    assert " de el " not in TEXTS[kind].format(**VARS)


@pytest.mark.parametrize("kind", sorted(TEXTS))
def test_no_free_text_says_de_el(kind: str) -> None:
    assert " de el " not in render_text(kind, VARS)


def test_the_cancellation_says_for_when() -> None:
    assert render_text("cancelled", VARS) == (
        "Hola, Ana. Tu reserva en La Fonda para el jueves 23 a las 20:30 quedó cancelada. "
        "Si quieres otra hora, escríbenos por aquí."
    )
