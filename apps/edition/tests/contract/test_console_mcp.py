"""El servidor MCP de `console.*` — Requisito 5, cierre de T025.

Sirve el catálogo ya resuelto y **vuelve a comprobar la lista blanca al invocar**. Las
dos cosas, no una: publicar bien y confiar en que nadie llame otra cosa es la mitad
del trabajo. El sustrato ya hace lo mismo con su registro, y por el mismo motivo.
"""

from __future__ import annotations

import json

import pytest

from auphere_edition.catalog import CatalogUnavailable, Tool
from auphere_edition.console_mcp import ConsoleMcpServer, ToolNotInCatalog


def server(*tools: Tool, device_present: bool = False, calls=None) -> ConsoleMcpServer:
    return ConsoleMcpServer(
        source=lambda: list(tools),
        device_present=lambda: device_present,
        invoke=calls or (lambda name, args: {"ok": name}),
    )


def test_initialize_announces_the_tools_capability():
    reply = server(Tool("console.clients.list")).handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert reply["id"] == 1
    assert "tools" in reply["result"]["capabilities"]


def test_tools_list_publishes_exactly_the_resolved_catalog():
    reply = server(Tool("console.clients.list"), Tool("console.usage.read")).handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    assert {t["name"] for t in reply["result"]["tools"]} == {
        "console.clients.list",
        "console.usage.read",
    }


def test_tools_list_applies_the_network_reach_rule():
    """Con dispositivo presente, lo que alcanza la web no se publica (R14)."""
    reply = server(
        Tool("connector.web.fetch", reaches_network=True),
        Tool("console.clients.list"),
        device_present=True,
    ).handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert {t["name"] for t in reply["result"]["tools"]} == {"console.clients.list"}


def test_an_unresolvable_catalog_is_an_error_not_an_empty_list():
    """R5.3 — publicar cero herramientas diría «no tienes nada», que es otra cosa."""

    def broken():
        raise TimeoutError("la API no contesta")

    s = ConsoleMcpServer(source=broken, device_present=lambda: False, invoke=lambda n, a: None)
    reply = s.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    assert "error" in reply
    assert "result" not in reply


def test_calling_a_tool_outside_the_catalog_is_refused():
    """Defensa en profundidad: el catálogo publicado no es la única puerta."""
    with pytest.raises(ToolNotInCatalog):
        server(Tool("console.clients.list")).invoke_tool("console.secreto", {})


def test_calling_a_tool_excluded_by_network_reach_is_refused():
    """Lo retirado del catálogo tampoco se puede invocar a mano."""
    s = server(
        Tool("connector.web.fetch", reaches_network=True), device_present=True
    )
    with pytest.raises(ToolNotInCatalog):
        s.invoke_tool("connector.web.fetch", {})


def test_a_tool_in_the_catalog_is_invoked():
    seen = {}

    def invoke(name, args):
        seen["name"] = name
        return {"rows": []}

    s = server(Tool("console.clients.list"), calls=invoke)
    assert s.invoke_tool("console.clients.list", {}) == {"rows": []}
    assert seen["name"] == "console.clients.list"


def test_an_unknown_method_gets_a_jsonrpc_error_not_a_crash():
    reply = server().handle({"jsonrpc": "2.0", "id": 9, "method": "does/not/exist"})
    assert reply["error"]["code"] == -32601


def test_a_notification_gets_no_reply():
    """Sin ``id`` es una notificación: contestar rompería el protocolo."""
    assert server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


# ── el bucle stdio, que es el punto de entrada real ────────────────────


def test_stdio_frames_one_json_object_per_line():
    import io

    out = io.StringIO()
    server(Tool("console.clients.list")).serve_stdio(
        stdin=io.StringIO(
            '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
        ),
        stdout=out,
    )
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2], "la notificación no debe contestarse"


def test_stdio_survives_an_unreadable_line():
    """El sustrato escribe en este canal; una línea rota no puede tumbar la sesión."""
    import io

    out = io.StringIO()
    server(Tool("console.clients.list")).serve_stdio(
        stdin=io.StringIO('esto no es json\n{"jsonrpc":"2.0","id":7,"method":"tools/list"}\n'),
        stdout=out,
    )
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert len(replies) == 1 and replies[0]["id"] == 7
