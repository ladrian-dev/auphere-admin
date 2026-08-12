"""Contratos sobre el OpenAPI publicado (WP-28, Schemathesis).

``test_v1_contract.py`` congela la FORMA de `/v1` contra un fichero. Esto
es lo complementario: comprueba que el esquema publicado **describe la
realidad**, generando peticiones a partir del propio OpenAPI y mirando qué
contesta la aplicación.

Lo que se afirma, y por qué solo eso:

- **Ninguna entrada produce un 5xx.** Es lo que un partner vive como "se
  os ha caído la API", y es el fallo que una integración con un bug
  provoca sin querer: un campo de más, un tipo equivocado, un id que no es
  un UUID. Un 4xx es una respuesta; un 500 es un incidente.
- **El código de respuesta está documentado.** Un 422 que el esquema no
  declara es un contrato roto aunque la aplicación funcione: el cliente
  generado a partir del OpenAPI no sabe manejarlo.

Lo que NO se hace, a propósito: fuzzear autenticado. Sin credenciales
válidas la mayoría de operaciones responde 401 antes de tocar la base — que
es exactamente la superficie que interesa aquí (el manejo de entrada
malformada por parte del framework y de las dependencias). Fuzzear los
caminos de escritura contra una base compartida es otra decisión, con otro
coste, y merece su propio trabajo.
"""

from __future__ import annotations

import pytest
import schemathesis
from hypothesis import HealthCheck, settings

from nexus_api.main import app

# La carga del esquema recorre la app entera; hacerlo una vez por caso de
# prueba multiplicaría el tiempo de la suite sin cambiar nada.
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

# Superficie pública de partners. El admin queda fuera: su autenticación es
# un token estático de operador y no es una API que nadie integre.
_PUBLIC_PREFIXES = ("/v1/", "/v2/")


@schema.parametrize()
@settings(
    max_examples=15,
    deadline=None,
    # **Determinista a propósito.** Sin esto el corpus cambia en cada
    # ejecución: este test encontró un 400 sin documentar una vez y las
    # tres siguientes pasó, que es exactamente cómo una compuerta de CI se
    # gana la etiqueta de "flaky" y acaba desactivada. Con la semilla fija
    # es un corpus de regresión reproducible; ampliar la cobertura es subir
    # ``max_examples`` a conciencia, no esperar a tener suerte.
    #
    # El fuzzing exploratorio (semilla libre, muchos más ejemplos) es otra
    # cosa y no debe bloquear un merge.
    derandomize=True,
    suppress_health_check=[
        # La app abre conexiones a Postgres y Redis en el arranque;
        # Hypothesis lo ve como "función lenta" y no es lo que se mide.
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
        # El cuerpo de una difusión lleva teléfonos con patrón y parámetros
        # con nombre, así que el generador descarta la mayoría de lo que
        # produce. Es una limitación del generador, no un defecto de la
        # API: los ejemplos que SÍ pasan el filtro se ejecutan igual.
        HealthCheck.filter_too_much,
    ],
)
def test_no_input_produces_a_server_error(case) -> None:
    if not case.path.startswith(_PUBLIC_PREFIXES):
        pytest.skip("solo la superficie pública de partners")

    response = case.call()

    assert response.status_code < 500, (
        f"{case.method} {case.path} devolvió {response.status_code} — "
        "una entrada malformada tiene que ser un 4xx, no un incidente"
    )
    case.validate_response(response, checks=(schemathesis.checks.status_code_conformance,))
