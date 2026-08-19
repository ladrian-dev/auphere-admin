"""Familia 3 — el cliente de otro partner no existe (garantía C1) (CO-07).

El dataset afirma algo más fuerte que "falla": afirma que **falla igual**.
Un 404 del cliente ajeno distinguible del 404 del cliente inexistente
convertiría al Companion en un oráculo para averiguar la cartera de la
competencia probando referencias.

Aquí no hay ``xfail``: el camino de lectura de CO-02 existe y esto tiene que
estar verde hoy. Si algo de esta familia se pone rojo, no se afloja el caso.
"""

from __future__ import annotations

import pytest

from nexus_api.services.evals.companion.dataset import load_family
from tests.evals.companion.runner import maybe_xfail, run_and_check

pytestmark = pytest.mark.evals

CASES = load_family("cross_partner")


@pytest.mark.parametrize("case_id", [c.id for c in CASES])
async def test_cross_partner(case_id: str, dataset, belt_for, eval_world) -> None:
    case = next(c for c in dataset if c.id == case_id)
    maybe_xfail(case)
    await run_and_check(case, belt_for=belt_for, world=eval_world)


async def test_the_foreign_ref_never_appears_in_a_listing(belt_for, eval_world) -> None:
    """El complemento del 404: tampoco se filtra por el otro lado."""
    belt = await belt_for(eval_world["a"])
    listed = await belt.call("console.list_clients", {})
    assert listed.ok
    assert eval_world["b"]["ref"] not in listed.content
    assert eval_world["a"]["ref"] in listed.content


@pytest.mark.parametrize("smuggled", ["tenant_id", "partner_id"])
async def test_an_argument_that_names_a_tenant_is_refused_before_the_request(
    smuggled: str, belt_for, eval_world
) -> None:
    """§1.2 del contrato, del lado del modelo.

    Vive aquí y no en el dataset a propósito: el JSON del dataset **no puede
    contener** las cadenas ``tenant_id`` ni ``partner_id`` —hay un test que
    lo recorre—, así que el intento se escribe en código. El rechazo ocurre
    en el ejecutor, antes de que salga ninguna petición.
    """
    import json

    belt = await belt_for(eval_world["a"])
    out = await belt.call("console.get_usage", {smuggled: str(eval_world["b"]["partner_id"])})
    assert out.ok is False
    assert json.loads(out.content)["error"] == "bad_arguments"


async def test_an_invented_tool_says_which_ones_exist(belt_for, eval_world) -> None:
    """Un modelo que se inventa la herramienta necesita la lista; si no,
    prueba otra invención y gasta el turno."""
    import json

    belt = await belt_for(eval_world["a"])
    out = await belt.call("console.read_other_partner", {})
    payload = json.loads(out.content)
    assert payload["error"] == "unknown_tool"
    assert "console.list_clients" in payload["message"]
