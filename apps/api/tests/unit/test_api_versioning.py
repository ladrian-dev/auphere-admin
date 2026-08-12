"""Versionado por path de la superficie de partners (WP-28).

Dos garantías que se compran por separado:

- **`/v2` existe y sirve lo mismo**, para que una integración nueva no
  nazca sobre una versión en mantenimiento;
- **`/v1` no cambia**, que es lo que Facelad necesita mientras migra.

La segunda no la da la organización del código: hoy las dos versiones
comparten manejador, así que lo único que impide que un cambio en `/v2`
se cuele en `/v1` es el contrato congelado de `test_v1_contract.py`. Este
archivo cubre el mecanismo; aquel cubre la promesa.
"""

from __future__ import annotations

import pytest

from nexus_api.api.versioning import API_VERSIONS, CURRENT_API_VERSION

pytestmark = pytest.mark.asyncio


async def test_both_versions_serve_the_same_surface(client) -> None:
    schema = (await client.get("/openapi.json")).json()
    by_version = {
        v: {p.removeprefix(f"/{v}") for p in schema["paths"] if p.startswith(f"/{v}/")}
        for v in API_VERSIONS
    }
    assert by_version["v1"], "no hay rutas bajo /v1"
    assert by_version["v1"] == by_version["v2"], (
        "las dos versiones han divergido sin que nadie lo declare:\n"
        f"  solo en v1: {sorted(by_version['v1'] - by_version['v2'])}\n"
        f"  solo en v2: {sorted(by_version['v2'] - by_version['v1'])}"
    )


async def test_operation_ids_are_unique_across_versions(client) -> None:
    """Montar el mismo manejador dos veces produce ids duplicados en el
    OpenAPI si nadie lo evita, y cualquier generador de cliente saca
    entonces dos métodos con el mismo nombre."""
    schema = (await client.get("/openapi.json")).json()
    ids = [
        op["operationId"]
        for path in schema["paths"].values()
        for op in path.values()
        if isinstance(op, dict) and "operationId" in op
    ]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"operationId duplicados: {sorted(duplicates)}"


async def test_v1_answers_with_deprecation_headers(client) -> None:
    r = await client.get("/v1/partners/whatsapp/signup-config")
    assert "Deprecation" in r.headers
    assert r.headers["Link"] == f'</{CURRENT_API_VERSION}>; rel="successor-version"'


async def test_v1_announces_deprecation_on_errors_too(client) -> None:
    """Un partner que está recibiendo 401 o 429 de `/v1` es justo quien
    más necesita enterarse. Por eso va en un middleware y no en una
    dependencia del camino feliz."""
    r = await client.get("/v1/partners/clients/desconocido")
    assert r.status_code in (401, 403, 404)
    assert "Deprecation" in r.headers


async def test_v2_carries_no_deprecation_headers(client) -> None:
    """Control negativo: si las cabeceras salieran en todas partes, el
    test de arriba pasaría sin que el middleware distinguiera nada."""
    r = await client.get("/v2/partners/whatsapp/signup-config")
    assert "Deprecation" not in r.headers
    assert "Sunset" not in r.headers


async def test_no_sunset_date_is_announced_until_one_is_agreed(client) -> None:
    """Anunciar una fecha de apagado que nadie ha acordado con el partner
    es peor que no anunciar ninguna: se convierte en un compromiso que
    aparece en su código de integración."""
    r = await client.get("/v1/partners/whatsapp/signup-config")
    assert "Sunset" not in r.headers


async def test_the_unversioned_path_is_not_served(client) -> None:
    """El prefijo lo pone el montaje, así que un router al que se le
    olvide la versión se notaría aquí y no en producción."""
    assert (await client.get("/partners/whatsapp/signup-config")).status_code == 404
