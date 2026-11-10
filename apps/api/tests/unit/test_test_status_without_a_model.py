"""El estado de una prueba cuando alguna pasada se quedó sin modelo (bug
``el-probador-tapa-los-fallos-del-modelo``)."""

from __future__ import annotations

import pytest

from nexus_api.services.testing.runs import status_of


@pytest.mark.parametrize(
    ("attempts", "unavailable", "expected"),
    [
        # Sin modelo y sin nada en rojo: no se puede decir que pase ni que falle.
        ([None, None, None], 3, "model_failed"),
        ([True, True, None], 1, "model_failed"),
        ([True, None, None], 2, "model_failed"),
        # Una en rojo es del agente, tenga o no modelo la de al lado.
        ([False, None, None], 2, "failed"),
        ([True, False, None], 1, "flaky"),
        # Lo de siempre, sin fallos del modelo.
        ([True, True, True], 0, "passed"),
        ([True, True, False], 0, "flaky"),
        ([False, False, False], 0, "failed"),
        # «No sé» es que el juez no pudo decidir, no que faltara el modelo.
        ([None, None, None], 0, "unknown"),
        ([], 0, "not_run"),
    ],
)
def test_status_of(attempts: list[bool | None], unavailable: int, expected: str) -> None:
    assert status_of(attempts, unavailable=unavailable) == expected
