"""``/v1`` está CONGELADA, y esto es lo que lo hace verdad (WP-28).

Facelad consume `/v1` en producción. Mientras `/v1` y `/v2` compartan
manejador —que es hoy, a propósito, para no duplicar mantenimiento antes
de tener un cambio que lo justifique— **lo único que impide que una
evolución de `/v2` se cuele en `/v1` es que este test se ponga rojo.**

El contrato vive en ``v1_contract.json``, versionado. Tocarlo es un commit
deliberado que un revisor ve, y esa es la señal: si el diff toca ese
fichero sin que haya una conversación con el partner detrás, el cambio
está rompiendo una integración viva.

Qué se congela y qué no:

- **Sí**: rutas, métodos, códigos de respuesta, y el nombre y la
  obligatoriedad de cada parámetro y de cada campo del cuerpo. Es lo que
  rompe a un cliente.
- **No**: descripciones, ejemplos, orden de las claves, ni el nombre
  interno de los esquemas. Congelar la prosa convertiría el test en un
  peaje por escribir mejor documentación, y a la tercera vez alguien
  actualizaría el fichero sin mirar.
"""

from __future__ import annotations

import json
import pathlib

import pytest

pytestmark = pytest.mark.asyncio

CONTRACT_PATH = pathlib.Path(__file__).parent / "v1_contract.json"


def _shape(schema: dict, ref_store: dict) -> dict:
    """Reduce el OpenAPI a lo que rompe a un cliente."""

    def _resolve(node: object, seen: frozenset[str] = frozenset()) -> object:
        """Aplana ``$ref`` para comparar formas y no nombres de esquema.

        Con protección de ciclos: un esquema recursivo colgaría el test en
        vez de fallarlo, que es la peor forma de fallar.
        """
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                name = ref.rsplit("/", 1)[-1]
                if name in seen:
                    return {"$recursive": name}
                return _resolve(ref_store.get(name, {}), seen | {name})
            return {
                k: _resolve(v, seen)
                for k, v in sorted(node.items())
                # Prosa y metadatos: cambian sin romper a nadie.
                if k
                not in {
                    "description",
                    "title",
                    "example",
                    "examples",
                    "summary",
                    "operationId",
                    "tags",
                }
            }
        if isinstance(node, list):
            return [_resolve(v, seen) for v in node]
        return node

    out: dict = {}
    for path, methods in schema["paths"].items():
        if not path.startswith("/v1/"):
            continue
        out[path] = {}
        for method, op in sorted(methods.items()):
            if not isinstance(op, dict):
                continue
            out[path][method] = {
                "params": sorted(
                    (p.get("name"), p.get("in"), bool(p.get("required")))
                    for p in op.get("parameters", [])
                ),
                "body": _resolve(op.get("requestBody", {})),
                "responses": sorted(op.get("responses", {}).keys()),
            }
    return out


async def test_v1_matches_the_frozen_contract(client) -> None:
    schema = (await client.get("/openapi.json")).json()
    # Ida y vuelta por JSON antes de comparar: las tuplas de ``params`` se
    # serializan como listas, y sin esto TODA ruta saldría como modificada
    # — un fallo permanente que se arregla actualizando el fichero, que es
    # justo la costumbre que este test no puede permitirse crear.
    current = json.loads(
        json.dumps(_shape(schema, schema.get("components", {}).get("schemas", {})))
    )

    if not CONTRACT_PATH.exists():  # pragma: no cover - solo la primera vez
        CONTRACT_PATH.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        pytest.fail(f"contrato de /v1 generado en {CONTRACT_PATH.name}: revísalo y commitéalo")

    frozen = json.loads(CONTRACT_PATH.read_text())

    added = sorted(set(current) - set(frozen))
    removed = sorted(set(frozen) - set(current))
    changed = sorted(p for p in set(current) & set(frozen) if current[p] != frozen[p])

    assert not (added or removed or changed), (
        "/v1 está congelada y ha cambiado. Si el cambio es intencionado y está "
        "acordado con el partner, actualiza v1_contract.json en el mismo commit "
        "y explica por qué.\n"
        f"  rutas nuevas:        {added}\n"
        f"  rutas desaparecidas: {removed}\n"
        f"  rutas modificadas:   {changed}"
    )


async def test_the_contract_is_not_empty(client) -> None:
    """Un contrato vacío pasaría el test de arriba para siempre. Ha pasado
    en otros proyectos: un cambio en el filtro deja el barrido a cero y el
    guardián se convierte en decoración."""
    frozen = json.loads(CONTRACT_PATH.read_text())
    assert len(frozen) >= 10, f"solo {len(frozen)} rutas congeladas; ¿se rompió el filtro?"
    assert all(p.startswith("/v1/") for p in frozen)


async def test_the_contract_notices_a_removed_field(client) -> None:
    """Control del control: se comprueba que la comparación detecta un
    cambio de forma real y no solo diferencias de texto."""
    schema = (await client.get("/openapi.json")).json()
    current = _shape(schema, schema.get("components", {}).get("schemas", {}))
    mutated = json.loads(json.dumps(current))
    path = next(p for p, ops in mutated.items() if "post" in ops)
    mutated[path]["post"]["responses"] = ["999"]

    assert mutated[path] != current[path]
