"""Familia 1 — consultas con respuesta conocida (CO-07).

El Companion lee con herramienta y afirma un dato que se puede verificar.
Lo que se comprueba aquí es que **el dato sale de la base**: la lectura va al
router ``/console/*`` real con el principal real, y el caso declara qué tiene
que traer el cuerpo. Si un endpoint deja de devolver ``totals_by_meter``, el
caso se pone rojo aunque el modelo siga sonando convincente.

Los seis casos espejo (afirmar sin haber leído) comprueban lo contrario: que
R1 los marca. Sin ellos el umbral se cumpliría vaciando el detector.
"""

from __future__ import annotations

import pytest

from nexus_api.services.evals.companion.dataset import load_family
from tests.evals.companion.runner import maybe_xfail, run_and_check

pytestmark = pytest.mark.evals

CASES = load_family("known_answer")


@pytest.mark.parametrize("case_id", [c.id for c in CASES])
async def test_known_answer(case_id: str, dataset, belt_for, eval_world) -> None:
    case = next(c for c in dataset if c.id == case_id)
    maybe_xfail(case)
    await run_and_check(case, belt_for=belt_for, world=eval_world)
