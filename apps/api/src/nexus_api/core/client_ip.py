"""De dónde sale la IP del visitante — spec 006, Requisito 7.1.

**El problema que esto arregla existía antes de esta spec.**
``api/console/auth.py`` documenta dos cubos de ritmo independientes, uno por
correo y otro por IP, y dice del segundo que *«frena el barrido de muchas
cuentas desde una»*. La IP salía de ``request.client.host``. Pero el navegador
nunca habla con esta API: habla con el BFF (ADR-032), así que
``request.client.host`` es **la IP de salida del BFF para todo el mundo**. El
cubo «por IP» era un único cubo global.

Con un formulario de login eso ya era malo. Con un formulario de alta abierto,
que además manda correo, es el vector entero.

**La solución: una cabecera propia que sólo pone el BFF.** Y tres razones para
no usar ``X-Forwarded-For``, que es lo primero que uno piensa:

1. ``X-Forwarded-For`` lo puede poner **cualquiera** que alcance la API. Una
   cabecera nuestra, dentro de una petición que ya va firmada con el token de
   servicio del BFF, no la falsifica un tercero.
2. Con ``X-Forwarded-For`` hay que adivinar cuántos proxies hay delante y cuál
   de la lista es el cliente. Adivinar mal es contar la IP de un proxy.
3. Si la cabecera falta, aquí se sabe y se dice. Con ``X-Forwarded-For``
   ausente uno cae en ``request.client.host`` sin enterarse, que es justo cómo
   se llegó a la situación anterior.

**Qué pasa cuando no hay cabecera: se cae al cubo único, no a la IP del
socket.** Es deliberado y es la dirección correcta del error — mejor limitar de
más a un conjunto de peticiones que no sabemos identificar, que fingir un
límite por IP que no lo es. Que el límite se esté aplicando en modo degradado
es visible porque el cubo tiene nombre propio.
"""

from __future__ import annotations

import ipaddress
from typing import Protocol

#: La cabecera. La pone el BFF en cada llamada pre-sesión y no la pone nadie
#: más. El nombre lleva prefijo propio para que no se confunda con las que
#: cualquier proxy del mundo inventa.
CLIENT_IP_HEADER = "X-Nexus-Client-IP"

#: A dónde van las peticiones cuya IP no se conoce. **No parece una IP a
#: propósito**: si fuera ``0.0.0.0``, una petición con esa IP real compartiría
#: cubo con todas las anónimas, y el nombre no diría nada en un panel.
SHARED_BUCKET = "sin-ip-de-cliente"


class _HasHeaders(Protocol):
    """Lo mínimo de una petición que hace falta aquí.

    Se tipa así y no como ``fastapi.Request`` para que la política se pueda
    probar sin levantar una aplicación — el mismo criterio que el resto de
    módulos que deciden algo en este repositorio.
    """

    @property
    def headers(self) -> object: ...


def resolve_client_ip(header_value: str | None) -> str:
    """La IP del visitante, o el cubo único si no se sabe.

    Un valor que no parsea como IP se trata **como ausente**, no se acepta tal
    cual. Aceptarlo dejaría que quien alcance la API mandase una cadena
    distinta en cada petición y estrenara un cubo de ritmo cada vez, que es
    exactamente tener el limitador apagado.
    """
    if header_value is None:
        return SHARED_BUCKET
    candidate = header_value.strip()
    if not candidate:
        return SHARED_BUCKET
    try:
        # ``ip_address`` acepta v4 y v6 y rechaza octetos imposibles, listas
        # separadas por comas y cualquier otra cosa.
        ipaddress.ip_address(candidate)
    except ValueError:
        return SHARED_BUCKET
    return candidate


def client_ip(request: _HasHeaders) -> str:
    """La versión que usa la API. Lee **sólo** de la cabecera del BFF."""
    headers = request.headers
    getter = getattr(headers, "get", None)
    raw = getter(CLIENT_IP_HEADER) if callable(getter) else None
    return resolve_client_ip(raw if isinstance(raw, str) else None)


def storable_client_ip(header_value: str | None) -> str | None:
    """La IP **para guardar**, que no es la misma que la IP para contar.

    `ConsoleSession.ip` es una columna ``INET``: el marcador del cubo único no
    es una IP y guardarlo reventaría el ``INSERT``. Cuando no se sabe la IP, lo
    honesto en una columna es ``NULL`` — «no consta», que es exactamente el
    caso.

    Dos funciones y no una porque son dos preguntas distintas: *«¿contra qué
    cubo cuento esta petición?»* siempre tiene respuesta; *«¿de qué IP vino?»*
    a veces no.
    """
    resolved = resolve_client_ip(header_value)
    return None if resolved == SHARED_BUCKET else resolved


def client_ip_for_storage(request: _HasHeaders) -> str | None:
    """La versión que usa la API, leyendo de la cabecera del BFF."""
    headers = request.headers
    getter = getattr(headers, "get", None)
    raw = getter(CLIENT_IP_HEADER) if callable(getter) else None
    return storable_client_ip(raw if isinstance(raw, str) else None)
