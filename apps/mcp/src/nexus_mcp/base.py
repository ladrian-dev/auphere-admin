"""Tool base classes — schema-first contract every server implements.

Each tool is a ``ToolBase`` subclass with class-level attributes:

- ``name``         — fully-qualified ``server.action`` matching ``tool_catalog.name``.
- ``description``  — shown to the LLM in the function-calling tool list.
- ``input_model``  — Pydantic model that validates the LLM's arguments.
- ``output_model`` — Pydantic model that the result must serialise as.
- ``side_effects`` — informational, mirrors ``tool_catalog.side_effects``.

The ``invoke(args)`` method:
1. Asserts the active tenant via ``require_current_tenant`` — a tool may
   never be called outside a tenant-scoped context.
2. Validates ``args`` through ``input_model``.
3. Delegates to ``run(payload)`` (subclass implements business logic).
4. Wraps the return into ``output_model`` and serialises it.

The result envelope (``ToolResult``) is what the pipeline persists into
``Message.tool_calls`` — same shape as the block-C stubs so the existing
schema doesn't change.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from nexus_api.core.tenant_context import require_current_tenant
from pydantic import BaseModel, ConfigDict


class InputModel(BaseModel):
    """Marker base for tool input schemas. Disallow extras so the LLM cannot
    smuggle ``tenant_id`` or other ambient state through arguments."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    """Marker base for tool output schemas."""

    model_config = ConfigDict(extra="forbid")


# ── errors ────────────────────────────────────────────────────────────────────


class ToolError(Exception):
    """Raised by a tool when execution fails for a tenant-internal reason."""


class ToolNotInWhitelist(ToolError):
    """Raised by ``MCPRegistry.dispatch`` when a tool name is missing from
    the active ``agent_config.tools`` whitelist for this tenant.

    The metric ``isolation.tool_whitelist_violation`` is incremented BEFORE
    the exception propagates so callers don't have to remember.
    """


# ── result envelope ──────────────────────────────────────────────────────────


ToolResult = dict[str, Any]


def make_envelope(
    *,
    tool: str,
    tenant_id: uuid.UUID,
    args: dict[str, Any],
    result: dict[str, Any],
    status: str = "ok",
) -> ToolResult:
    return {
        "tool": tool,
        "tenant_id": str(tenant_id),
        "args": dict(args),
        "result": dict(result),
        "status": status,
        "executed_at": datetime.now(UTC).isoformat(),
    }


# ── tool definition (LLM-facing) ─────────────────────────────────────────────


@dataclass(frozen=True)
class ToolDef:
    """JSON-Schema view of a tool, suitable for LiteLLM's ``tools=`` param.

    The ``parameters`` field is the raw JSON Schema dict produced by
    ``InputModel.model_json_schema()``; the LLM uses it to decide which
    arguments to fill.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_tool(self) -> dict[str, Any]:
        """Render in the OpenAI / Anthropic / LiteLLM ``tools`` shape."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── base class ───────────────────────────────────────────────────────────────


class ToolBase(ABC):
    """All concrete tools subclass this and implement ``run``.

    The class-level attributes are read by the registry at startup to build
    the catalog of ``ToolDef`` objects.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[InputModel]]
    output_model: ClassVar[type[OutputModel]]
    side_effects: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    async def run(self, payload: InputModel) -> OutputModel:
        """Subclass-implemented business logic. ``payload`` is already
        validated; the active tenant is in the contextvar."""

    async def invoke(self, args: dict[str, Any]) -> ToolResult:
        tenant_id = require_current_tenant()
        validated = self.input_model.model_validate(args)
        out = await self.run(validated)
        # Strict shape check — ``out`` MUST be an ``output_model`` instance
        # so the schema we publish is the schema the tool returns.
        if not isinstance(out, self.output_model):
            raise ToolError(
                f"tool {self.name!r} returned {type(out).__name__}, "
                f"expected {self.output_model.__name__}"
            )
        return make_envelope(
            tool=self.name,
            tenant_id=tenant_id,
            args=validated.model_dump(mode="json"),
            result=out.model_dump(mode="json"),
        )

    @classmethod
    def to_tool_def(cls) -> ToolDef:
        return ToolDef(
            name=cls.name,
            description=cls.description,
            parameters=cls.input_model.model_json_schema(),
        )
