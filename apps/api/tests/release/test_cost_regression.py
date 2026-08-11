"""El coste por turno es una propiedad testeada, no una sorpresa mensual (WP-22).

Antes de la Fase 2, que un cambio de prompt duplicara el coste solo se
descubría al recibir la factura del proveedor — semanas después, mezclado
con el crecimiento de tráfico y sin forma de atribuirlo a un cambio
concreto. Con ``usage_records.cost_usd`` (WP-18 + WP-19) el dato existe;
esto lo convierte en un umbral que rompe el build.

Cómo funciona:

- La referencia está versionada en ``cost_baseline.json``. Subirla es un
  commit deliberado que explica por qué — que es exactamente lo que se
  quiere que ocurra cuando la subida está justificada.
- La medida se toma de la base de datos del entorno, agregando el coste
  real por turno. No se estima ni se extrapola: son los dólares que se
  gastaron.
- Se salta si no hay entorno configurado, como el resto de la suite de
  release. Un test de coste que se ejecuta contra una base vacía diría
  "0 dólares por turno" y pasaría siempre.

    NEXUS_COST_REGRESSION_DSN=postgresql://... \\
    uv run pytest apps/api/tests/release/test_cost_regression.py -v
"""

from __future__ import annotations

import json
import os
import pathlib
from decimal import Decimal

import pytest

BASELINE_PATH = pathlib.Path(__file__).parent / "cost_baseline.json"

# Turnos mínimos para que la media signifique algo. Con menos, un solo
# turno raro mueve la media lo suficiente para dar un falso positivo (o,
# peor, ocultar uno real).
MIN_TURNS = 30

# El coste por turno se calcula agregando primero POR TURNO y promediando
# después. Promediar filas directamente pesaría más los turnos con más
# llamadas, que es justo el sesgo que interesa detectar.
_QUERY = """
    WITH per_turn AS (
        SELECT conversation_id,
               date_trunc('second', occurred_at) AS turn_at,
               sum(cost_usd) AS turn_cost
          FROM usage_records
         WHERE cost_usd IS NOT NULL
           AND meter LIKE 'llm.%'
           AND occurred_at > now() - interval '30 days'
         GROUP BY 1, 2
    )
    SELECT count(*), avg(turn_cost) FROM per_turn
"""


def _baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text())


@pytest.fixture(scope="session")
def dsn() -> str:
    value = os.environ.get("NEXUS_COST_REGRESSION_DSN")
    if not value:
        pytest.skip("set NEXUS_COST_REGRESSION_DSN to run the cost regression test")
    return value


def test_the_baseline_file_is_usable() -> None:
    """Corre siempre, también en CI sin entorno.

    Un fichero de referencia mal escrito haría que el test de verdad se
    saltara o pasara por accidente, y nadie lo notaría hasta que llegase
    una factura rara.
    """
    baseline = _baseline()
    assert Decimal(str(baseline["usd_per_turn"])) > 0
    assert 0 < baseline["tolerance_pct"] <= 100
    assert baseline["measured_at"] and baseline["environment"]


@pytest.mark.asyncio
async def test_cost_per_turn_has_not_regressed(dsn: str) -> None:
    import asyncpg

    baseline = _baseline()
    reference = Decimal(str(baseline["usd_per_turn"]))
    tolerance = Decimal(str(baseline["tolerance_pct"])) / 100

    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(_QUERY)
    finally:
        await conn.close()

    turns = int(row[0] or 0)
    if turns < MIN_TURNS:
        pytest.skip(f"solo {turns} turnos valorados; hacen falta {MIN_TURNS} para una media útil")

    measured = Decimal(str(row[1]))
    ceiling = reference * (1 + tolerance)

    assert measured <= ceiling, (
        f"el coste por turno subió a ${measured:.6f} desde ${reference:.6f} "
        f"(+{((measured / reference) - 1) * 100:.1f}%, tope +{baseline['tolerance_pct']}%). "
        "Si la subida está justificada, actualiza cost_baseline.json en un commit "
        "que explique por qué."
    )

    # Una BAJADA grande tampoco se ignora: suele significar que se dejó de
    # medir algo (un modelo salió del catálogo y sus filas entran sin
    # precio), no que se haya optimizado nada.
    assert measured >= reference * Decimal("0.4"), (
        f"el coste por turno cayó a ${measured:.6f} desde ${reference:.6f}. "
        "Antes de celebrarlo, comprueba que no hay filas con cost_usd NULL "
        "por un modelo fuera del catálogo."
    )
