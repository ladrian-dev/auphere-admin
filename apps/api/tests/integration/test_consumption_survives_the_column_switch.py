"""Spec 007/008 · el consumo que ve el partner sobrevive al cambio de columna.

**Este fichero existe por un defecto que estuvo a punto de llegar a producción.**
La spec 007 dejó de escribir `companion.runs.input_tokens` y pasó a
`uncached_input_tokens`. Dos consultas —la atribución del Companion y el consumo
por teammate— seguían sumando sólo la columna vieja, así que habrían mostrado
**cero de entrada para todo el consumo posterior al despliegue**.

Es la peor forma de romper un panel: no da error, da un número más bajo. Y un
panel que baja se lee como «hubo menos trabajo», no como «esto está roto».

Lo que estos casos fijan es que las consultas leen **las dos** columnas, para que
una serie que cruce el despliegue no tenga un escalón artificial.
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = [pytest.mark.integration]

_API = pathlib.Path(__file__).resolve().parents[2] / "src" / "nexus_api"

#: (fichero, qué alimenta) de cada consulta que suma tokens de un run.
_QUERIES = (
    ("api/console/companion.py", "la atribución del Companion por partner"),
    ("api/console/teammates.py", "el consumo por teammate que se ve en la consola"),
)


@pytest.mark.parametrize(("relative", "what"), _QUERIES)
def test_the_query_reads_both_columns(relative: str, what: str) -> None:
    """Sumar sólo `input_tokens` deja el panel a cero desde el despliegue."""
    source = (_API / relative).read_text(encoding="utf-8")
    sums = [
        block
        for block in re.findall(r"sa\.func\.sum\((?:[^()]|\([^()]*\))*\)", source, re.S)
        if "input_tokens" in block
    ]
    assert sums, f"{relative}: no se encontró ninguna suma de tokens ({what})"

    for block in sums:
        assert "uncached_input_tokens" in block, (
            f"{relative} suma `input_tokens` sin `uncached_input_tokens`. "
            f"Alimenta {what}, y desde la spec 007 los runs nuevos dejan la "
            f"columna vieja a NULL: este panel se iría a cero sin dar un error."
        )


def test_the_write_path_only_fills_the_new_column() -> None:
    """La otra mitad: si alguien volviera a escribir la columna vieja, la mezcla
    de magnitudes dejaría de ser sólo histórica y pasaría a ser permanente."""
    source = (_API / "api/console/companion.py").read_text(encoding="utf-8")
    assert "run.uncached_input_tokens = input_tokens" in source
    assert "run.input_tokens = input_tokens" not in source, (
        "`companion.runs.input_tokens` está deprecada y no debe volver a "
        "escribirse: guardaba la cuota ponderada con un factor que ya no existe."
    )
