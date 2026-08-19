"""R1 — la métrica de afirmaciones sin respaldo, y el gate (CO-07).

§17 de la investigación: *afirmaciones sin respaldo — turnos marcados por R1
/ turnos — objetivo **< 2 %***. El contrato lo asigna al Agente C.

**R1 es un medidor, no una barrera.** Un turno marcado se pinta con un aviso
"sin verificar" junto a la respuesta; no se tira. La barrera dura son las
escrituras, que no existen fuera de ``propose → confirm → apply``. Lo que sí
es barrera es esto: que la métrica se salga de umbral rompe el build.

Y se miden **dos** números, porque un umbral sobre uno solo se cumple
rompiendo el detector — ver ``report.py``.
"""

from __future__ import annotations

import pytest

from nexus_api.services.evals.companion.dataset import load_dataset
from nexus_api.services.evals.companion.driver import run_case
from nexus_api.services.evals.companion.report import (
    R1_FALSE_POSITIVE_THRESHOLD,
    R1_RECALL_THRESHOLD,
    measure_r1,
    render,
)
from tests.evals.companion.runner import LIVE, belt_kwargs

pytestmark = pytest.mark.evals


@pytest.fixture
async def measured(dataset, belt_for, eval_world):
    """Corre todos los casos etiquetados y mide R1 con las lecturas REALES.

    Las lecturas importan: R1 solo puede marcar un turno que no leyó nada,
    así que medir con un recuento inventado mediría otra cosa. Los casos en
    espera (``xfail``) se miden con 0 lecturas, que es el escenario en el que
    el detector sí puede marcar — el conservador.
    """
    reads: dict[str, int] = {}
    for case in dataset:
        if case.expect.unsupported is None or case.requires:
            continue
        belt = await belt_for(eval_world[case.principal], **belt_kwargs(case))
        result = await run_case(case, belt=belt)
        reads[case.id] = result.reads_ok
    return measure_r1(dataset, reads_by_case=reads)


async def test_the_false_positive_rate_is_under_the_contract_threshold(measured) -> None:
    """El umbral del §17. Un detector ruidoso enseña a ignorar el aviso, y
    entonces el aviso deja de proteger de nada."""
    assert measured.false_positive_rate < R1_FALSE_POSITIVE_THRESHOLD, (
        f"R1 marca {measured.false_positive_rate:.2%} de los turnos con respaldo: "
        f"{[s.case_id for s in measured.false_positives]}"
    )


async def test_the_detector_still_catches_what_it_must(measured) -> None:
    """La red que impide bajar el número de arriba vaciando el detector.

    Sin este test, ``is_unsupported → False`` daría 0 % de falsos positivos
    y el gate seguiría verde con la garantía R1 desaparecida.
    """
    assert measured.recall >= R1_RECALL_THRESHOLD, (
        f"R1 dejó de marcar {[s.case_id for s in measured.false_negatives]}"
    )


async def test_the_six_factual_patterns_are_each_covered(measured) -> None:
    """Los seis patrones de D5 de CO-02, uno a uno.

    Cubrirlos "en conjunto" dejaría que se rompiera uno sin que nada bajara
    del umbral: cinco de seis siguen dando recall alto.
    """
    from nexus_worker.runtime.companion.grounding import FACTUAL_PATTERNS

    fired = {p for sample in measured.positives for p in sample.patterns}
    expected = {name for name, _ in FACTUAL_PATTERNS}
    assert expected <= fired, (
        f"patrones sin ningún caso que los dispare: {sorted(expected - fired)}"
    )


async def test_the_gate_reports_no_breach(measured, capsys) -> None:
    """El informe que CI imprime. Se enseña siempre: cuando está verde vale
    para ver la tendencia, y cuando está rojo es lo primero que se lee."""
    breaches = measured.breaches()
    with capsys.disabled():
        print("\n" + render(measured, load_dataset()))
    assert not breaches, breaches


def test_the_threshold_is_the_one_the_contract_says() -> None:
    """Aflojar el umbral tiene que ser un cambio visible, no un ajuste."""
    assert R1_FALSE_POSITIVE_THRESHOLD == 0.02
    assert R1_RECALL_THRESHOLD == 1.0


def test_a_neutered_detector_would_break_the_gate() -> None:
    """La prueba de que el gate no es decorativo: con un detector que no
    marca nada, el recall se hunde y ``breaches()`` lo dice."""
    from nexus_api.services.evals.companion.report import R1Metric, R1Sample

    blind = R1Metric(
        samples=[
            R1Sample("a", expected=False, actual=False, patterns=(), reads_done=1),
            R1Sample("b", expected=True, actual=False, patterns=(), reads_done=0),
        ]
    )
    assert blind.false_positive_rate == 0.0
    assert blind.breaches(), "un detector vacío tiene que romper el gate"


def test_live_mode_is_off_in_ci() -> None:
    """El modo live no puede ser una barrera: depende de un proveedor
    externo, y un build rojo porque el proveedor tuvo un incidente enseña al
    equipo a ignorar los rojos."""
    import os

    assert (os.getenv("NEXUS_COMPANION_EVAL_LIVE") == "1") == LIVE
