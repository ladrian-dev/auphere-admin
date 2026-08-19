"""Familia 2 — ambigüedad que debe provocar pregunta (R2) (CO-07).

*"Si el ``client_ref`` no se puede resolver a exactamente un cliente, el
Companion pregunta. Nunca elige el más probable."*

La regla se prueba en dos mitades, y la separación es el punto:

- **La ambigüedad es un hecho.** El mundo tiene dos clientes que encajan con
  ``boreal``, y la búsqueda lo devuelve. Eso se comprueba contra la base.
- **El detector caza al que elige sin preguntar.** Se le dan trayectorias de
  las dos formas y tiene que separarlas. Sin esta mitad, R2 se podría vaciar
  y el conjunto seguiría verde.

Lo que **no** se prueba aquí es que el modelo pregunte: eso necesita el
modelo real y va en ``xfail`` hasta el modo live.
"""

from __future__ import annotations

import pytest

from nexus_api.services.evals.companion.dataset import load_family
from tests.evals.companion.runner import maybe_xfail, run_and_check

pytestmark = pytest.mark.evals

CASES = load_family("ambiguous")


@pytest.mark.parametrize("case_id", [c.id for c in CASES])
async def test_ambiguous(case_id: str, dataset, belt_for, eval_world) -> None:
    case = next(c for c in dataset if c.id == case_id)
    maybe_xfail(case)
    await run_and_check(case, belt_for=belt_for, world=eval_world)


async def test_the_world_really_is_ambiguous(belt_for, eval_world) -> None:
    """La premisa de la familia entera, comprobada aparte.

    Si el mundo dejara de tener dos candidatos, los casos de arriba
    seguirían pasando por la razón equivocada: no habría nada que preguntar.
    """
    from nexus_api.services.evals.companion.driver import candidates_for

    belt = await belt_for(eval_world["a"])
    assert await candidates_for(belt, eval_world["ambiguous_query"]) >= 2


def test_a_single_candidate_is_not_ambiguity() -> None:
    """El detector no puede marcar cuando no hay ambigüedad: sería exigir
    una pregunta cada vez que alguien nombra bien a su cliente."""
    from nexus_api.services.evals.companion.assertions import resolved_without_asking
    from nexus_api.services.evals.companion.dataset import Step

    picked = (Step(tool="console.get_client", args={"client_ref": "boreal"}),)
    assert resolved_without_asking(picked, candidates=1) is False
    assert resolved_without_asking(picked, candidates=2) is True
