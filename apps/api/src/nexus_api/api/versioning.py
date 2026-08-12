"""Versionado por path de la API pública de partners (WP-28).

Facelad consume `/v1` en producción. Evolucionar esa superficie sin romper
su integración exige dos cosas que no son la misma: **poder cambiar** (una
versión nueva donde hacerlo) y **no cambiar** (una garantía de que la vieja
sigue igual).

Cómo se resuelve cada una, y por qué así:

- **Poder cambiar**: los routers ya no llevan la versión en su prefijo. Se
  montan una vez por versión viva. Hoy `/v1` y `/v2` sirven exactamente
  los mismos manejadores — duplicarlos "por si acaso" habría sido duplicar
  el mantenimiento antes de tener un solo cambio que justificara la
  bifurcación. El día que uno de ellos tenga que divergir se copia ESE
  manejador, no la superficie entera.
- **No cambiar**: la congelación NO la impone el código, la impone un test
  de contrato (`tests/unit/test_v1_contract.py`) contra un OpenAPI
  versionado en el repo. Es la única forma que funciona: mientras las dos
  versiones compartan manejador, lo que impide que un cambio en `/v2` se
  cuele en `/v1` es que el build se ponga rojo, no la organización de los
  ficheros.

`/v1` responde además con cabeceras de obsolescencia. `Sunset` solo sale
si hay fecha configurada: anunciar una fecha de apagado que nadie ha
acordado con el partner es peor que no anunciar ninguna.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute

#: Versiones vivas de la superficie pública, en orden.
API_VERSIONS: tuple[str, ...] = ("v1", "v2")

#: La que se documenta como recomendada para integraciones nuevas.
CURRENT_API_VERSION = "v2"

#: Congeladas: mismos manejadores, pero su forma no puede cambiar.
DEPRECATED_API_VERSIONS: frozenset[str] = frozenset({"v1"})


#: Respuestas de error que TODA la superficie pública puede devolver, por
#: compartir el mismo esquema de autenticación y el mismo limitador.
#:
#: Estaban sin documentar hasta WP-28 y lo detectó Schemathesis en su
#: primera pasada: el OpenAPI publicado declaraba ``200, 422`` y la API
#: devolvía 401 en cuanto faltaba la cabecera. Un partner que genere su
#: cliente a partir del esquema obtiene código que no contempla que su
#: clave caduque — y se entera en producción.
COMMON_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    400: {
        "description": (
            "El cuerpo no se pudo leer (JSON ilegible o codificación "
            "inválida). Distinto del 422, que significa que el cuerpo se "
            "leyó y no cumple el esquema — lo decide FastAPI, no nosotros."
        )
    },
    401: {"description": "Falta la clave de API, o no es válida."},
    403: {"description": "Clave válida sin el scope necesario, o partner suspendido."},
    429: {
        "description": (
            "Límite de peticiones superado para esta superficie. Reintentar "
            "con espera; el cubo se rellena a ritmo constante."
        )
    },
}


def _unique_id_factory(version: str) -> Callable[[APIRoute], str]:
    """``operation_id`` distinto por versión.

    Sin esto, montar el mismo manejador dos veces produce dos operaciones
    con el mismo id en el OpenAPI: FastAPI avisa y cualquier generador de
    cliente produce métodos duplicados. El id lleva la versión delante
    porque es lo que distingue las dos operaciones para quien consume el
    esquema.
    """

    def _generate(route: APIRoute) -> str:
        return f"{version}_{route.name}"

    return _generate


def mount_versioned(app: FastAPI, routers: list[APIRouter]) -> None:
    """Monta cada router bajo cada versión viva."""
    for version in API_VERSIONS:
        for router in routers:
            app.include_router(
                router,
                prefix=f"/{version}",
                generate_unique_id_function=_unique_id_factory(version),
                responses=COMMON_ERROR_RESPONSES,
            )


def deprecation_middleware(
    *,
    deprecation_date: str,
    sunset_date: str | None,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Cabeceras RFC 8594 / RFC 9745 en las versiones congeladas.

    Va en un middleware y no en una dependencia para que también salgan en
    las respuestas de error: un partner que está recibiendo 429 o 404 de
    `/v1` es exactamente quien más necesita enterarse de que esa versión
    está en mantenimiento.
    """

    async def _middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        version = request.url.path.lstrip("/").split("/", 1)[0]
        if version in DEPRECATED_API_VERSIONS:
            response.headers["Deprecation"] = deprecation_date
            if sunset_date:
                response.headers["Sunset"] = sunset_date
            # Apunta a dónde está la versión viva. El enlace es parte del
            # contrato de la cabecera: sin él, "deprecated" no dice qué
            # hacer al respecto.
            response.headers["Link"] = f'</{CURRENT_API_VERSION}>; rel="successor-version"'
        return response

    return _middleware
