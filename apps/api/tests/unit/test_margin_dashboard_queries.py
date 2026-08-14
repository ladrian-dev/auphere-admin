"""El panel de margen no puede cobrarle al cliente las pruebas del operador.

El panel vive en un JSON con SQL dentro (``infra/grafana/dashboards/
nexus-margin.json``), así que ningún test de código lo toca y ningún
compilador lo revisa: la única forma de que una regresión ahí se vea es
esta. Sin el filtro por ``source`` (0079), un operador probando un agente
sube el coste del cliente en la tabla que se usa para decidir precio y
margen — y sube más el del cliente mejor atendido, que es el que más
pruebas recibe.

Se comprueba lo mínimo que no se puede afirmar leyendo el JSON de un
vistazo: que **toda** consulta que agrega dinero o cantidades declara de
qué origen habla. Un panel nuevo que olvide el filtro rompe este test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[4] / "infra/grafana/dashboards/nexus-margin.json"

# Columnas de la vista que mezclan orígenes al agregarse. Si una consulta
# toca alguna, tiene que decir de qué ``source`` habla.
_AGGREGATING = ("cost_usd_total", "billable_qty_total", "unpriced_records", "records")


def _postgres_sql() -> list[tuple[str, str]]:
    dash = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for panel in dash["panels"]:
        if panel.get("datasource", {}).get("uid") != "nexus-postgres":
            continue
        for target in panel.get("targets", []):
            sql = target.get("rawSql")
            if sql:
                out.append((panel["title"], sql))
    return out


def test_the_dashboard_is_still_valid_json_with_postgres_panels() -> None:
    """Guardián del guardián: si el fichero deja de parsearse o los
    paneles cambian de datasource, los asserts de abajo pasarían sobre una
    lista vacía y este archivo daría verde sin comprobar nada."""
    assert DASHBOARD.exists(), DASHBOARD
    panels = _postgres_sql()
    assert len(panels) >= 4


@pytest.mark.parametrize("title,sql", _postgres_sql())
def test_every_aggregating_query_declares_its_source(title: str, sql: str) -> None:
    if not any(col in sql for col in _AGGREGATING):
        pytest.skip(f"{title}: no agrega consumo")
    assert "source = " in sql, (
        f"El panel «{title}» suma consumo sin filtrar por source: "
        "está mezclando el gasto del QA Playground con el coste del cliente."
    )


def test_the_client_cost_table_counts_only_channel_traffic() -> None:
    """El panel concreto que alimenta la conversación de precio."""
    sql = dict(_postgres_sql())["Coste por tenant y versión de agente"]
    assert "source = 'channel'" in sql


def test_the_qa_spend_is_shown_and_not_merely_excluded() -> None:
    """Ocultarlo habría sido la solución fácil y equivocada: el problema
    de partida era que ese gasto no aparecía en ninguna parte."""
    titles_and_sql = _postgres_sql()
    assert any("source = 'qa'" in sql for _title, sql in titles_and_sql), (
        "El gasto interno tiene que tener su propio panel: medirlo y "
        "esconderlo deja el mismo agujero con otro nombre."
    )
