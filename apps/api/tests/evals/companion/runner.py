"""Lo que comparten los cuatro tests de familia (CO-07).

Un caso se corre por el grafo real con el juego de herramientas real, y sus
``expect`` se aplican al resultado. Lo único de mentira es el modelo.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from nexus_api.services.evals.companion.assertions import check_case
from nexus_api.services.evals.companion.dataset import CompanionCase
from nexus_api.services.evals.companion.driver import candidates_for, run_case

#: El modo live se enciende a mano. Nunca en CI: una barrera que depende de
#: un proveedor externo no es una barrera, es una fuente de rojos.
LIVE = os.getenv("NEXUS_COMPANION_EVAL_LIVE") == "1"


def belt_kwargs(case: CompanionCase) -> dict[str, Any]:
    """Lo que el caso cambia del juego de herramientas de producción.

    Son dos cosas y las dos son de control: el tope duro de llamadas y el
    modo del hilo. Todo lo demás lo pone el ejecutor real.
    """
    kwargs: dict[str, Any] = {}
    if case.max_calls is not None:
        kwargs["max_calls"] = case.max_calls
    if case.mode is not None:
        kwargs["mode"] = case.mode
    return kwargs


def maybe_xfail(case: CompanionCase) -> None:
    """Marca el caso que todavía no puede pasar, con su motivo literal."""
    if case.requires == "co-04":
        pytest.xfail(case.xfail_reason or "camino de escritura — CO-04")
    if case.requires == "live" and not LIVE:
        pytest.xfail(case.xfail_reason or "necesita el modelo real — modo live")


async def missing_body_for(belt: Any, case: CompanionCase) -> str | None:
    """El cuerpo del error de una referencia que no existe, con la MISMA
    herramienta. Es el patrón de comparación de la opacidad: sin él, la
    afirmación "es el mismo 404" no se puede hacer."""
    if not case.expect.opaque_as_missing:
        return None
    tool = next((s.tool for s in case.trajectory if s.is_tool), None)
    if tool is None:  # pragma: no cover - caso mal escrito
        return None
    outcome = await belt.call(tool, {"client_ref": "no-existe-jamas-2f1a"})
    return str(outcome.content)


async def run_and_check(
    case: CompanionCase,
    *,
    belt_for: Any,
    world: dict[str, Any],
    candidates: int | None = None,
) -> None:
    """Corre el caso y afirma cada resultado por separado.

    Cada aserción se comprueba una a una y con su detalle en el mensaje: un
    ``assert all(...)`` diría "falló el caso" y no cuál de las cinco cosas
    falló, que es justo lo que se necesita saber cuando CI se pone rojo.
    """
    side = world[case.principal]
    belt = await belt_for(side, **belt_kwargs(case))

    result = await run_case(case, belt=belt)

    if candidates is None and case.expect.min_candidates is not None:
        # Juego aparte: el ejecutor rechaza repetir una consulta dentro del
        # mismo turno, y varios casos ya listaron con esa misma búsqueda.
        # Contar los candidatos es del test, no del turno.
        candidates = await candidates_for(await belt_for(side), world["ambiguous_query"])

    # La referencia de opacidad se lee con un juego aparte: el ejecutor
    # rechaza repetir la misma consulta dentro de un turno, y esta consulta
    # no es del turno, es del test.
    missing = None
    if case.expect.opaque_as_missing:
        probe = await belt_for(side)
        missing = await missing_body_for(probe, case)

    results = check_case(
        case,
        reads_ok=result.reads_ok,
        last_body=result.last_body,
        last_error_code=result.last_error_code,
        missing_body=missing,
        candidates=candidates,
    )
    assert results, f"{case.id}: el caso no produjo ninguna comprobación"
    for outcome in results:
        assert outcome.passed, f"{case.id} · {outcome.kind}: {outcome.detail}"


def ids(cases: list[CompanionCase]) -> list[str]:
    return [c.id for c in cases]
