"""/cso 2026-11-20 (T093): lo que solo entiende Anthropic no sale nunca hacia OpenAI.

``mcp_servers`` lleva el token del servidor MCP del cliente y ``container`` sus Skills.
LiteLLM 1.83.14 los mete en el cuerpo de ``/v1/chat/completions`` si llegan como kwargs
(``add_provider_specific_params_to_optional_params``): el token viajaría a OpenAI. Se quitan
en las dos puertas: el perfil de la llamada (``respond_hop_extra``) y la última antes de
salir (``_drop_openai_unsupported``).
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_worker.runtime.llm import _drop_openai_unsupported, respond_hop_extra

MCP_EXTRA: dict[str, Any] = {
    "mcp_servers": [
        {"type": "url", "url": "https://mcp.example", "name": "c", "authorization_token": "tok"}
    ],
    "container": {"skills": [{"type": "custom", "skill_id": "s1"}]},
    "extra_headers": {"anthropic-beta": "mcp-client-2025-04-04"},
}


@pytest.mark.parametrize(
    "model", ["openai/gpt-5.6-sol", "openai/gpt-5.6-terra", "openai/gpt-5.6-luna"]
)
def test_the_profile_drops_mcp_and_skills_toward_openai(model: str) -> None:
    extra = respond_hop_extra(model, MCP_EXTRA, tools=True) or {}
    assert "mcp_servers" not in extra and "container" not in extra
    assert "tok" not in repr(extra)


def test_the_last_gate_drops_them_too() -> None:
    kwargs: dict[str, Any] = {"model": "openai/gpt-5.6-luna", "messages": [], **MCP_EXTRA}
    out = _drop_openai_unsupported(kwargs)
    assert "mcp_servers" not in out and "container" not in out
    assert "tok" not in repr(out)


def test_anthropic_keeps_them() -> None:
    extra = respond_hop_extra("anthropic/claude-sonnet-5-5", MCP_EXTRA, tools=True) or {}
    assert extra["mcp_servers"][0]["authorization_token"] == "tok"
    assert "container" in extra
