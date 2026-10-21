"""A LiteLLM call that carries tools must not need a package the image lacks.

LiteLLM 1.106.0 started importing its MCP gateway, and with it the optional
``mcp`` package, on every ``completion()`` that carries ``tools``. The images
resolve dependencies when they are built, so they picked that release up
without ``mcp``: every agent turn with tools died inside the runner, for every
model, logged as «proxy unreachable». ``nexus_api.core.litellm_smoke`` is the
check the Dockerfiles run right after installing, so the next release that
does this fails the build instead of the turn.
"""

from __future__ import annotations

from typing import Any

import litellm
import pytest

from nexus_api.core import litellm_smoke


def test_a_tool_call_needs_no_package_the_environment_lacks() -> None:
    assert litellm_smoke.import_errors_on_tool_call() == []


def test_the_check_reports_an_import_error_hidden_inside_the_litellm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The shape seen in staging on 2026-10-21: LiteLLM wraps the
    # ModuleNotFoundError in its own APIConnectionError.
    async def broken(**_: Any) -> None:
        try:
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        except ModuleNotFoundError as exc:
            raise litellm.APIConnectionError(
                message="No module named 'mcp'", llm_provider="anthropic", model="m"
            ) from exc

    monkeypatch.setattr(litellm, "acompletion", broken)

    errors = litellm_smoke.import_errors_on_tool_call()

    assert [type(e).__name__ for e in errors] == ["ModuleNotFoundError"]
    assert errors[0].name == "mcp"  # type: ignore[attr-defined]


def test_a_plain_connection_failure_is_the_expected_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refused(**_: Any) -> None:
        raise litellm.APIConnectionError(
            message="Connection refused", llm_provider="anthropic", model="m"
        )

    monkeypatch.setattr(litellm, "acompletion", refused)

    assert litellm_smoke.import_errors_on_tool_call() == []


def test_main_exits_non_zero_when_a_tool_call_would_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        litellm_smoke,
        "import_errors_on_tool_call",
        lambda: [ModuleNotFoundError("No module named 'mcp'", name="mcp")],
    )

    assert litellm_smoke.main() == 1
