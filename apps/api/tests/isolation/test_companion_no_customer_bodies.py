"""Garantía de aislamiento — el Companion nunca sirve el cuerpo de un
mensaje de un cliente final (decisión C8, CO-01).

Por qué este archivo existe
---------------------------
``test_console_scope.py`` recorre el OpenAPI de todas las rutas
``/console/*`` y rechaza cualquier propiedad de respuesta que se llame como
el cuerpo de un mensaje (``content``, ``text``, ``body``, ``transcript``…),
con una lista blanca de tres entradas.

El Companion **sí** sirve una transcripción por REST
(``GET /console/companion/runs/{id}/events``) — la suya: lo que Auphere le
dijo al partner y lo que el partner le dijo a Auphere. Tiene que sobrevivir
a un F5, a un portátil cerrado y a un reinicio de la API, así que no puede
vivir en la memoria del navegador como la del playground.

Había dos caminos y se eligió el segundo:

1. **Ampliar ``ALLOWED_RESPONSE_FIELDS``.** Rechazado. Esa lista es GLOBAL:
   se resta de los infractores de *todas* las rutas. Meter ``text`` ahí para
   desbloquear un carril ciega la comprobación en los otros ~60 endpoints
   de la consola, para siempre.
2. **Nombrar el modelo para que no colisione, y construir aquí un guardián
   propio, más fuerte.** ``CompanionEventOut`` es ``{seq, event, data}`` con
   ``data`` sin propiedades declaradas — la forma honesta, porque los
   payloads son heterogéneos por diseño y una unión tipada obligaría a
   declarar ``text`` como propiedad.

Un ``dict`` opaco no es una garantía, es la ausencia de una. La garantía se
construye donde los eventos se ESCRIBEN: ``COMPANION_EVENTS`` es un
catálogo cerrado de evento → claves permitidas, aplicado por el publicador,
y esto lo prueba.

Cualquier herramienta que CO-02 añada tiene que pasar por aquí, no por el
recorrido genérico. La segunda mitad del archivo es justo eso: las claves
de los eventos del bucle de herramientas, y la comprobación de que toda
herramienta lee un endpoint ``/console/*` real — que es lo que la devuelve
a la red del guardián genérico.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.api.companion_streaming import (
    COMPANION_AUTHORED_EVENTS,
    COMPANION_EVENTS,
    UnknownCompanionEvent,
    publish,
    read_events,
    sanitise_payload,
)
from tests.isolation.test_console_scope import FORBIDDEN_RESPONSE_FIELDS

pytestmark = [pytest.mark.isolation]

#: Lo único que el Companion puede llamar ``text``: sus propias palabras.
#: Cualquier otra clave del conjunto prohibido es, por definición, el cuerpo
#: de un mensaje que escribió alguien que no es ni Auphere ni el partner.
COMPANION_TEXT_KEYS = {"text"}


def test_no_catalogued_payload_key_can_carry_a_customer_body() -> None:
    """Ninguna clave declarada se llama como el cuerpo de un mensaje ajeno,
    salvo ``text`` en los dos eventos que el propio Companion redacta."""
    offenders: dict[str, set[str]] = {}
    for event, keys in COMPANION_EVENTS.items():
        bad = (keys & FORBIDDEN_RESPONSE_FIELDS) - (
            COMPANION_TEXT_KEYS if event in COMPANION_AUTHORED_EVENTS else set()
        )
        if bad:
            offenders[event] = bad
    assert not offenders, (
        f"claves que podrían llevar el cuerpo de un mensaje de cliente final: {offenders}. "
        "O se renombran, o se justifica aquí por qué ese texto lo escribió el Companion."
    )


def test_text_is_confined_to_the_events_the_companion_authors() -> None:
    """Un evento nuevo no puede colar ``text`` sin declararse como autorado
    por el Companion — y declararlo obliga a pasar por este archivo."""
    with_text = {e for e, keys in COMPANION_EVENTS.items() if keys & COMPANION_TEXT_KEYS}
    assert with_text <= COMPANION_AUTHORED_EVENTS, (
        f"eventos con 'text' fuera de la lista de autorados: {with_text - COMPANION_AUTHORED_EVENTS}"
    )


def test_the_catalogue_is_closed() -> None:
    """Publicar algo no declarado falla en vez de colarse."""
    with pytest.raises(UnknownCompanionEvent):
        sanitise_payload("customer.message", {"content": "hola"})


def test_the_publisher_really_strips_a_smuggled_body() -> None:
    """Control del control. Si el filtro dejara de filtrar, esta prueba —y
    solo esta— se pone roja."""
    clean = sanitise_payload(
        "tool.completed" if "tool.completed" in COMPANION_EVENTS else "cost.updated",
        {"input_tokens": 1, "content": "lo que escribió un cliente final", "body": "…"},
    )
    assert "content" not in clean and "body" not in clean


async def test_a_smuggled_body_never_reaches_the_durable_log(fake_redis) -> None:
    """Extremo a extremo del guardián: lo que no está declarado no llega al
    log, así que tampoco puede salir por ``/events`` ni por el stream."""
    run_id = uuid.uuid4()
    await publish(
        fake_redis,
        run_id,
        seq=1,
        event="text.delta",
        data={
            "message_id": "m1",
            "text": "la respuesta del Companion",
            "transcript": "hola, quería reservar cita",  # cuerpo de cliente final
            "interactive_payload": {"button": "Sí"},
        },
    )
    events, _gap = await read_events(fake_redis, run_id)
    assert set(events[0].data) == {"message_id", "text"}


# ── C3 · las herramientas de CO-02 ─────────────────────────────────────
#
# Las herramientas no devuelven su resultado por el stream —eso va al
# contexto del modelo—, pero sí anuncian qué se llamó y qué se leyó. Dos
# frentes, y los dos se cierran aquí: las claves de los eventos nuevos (que
# ya cubre el recorrido del catálogo de arriba) y el catálogo de
# herramientas, que es lo que decide a qué endpoints puede llegar el
# Companion.


def test_the_new_tool_events_are_in_the_closed_catalogue() -> None:
    """Un evento del bucle de herramientas que no esté declarado no se
    publica: :func:`sanitise_payload` lanza."""
    for event in ("tool.call.started", "tool.call.completed", "citation"):
        assert event in COMPANION_EVENTS, f"{event} no está en el catálogo cerrado"


def test_no_tool_event_can_carry_a_read_body() -> None:
    """El resultado de una lectura NUNCA viaja por el stream. Si alguien
    añadiera una clave ``result``/``content`` a ``tool.call.completed``, la
    transcripción del Companion pasaría a llevar datos de negocio de un
    cliente del partner sin que nadie lo decidiera."""
    for event in ("tool.call.started", "tool.call.completed", "citation"):
        assert not (COMPANION_EVENTS[event] & FORBIDDEN_RESPONSE_FIELDS)
        assert "result" not in COMPANION_EVENTS[event]


def test_every_tool_reads_a_console_route_and_nothing_else() -> None:
    """Toda herramienta apunta a una ruta ``/console/*`` que existe y que es
    un ``GET``.

    Es lo que ata la garantía C3 al guardián genérico: una respuesta que
    sale por un endpoint de la consola ya pasó por el recorrido del OpenAPI
    de ``test_console_scope.py``, que prohíbe los cuerpos de mensaje. Una
    herramienta que apuntara a otra parte quedaría fuera de esa red.
    """
    from nexus_api.companion.tools.catalog import READ_TOOLS
    from nexus_api.main import app

    routes = {
        (getattr(r, "path", None), method)
        for r in app.routes
        for method in (getattr(r, "methods", None) or set())
    }
    missing = []
    for tool in READ_TOOLS:
        assert tool.method == "GET", f"{tool.name} no es de lectura"
        assert tool.path.startswith("/console/"), f"{tool.name} sale de /console/*"
        # El catálogo nombra el parámetro ``client_ref``; la ruta de FastAPI
        # lo llama ``{ref}``. Se normaliza para comparar.
        declared = tool.path.replace("{client_ref}", "{ref}")
        if (declared, "GET") not in routes:
            missing.append((tool.name, declared))
    assert not missing, f"herramientas que apuntan a rutas inexistentes: {missing}"


def test_conversation_stats_reads_metadata_and_never_the_list() -> None:
    """Decisión C8, la explícita: el Companion puede saber CUÁNTAS
    conversaciones hubo y cuántas se escalaron, y no puede leer ni una."""
    from nexus_api.companion.tools.catalog import TOOLS_BY_NAME

    stats = TOOLS_BY_NAME["console.conversation_stats"]
    assert stats.path.endswith("/conversations/stats")
    listing = {t.path for t in TOOLS_BY_NAME.values()}
    assert "/console/clients/{client_ref}/conversations" not in listing


def test_no_tool_accepts_a_tenant_or_partner_id() -> None:
    """La regla CP-04, heredada tal cual: el cliente se nombra por su
    referencia y lo resuelve el router bajo el principal."""
    from nexus_api.companion.tools.catalog import READ_TOOLS

    for tool in READ_TOOLS:
        names = {p.name for p in tool.params}
        assert not (names & {"tenant_id", "partner_id", "tenant", "partner"}), tool.name
