"""El dataset está bien formado y dice la verdad sobre sí mismo (CO-07).

Un dataset de evals que se degrada en silencio es peor que ninguno: sigue
saliendo verde mientras deja de cubrir. Estos tests son los que impiden que
alguien borre media familia o afloje un caso sin que se note.

No tocan base de datos: cargan el JSON y lo miran.
"""

from __future__ import annotations

import json

import pytest

from nexus_api.services.evals.companion.dataset import (
    DATASET_DIR,
    FAMILIES,
    FAMILY_FILES,
    FORBIDDEN_KEYS,
    DatasetError,
    load_dataset,
    load_family,
)

pytestmark = pytest.mark.evals

#: Lo que el paquete se comprometió a cubrir. Bajar un número aquí es una
#: decisión que se toma a la vista, no un descuido.
MINIMUM_PER_FAMILY: dict[str, int] = {
    "known_answer": 26,
    "ambiguous": 14,
    "cross_partner": 12,
    "destructive": 17,
}

MINIMUM_TOTAL = 69


def test_the_dataset_has_the_promised_size() -> None:
    cases = load_dataset()
    assert len(cases) >= MINIMUM_TOTAL, f"el dataset encogió a {len(cases)} casos"


@pytest.mark.parametrize("family", FAMILIES)
def test_every_family_keeps_its_floor(family: str) -> None:
    cases = load_family(family)  # type: ignore[arg-type]
    assert len(cases) >= MINIMUM_PER_FAMILY[family], (
        f"{family} bajó a {len(cases)} casos (mínimo {MINIMUM_PER_FAMILY[family]})"
    )


def test_no_case_can_name_a_tenant_or_a_partner() -> None:
    """§1.2 del contrato, aplicado al propio dataset.

    No es decorativo: si un caso pudiera pasar ``tenant_id``, el caso
    estaría probando una superficie que no debe existir, y la comprobación
    de aislamiento se habría escrito alrededor del agujero.
    """
    for family in FAMILIES:
        raw = json.loads((DATASET_DIR / FAMILY_FILES[family]).read_text(encoding="utf-8"))
        flat = json.dumps(raw).lower()
        for forbidden in FORBIDDEN_KEYS:
            assert f'"{forbidden}"' not in flat, f"{family} nombra {forbidden}"


def test_every_pending_case_says_what_it_waits_for() -> None:
    """Un ``xfail`` sin motivo legible es deuda invisible."""
    for case in load_dataset():
        if case.requires:
            assert case.xfail_reason, case.id
            assert len(case.xfail_reason) > 40, (
                f"{case.id}: el motivo tiene que explicar, no etiquetar"
            )
            assert case.requires in {"co-04", "live"}, case.requires


def test_the_trajectories_fit_in_a_turn() -> None:
    """El bucle del grafo corta a ``MAX_MODEL_STEPS`` pasos. Una trayectoria
    más larga no se corre entera y el caso mentiría."""
    from nexus_worker.runtime.companion.graph import MAX_MODEL_STEPS

    for case in load_dataset():
        assert len(case.trajectory) <= MAX_MODEL_STEPS, case.id


def test_every_tool_named_in_a_runnable_case_exists() -> None:
    """Un caso que llama a una herramienta inexistente prueba el mensaje de
    "no existe", no lo que dice probar. Los casos en espera de CO-04 sí
    nombran herramientas futuras, y por eso se excluyen."""
    from nexus_api.services.evals.companion.assertions import tool_exists

    for case in load_dataset():
        if case.requires:
            continue
        for name in case.tool_names:
            assert tool_exists(name), f"{case.id}: {name} no está en el catálogo"


def test_every_tool_of_the_catalogue_is_exercised() -> None:
    """El dataset cubre el catálogo entero. Añadir una herramienta sin
    añadir su caso deja un hueco que nadie ve.

    Se llamaba ``..._read_tool_...`` cuando el catálogo eran dieciocho
    lecturas. Desde CO-04 son veintiocho —nueve ``propose_*`` y la puerta
    única de escritura— y el nombre viejo describía media garantía. Lo que
    NO cambia es el conjunto que recorre: ``TOOLS_BY_NAME``, el catálogo
    entero. Estrecharlo a ``READ_TOOLS`` habría dejado sin vigilar justo la
    mitad que escribe.
    """
    from nexus_api.companion.tools.catalog import TOOLS_BY_NAME

    exercised = {name for case in load_dataset() for name in case.tool_names}
    missing = sorted(set(TOOLS_BY_NAME) - exercised)
    assert not missing, f"herramientas sin ningún caso: {missing}"


def test_every_action_kind_is_exercised() -> None:
    """Y su gemelo por el otro lado: los nueve ``kind`` del §3.1.

    Una herramienta ``propose`` no se puede construir sin ``kind``, así que
    cubrir las herramientas cubre los ``kind`` — hoy. Este test fija que
    siga siendo verdad si mañana alguien añade un ``kind`` por otra vía.
    """
    from nexus_api.companion.tools.catalog import ACTION_KINDS, TOOLS_BY_NAME

    exercised = {name for case in load_dataset() for name in case.tool_names}
    covered = {
        TOOLS_BY_NAME[name].kind for name in exercised if TOOLS_BY_NAME.get(name) is not None
    }
    missing = sorted(set(ACTION_KINDS) - covered)
    assert not missing, f"kind sin ningún caso: {missing}"


def test_a_case_without_expectations_is_refused() -> None:
    from nexus_api.services.evals.companion.dataset import _case

    with pytest.raises(DatasetError, match="no comprueba nada"):
        _case(
            {
                "id": "x",
                "family": "known_answer",
                "trajectory": [{"text": "hola"}],
                "expect": {},
            },
            family="known_answer",
            where="test",
        )


def test_a_step_that_is_both_tool_and_text_is_refused() -> None:
    from nexus_api.services.evals.companion.dataset import _case

    with pytest.raises(DatasetError, match="herramienta O un texto"):
        _case(
            {
                "id": "x",
                "family": "known_answer",
                "trajectory": [{"tool": "console.whoami", "text": "hola"}],
                "expect": {"reads_ok": 1},
            },
            family="known_answer",
            where="test",
        )


def test_a_forbidden_capability_outside_the_closed_list_is_refused() -> None:
    from nexus_api.services.evals.companion.dataset import _case

    with pytest.raises(DatasetError, match="lista cerrada"):
        _case(
            {
                "id": "x",
                "family": "destructive",
                "trajectory": [{"text": "no"}],
                "expect": {"forbidden_capability": "reiniciar_el_universo"},
            },
            family="destructive",
            where="test",
        )
