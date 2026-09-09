"""El servidor MCP de ``console.*`` — Requisito 5. Cierra T025.

Es lo que el sustrato lanza como ``auphere-console-mcp`` y lo único que el teammate
tiene delante para operar la plataforma: por herramienta, nunca navegando (§VI).

**Sin dependencias.** Corre en la máquina del partner, y ahí cada dependencia es
superficie de suministro y una lectura de licencia más (§VIII). JSON-RPC sobre stdio
con la librería estándar es poco código y se audita entero.

**Publica y vuelve a comprobar.** ``tools/list`` sirve el catálogo ya resuelto, y
``invoke_tool`` **revalida** contra ese mismo catálogo antes de ejecutar. Publicar
bien y confiar en que nadie llame otra cosa es la mitad del trabajo: el registro del
propio sustrato hace esta doble comprobación por el mismo motivo.

**Un catálogo irresoluble es un error, no una lista vacía.** Servir cero herramientas
diría *«no tienes nada»*, que es una afirmación distinta —y falsa— de *«no puedo
garantizar qué tienes»*. R5.3 pide lo segundo.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from typing import Any

from auphere_edition.catalog import CatalogUnavailable, Tool, resolve_catalog

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "auphere-console"

_METHOD_NOT_FOUND = -32601
_INTERNAL_ERROR = -32603


class ToolNotInCatalog(RuntimeError):
    """Se pidió una herramienta que el catálogo resuelto no contiene."""


class ConsoleMcpServer:
    """Sirve el catálogo resuelto y ejecuta solo lo que está en él.

    Las tres dependencias entran inyectadas para que las reglas se puedan probar sin
    red ni procesos: la fuente del catálogo, la presencia del dispositivo y el
    invocador real.
    """

    def __init__(
        self,
        *,
        source: Callable[[], Sequence[Tool]],
        device_present: Callable[[], bool],
        invoke: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        self._source = source
        self._device_present = device_present
        self._invoke = invoke

    # ── catálogo ───────────────────────────────────────────────────────

    def _resolved(self) -> list[Tool]:
        return resolve_catalog(self._source, device_present=self._device_present())

    def invoke_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Revalida antes de ejecutar. El catálogo publicado no es la única puerta."""
        if name not in {t.name for t in self._resolved()}:
            raise ToolNotInCatalog(
                f"{name} no está en el catálogo de esta sesión y no se ejecuta"
            )
        return self._invoke(name, arguments)

    # ── JSON-RPC ───────────────────────────────────────────────────────

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Atiende una petición. Devuelve ``None`` para una notificación (sin ``id``)."""
        method = request.get("method", "")
        request_id = request.get("id")
        if request_id is None:
            return None

        try:
            if method == "initialize":
                return self._ok(
                    request_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"},
                    },
                )
            if method == "tools/list":
                return self._ok(
                    request_id,
                    {"tools": [{"name": t.name} for t in self._resolved()]},
                )
            if method == "tools/call":
                params = request.get("params") or {}
                result = self.invoke_tool(
                    str(params.get("name", "")), dict(params.get("arguments") or {})
                )
                return self._ok(request_id, {"content": result})
        except CatalogUnavailable as exc:
            return self._err(request_id, _INTERNAL_ERROR, str(exc))
        except ToolNotInCatalog as exc:
            return self._err(request_id, _INTERNAL_ERROR, str(exc))

        return self._err(request_id, _METHOD_NOT_FOUND, f"método desconocido: {method}")

    @staticmethod
    def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _err(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    # ── stdio ──────────────────────────────────────────────────────────

    def serve_stdio(self, stdin: Any = None, stdout: Any = None) -> None:
        """Bucle de líneas JSON. Una línea ilegible se ignora, no tumba la sesión."""
        source = stdin or sys.stdin
        sink = stdout or sys.stdout
        for line in source:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue
            reply = self.handle(request)
            if reply is not None:
                sink.write(json.dumps(reply) + "\n")
                sink.flush()


__all__ = ["PROTOCOL_VERSION", "SERVER_NAME", "ConsoleMcpServer", "ToolNotInCatalog"]


def main() -> int:
    """Punto de entrada de ``auphere-console-mcp``.

    Falla cerrado antes de servir nada: sin la URL y el token de la sesión no hay
    catálogo que garantizar, y R5.3 dice que entonces la sesión no abre.
    """
    import os

    from auphere_edition.catalog_source import http_catalog_source

    base_url = os.environ.get("AUPHERE_API_URL", "")
    token = os.environ.get("AUPHERE_SESSION_TOKEN", "")
    if not base_url or not token:
        sys.stderr.write(
            "auphere-console-mcp: faltan AUPHERE_API_URL o AUPHERE_SESSION_TOKEN; "
            "no se sirve un catálogo que no se puede garantizar (Requisito 5.3)\n"
        )
        return 2

    device_present = os.environ.get("AUPHERE_DEVICE_PRESENT", "") == "1"
    server = ConsoleMcpServer(
        source=http_catalog_source(base_url, token=token),
        device_present=lambda: device_present,
        invoke=lambda name, args: {"error": "la ejecución de herramientas llega con US1"},
    )
    server.serve_stdio()
    return 0
