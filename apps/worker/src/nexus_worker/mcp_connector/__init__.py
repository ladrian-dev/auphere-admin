"""Anthropic MCP connector — Fase E of claude-platform-integration.

Anthropic exposes a beta (``mcp-client-2025-11-20``) that lets the
Messages API talk to an external MCP server directly — no proxy, no
Composio-style adapter. This module wires that beta into the Nexus
runtime via the ``extra`` kwarg added to ``LLMProvider`` in Fase D.

This is the *exploratory* phase. The infrastructure is here; the
real comparison (latency, error rate, ergonomics vs. Composio) needs
a tenant with real OAuth credentials, which is operational work that
sits outside this code.

Activation is per ``agent_config`` via ``runtime_mcp_connector BOOLEAN``
(migration 0035) AND a non-empty ``runtime_mcp_servers JSONB``. The
handler enforces both: the boolean is the kill switch for the module,
the JSONB lists which servers to attach when the kill switch is up.

Public surface:

- :func:`build_mcp_extra` — given a list of server configs + a token
  resolver, returns the ``extra`` dict to pass to
  ``LLMRouter.respond_with_tools``.
- :data:`MCP_CONNECTOR_BETA_HEADER_VALUE` — the beta header to emit.

Architectural notes:

- OAuth credentials stay in Composio. The ``credential_key`` field in
  each server config points to a row in ``tenant_credentials``; the
  worker reads it per-turn (no caching in this module to keep token
  rotation immediate). If the credential is missing or the
  ``needs_reauth`` flag is set, the server entry is silently skipped
  rather than failing the turn — the Composio-backed path can still
  satisfy the request via the normal tool flow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# The MCP connector beta header. Pulled into a constant so a future
# bump (e.g. ``mcp-client-2026-XX``) is a single-file change.
MCP_CONNECTOR_BETA_HEADER_VALUE: str = "mcp-client-2025-11-20"


# Token resolver protocol — the pipeline passes an async callable that
# reads ``tenant_credentials`` and returns the OAuth bearer string, or
# ``None`` if it cannot. We isolate it as a callable (not a hard import
# of the repo) so tests can stub it without DB access.
TokenResolver = Callable[[str], Awaitable[str | None]]


async def build_mcp_extra(
    *,
    servers: tuple[dict[str, Any], ...],
    token_resolver: TokenResolver,
    base_extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build the ``extra`` dict that activates MCP connector on a call.

    Returns ``None`` when the result would be a no-op (no servers, all
    credentials missing). When non-None it has the shape:

        {
            "mcp_servers": [...AnthropicMcpServerTool...],
            "extra_headers": {"anthropic-beta": "mcp-client-2025-11-20"},
        }

    ``base_extra`` lets the caller stack this on top of an existing
    Fase D Skills extra dict — the headers are merged (combined CSV)
    rather than overwritten. That keeps Fase D and Fase E compatible
    in the same turn.
    """
    if not servers:
        return base_extra

    mcp_servers: list[dict[str, Any]] = []
    for cfg in servers:
        name = str(cfg.get("name") or "").strip()
        url = str(cfg.get("url") or "").strip()
        if not name or not url:
            continue
        credential_key = str(cfg.get("credential_key") or "").strip()
        token: str | None = None
        if credential_key:
            try:
                token = await token_resolver(credential_key)
            except Exception as exc:
                # A broken resolver should not crash the turn — log and
                # skip this server. The model still has the rest of its
                # tools available via the Composio path.
                log.warning(
                    "mcp_connector.token_resolution_failed",
                    server_name=name,
                    credential_key=credential_key,
                    error=str(exc),
                )
                continue
        if credential_key and not token:
            log.info(
                "mcp_connector.skipping_server_without_credential",
                server_name=name,
                credential_key=credential_key,
            )
            continue

        server: dict[str, Any] = {"type": "url", "url": url, "name": name}
        allowed_tools = tuple(cfg.get("allowed_tools") or ())
        if allowed_tools:
            server["tool_configuration"] = {"allowed_tools": list(allowed_tools)}
        if token:
            server["authorization_token"] = token
        mcp_servers.append(server)

    if not mcp_servers:
        return base_extra

    # Build the new ``extra``. If the caller stacked us on top of an
    # existing extra dict (e.g. Fase D Skills), merge the beta headers
    # CSV instead of clobbering. The Anthropic adapter inside LiteLLM
    # treats ``anthropic-beta`` as a comma-separated list, so simple
    # concatenation works.
    out: dict[str, Any] = dict(base_extra or {})
    out["mcp_servers"] = mcp_servers
    existing_headers = dict(out.get("extra_headers") or {})
    existing_beta = existing_headers.get("anthropic-beta", "")
    merged_beta = _merge_beta_csv(existing_beta, MCP_CONNECTOR_BETA_HEADER_VALUE)
    existing_headers["anthropic-beta"] = merged_beta
    out["extra_headers"] = existing_headers
    return out


def _merge_beta_csv(existing: str, *additions: str) -> str:
    """Combine two CSV beta-header values, preserving order + uniqueness.

    Anthropic accepts repeated betas as one comma-separated header. We
    deduplicate so ``code-execution-2025-08-25,mcp-client-2025-11-20``
    stays clean across stacked extras (Fase D + Fase E in the same
    turn).
    """
    seen: list[str] = []
    sources = [existing, *additions]
    for src in sources:
        for token in (t.strip() for t in src.split(",")):
            if token and token not in seen:
                seen.append(token)
    return ",".join(seen)


__all__ = [
    "MCP_CONNECTOR_BETA_HEADER_VALUE",
    "build_mcp_extra",
]
