"""El cliente HTTP en proceso de las herramientas (CO-02).

``httpx`` sobre ``ASGITransport``: la petición entra por el mismo ASGI que
una del navegador, así que corre el enrutado, la validación Pydantic, las
dependencias (``client_scope`` → RLS), el limitador y el manejador de
errores de FastAPI. Lo único que no cruza es la red.

Sin cabecera ``Authorization``: el sujeto viaja por
``console_auth.acting_as`` (ver ``docs/companion/PLAN-CO-02.md`` §D1). El
token de consola dura 60 s y su ``jti`` se quema en la primera
presentación, así que reenviar el del navegador no es una opción, y firmar
uno nuevo exigiría meter la clave privada de la consola en la API.
"""

from __future__ import annotations

from typing import Any

import httpx

#: Host ficticio. No sale de este proceso; existe porque ``httpx`` exige
#: una URL absoluta.
BASE_URL = "http://companion.internal"

#: Techo por llamada. Una herramienta que tarda más ya rompió la
#: conversación: el usuario está mirando el cajón.
DEFAULT_TIMEOUT_S = 10.0


def get_app() -> Any:
    """La aplicación ASGI. Import perezoso a propósito: ``main`` importa el
    router de la consola, que acabaría importando este módulo."""
    from nexus_api.main import app

    return app


def make_client(app: Any = None, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> httpx.AsyncClient:
    """Un cliente por run, cerrado al terminar."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app if app is not None else get_app()),
        base_url=BASE_URL,
        timeout=timeout_s,
    )


__all__ = ["BASE_URL", "DEFAULT_TIMEOUT_S", "get_app", "make_client"]
