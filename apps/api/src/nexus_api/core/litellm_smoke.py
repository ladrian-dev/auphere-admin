"""Build-time check: a LiteLLM call that carries tools must not need a package the image lacks.

The images install their Python dependencies by resolving them when they are
built, not from ``uv.lock``. So a new LiteLLM release reaches staging and
production without CI ever having run it. LiteLLM 1.106.0 (2026-10-18) is the
case that made this check exist: it imports its MCP gateway, and with it the
optional ``mcp`` package, on every ``completion()`` that carries ``tools``.
Without ``mcp`` installed every agent turn with tools died inside the runner,
for every model, and the runner logged it as «proxy unreachable».

The pin in ``pyproject.toml`` keeps that release out. This check catches the
next one: both Dockerfiles run ``python -m nexus_api.core.litellm_smoke``
right after installing, so the build fails instead of the turn.

The call goes to a closed local port and never leaves the build machine. A
connection error is the expected outcome. An ``ImportError`` anywhere in the
exception chain means that, in this environment, a tool call would crash
before reaching any provider.
"""

from __future__ import annotations

import asyncio
import os
import sys
from importlib import metadata

_TOOL = {
    "type": "function",
    "function": {
        "name": "inventory__search_products",
        "description": "Smoke-test tool. Never called.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
    },
}

#: Nothing listens here, so the request fails at connect time, locally.
_CLOSED_PORT = "http://127.0.0.1:9"


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not s for s in seen):
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def import_errors_on_tool_call() -> list[ImportError]:
    """Make one tool-carrying LiteLLM call and return every ImportError it raised."""
    # Do not fetch the model price map from the internet while building.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm

    async def call() -> None:
        await litellm.acompletion(
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "ping"}],
            tools=[_TOOL],
            api_key="smoke-test",
            api_base=_CLOSED_PORT,
            timeout=5,
            num_retries=0,
        )

    try:
        asyncio.run(call())
    except Exception as exc:
        return [e for e in _chain(exc) if isinstance(e, ImportError)]
    return []


def main() -> int:
    errors = import_errors_on_tool_call()
    version = metadata.version("litellm")
    if errors:
        for err in errors:
            print(
                f"litellm {version}: a tool call fails with {type(err).__name__}: {err}",
                file=sys.stderr,
            )
        return 1
    print(f"litellm {version}: tool calls need no missing package")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
