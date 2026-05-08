"""``SubprocessTool`` — adapter ``ToolBase`` que delega vía stdio MCP.

Bloque E introduce el primer subprocess server (Stagehand + Browserbase
Contexts, Node). El registry sigue exponiendo la firma estable
``dispatch(name, args, *, whitelist) -> ToolResult``; lo único nuevo es
que algunas tools ejecutan ``run()`` en un proceso aparte en vez de
in-process.

La validación pre-dispatch (whitelist + tenant context + Pydantic schema)
sigue siendo la misma — vive en ``ToolBase.invoke`` y en
``MCPRegistry.dispatch``. Lo único que cambia es ``run(payload)``: en vez
de tocar Postgres directo, serializa el payload, lo manda por stdio
JSON-RPC al server Node, y parsea la respuesta.

Convención de output del server Node (Bloque E):

  ``tools/call`` retorna ``{"content": [{"type": "text", "text": "<JSON>"}]}``
  donde ``<JSON>`` es un dict que matchea el ``output_model`` Pydantic.
  Esto evita acoplar el shape MCP estructural al envelope nuestro.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any, ClassVar, Protocol

from nexus_api.core.tenant_context import require_current_tenant

from nexus_mcp.base import (
    InputModel,
    OutputModel,
    ToolBase,
    ToolError,
    make_envelope,
)


class SubprocessTransport(Protocol):
    """Cualquier cosa que sepa hacer ``tools/call`` contra un server.

    Implementaciones:
    - ``nexus_mcp.transports.SubprocessPool`` (real, stdio JSON-RPC)
    - ``FakeAgendaProTransport`` en tests (no spawnea nada, devuelve dicts)
    """

    server_name: str

    async def call_tool(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        arguments: Mapping[str, Any],
        timeout: float = ...,
    ) -> dict[str, Any]: ...


def _extract_text_payload(mcp_response: dict[str, Any]) -> dict[str, Any]:
    """Extrae el JSON dict del primer text content del MCP response.

    El server Node devuelve el shape oficial MCP:
       ``{"content": [{"type": "text", "text": "<JSON>"}]}``
    """
    content = mcp_response.get("content")
    if not isinstance(content, list) or not content:
        raise ToolError(
            f"subprocess returned malformed MCP response (no content): {mcp_response!r}"
        )
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text":
        raise ToolError(f"subprocess returned non-text content: {first!r}")
    text = first.get("text")
    if not isinstance(text, str):
        raise ToolError(f"subprocess returned non-string text: {text!r}")
    try:
        parsed: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError(f"subprocess returned invalid JSON in text content: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ToolError(f"subprocess JSON payload is not an object: {parsed!r}")
    return parsed


def make_subprocess_tool_class(
    *,
    name: str,
    description: str,
    input_model: type[InputModel],
    output_model: type[OutputModel],
    transport_provider: TransportProvider,
    side_effects: tuple[str, ...] = (),
    timeout_s: float = 90.0,
) -> type[ToolBase]:
    """Genera dinámicamente una subclass ``ToolBase`` que ejecuta vía
    subprocess MCP.

    ``transport_provider`` es un callable ``() -> SubprocessTransport``.
    Es indirecto a propósito: el registry resuelve el transport al
    momento del dispatch (no al import time), permitiendo que tests
    inyecten un FakeAgendaProTransport sin tocar el módulo.
    """

    class _SubprocessToolImpl(ToolBase):
        name_attr: ClassVar[str] = name
        description_attr: ClassVar[str] = description
        # ToolBase declares these as ClassVar — set them on the subclass.

        async def run(self, payload: InputModel) -> OutputModel:
            assert isinstance(payload, input_model)
            tenant_id = require_current_tenant()
            transport = transport_provider()
            args = payload.model_dump(mode="json")
            try:
                mcp_response = await transport.call_tool(
                    tenant_id=tenant_id,
                    name=name,
                    arguments=args,
                    timeout=timeout_s,
                )
            except Exception as exc:
                raise ToolError(
                    f"subprocess tool {name!r} failed: {type(exc).__name__}: {exc}"
                ) from exc
            payload_dict = _extract_text_payload(mcp_response)
            try:
                return output_model.model_validate(payload_dict)
            except Exception as exc:
                raise ToolError(
                    f"subprocess tool {name!r} returned payload that does not match "
                    f"{output_model.__name__}: {exc}"
                ) from exc

    # Set ClassVar attrs. ToolBase reads these at registration time.
    _SubprocessToolImpl.name = name
    _SubprocessToolImpl.description = description
    _SubprocessToolImpl.input_model = input_model
    _SubprocessToolImpl.output_model = output_model
    _SubprocessToolImpl.side_effects = side_effects
    _SubprocessToolImpl.__name__ = f"SubprocessTool_{name.replace('.', '_')}"
    _SubprocessToolImpl.__qualname__ = _SubprocessToolImpl.__name__
    return _SubprocessToolImpl


# Convenience: un callable type para que mypy entienda la signature del
# transport_provider sin importar typing.Callable cada vez.
class TransportProvider(Protocol):
    def __call__(self) -> SubprocessTransport: ...


def subprocess_envelope(
    *,
    tool: str,
    tenant_id: uuid.UUID,
    args: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Construye el envelope estándar (mismo shape que tools in-process).

    Lo expongo separadamente para tests del server Node que quieran
    armar respuestas que lookean idénticas a las reales.
    """
    return make_envelope(
        tool=tool,
        tenant_id=tenant_id,
        args=args,
        result=result,
    )
