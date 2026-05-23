"""Unit tests for Fase E — Anthropic MCP connector wiring.

Covers:

- ``build_mcp_extra`` shape: mcp_servers list + ``anthropic-beta`` header.
- Token resolver is called per server and missing credentials skip the
  server cleanly (rather than crashing the turn).
- Beta header merging when stacked on top of a Fase D Skills extra dict
  (BOTH features active in the same turn).
- Feature flag parsing (CSV of UUIDs + garbage tolerance).
- ``mcp_connector_enabled_tenants`` cache semantics — re-read per call.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_worker.mcp_connector import (
    MCP_CONNECTOR_BETA_HEADER_VALUE,
    build_mcp_extra,
    is_mcp_connector_enabled_for,
    mcp_connector_enabled_tenants,
)
from nexus_worker.mcp_connector import _merge_beta_csv as merge_beta_csv

# ── feature flag ────────────────────────────────────────────────────


class TestFeatureFlag:
    def test_empty_env_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEXUS_MCP_CONNECTOR_ENABLED_TENANTS", raising=False)
        assert mcp_connector_enabled_tenants() == frozenset()
        assert not is_mcp_connector_enabled_for(uuid.uuid4())

    def test_csv_of_uuids_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        monkeypatch.setenv("NEXUS_MCP_CONNECTOR_ENABLED_TENANTS", f"{a} , {b}")
        assert mcp_connector_enabled_tenants() == frozenset({a, b})
        assert is_mcp_connector_enabled_for(a)

    def test_bad_uuid_dropped_silently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        good = uuid.uuid4()
        monkeypatch.setenv(
            "NEXUS_MCP_CONNECTOR_ENABLED_TENANTS",
            f"NOT-A-UUID,{good},also-bad",
        )
        assert mcp_connector_enabled_tenants() == frozenset({good})


# ── beta header merge ──────────────────────────────────────────────


class TestMergeBetaCSV:
    def test_appends_unique(self) -> None:
        out = merge_beta_csv("code-execution-2025-08-25", "mcp-client-2025-11-20")
        assert out == "code-execution-2025-08-25,mcp-client-2025-11-20"

    def test_dedupes(self) -> None:
        out = merge_beta_csv(
            "code-execution-2025-08-25,skills-2025-10-02",
            "code-execution-2025-08-25,mcp-client-2025-11-20",
        )
        # Order preserved, duplicates removed.
        assert out == (
            "code-execution-2025-08-25,skills-2025-10-02,mcp-client-2025-11-20"
        )

    def test_empty_inputs(self) -> None:
        assert merge_beta_csv("", "mcp-client-2025-11-20") == "mcp-client-2025-11-20"
        assert merge_beta_csv("mcp-client-2025-11-20", "") == "mcp-client-2025-11-20"
        assert merge_beta_csv("", "") == ""


# ── build_mcp_extra ────────────────────────────────────────────────


class TestBuildMcpExtra:
    async def test_returns_base_when_no_servers(self) -> None:
        async def resolver(_k: str) -> str | None:
            return "tok"

        base = {"anything": 1}
        out = await build_mcp_extra(servers=(), token_resolver=resolver, base_extra=base)
        assert out is base  # passthrough — no copy needed

    async def test_builds_mcp_servers_list(self) -> None:
        async def resolver(key: str) -> str | None:
            return f"token-for-{key}"

        servers = (
            {
                "name": "linear",
                "url": "https://mcp.linear.app/mcp",
                "allowed_tools": ("list_issues", "create_issue"),
                "credential_key": "linear",
            },
        )
        out = await build_mcp_extra(
            servers=servers, token_resolver=resolver, base_extra=None
        )
        assert out is not None
        assert out["mcp_servers"] == [
            {
                "type": "url",
                "url": "https://mcp.linear.app/mcp",
                "name": "linear",
                "tool_configuration": {
                    "allowed_tools": ["list_issues", "create_issue"]
                },
                "authorization_token": "token-for-linear",
            }
        ]
        assert out["extra_headers"]["anthropic-beta"] == MCP_CONNECTOR_BETA_HEADER_VALUE

    async def test_skips_server_with_missing_credential(self) -> None:
        """Missing token → drop the server, don't crash the turn.

        The Composio path can still satisfy the request via the normal
        tool flow, so a missing MCP credential should never break the
        runtime — it just falls back to "no MCP for this server".
        """
        async def resolver(_k: str) -> str | None:
            return None  # always missing

        servers = (
            {
                "name": "github",
                "url": "https://mcp.github.com/mcp",
                "allowed_tools": ("list_repos",),
                "credential_key": "github",
            },
        )
        out = await build_mcp_extra(
            servers=servers, token_resolver=resolver, base_extra=None
        )
        # All servers dropped → result is base_extra (None).
        assert out is None

    async def test_resolver_exception_is_isolated_per_server(self) -> None:
        async def resolver(key: str) -> str | None:
            if key == "broken":
                raise RuntimeError("boom")
            return "ok"

        servers = (
            {
                "name": "broken",
                "url": "https://mcp.example/broken",
                "credential_key": "broken",
            },
            {
                "name": "good",
                "url": "https://mcp.example/good",
                "credential_key": "good",
            },
        )
        out = await build_mcp_extra(
            servers=servers, token_resolver=resolver, base_extra=None
        )
        assert out is not None
        names = [s["name"] for s in out["mcp_servers"]]
        assert names == ["good"]

    async def test_stacks_with_skills_extra_merging_betas(self) -> None:
        """When the caller already built a Skills extra (Fase D),
        ``build_mcp_extra`` must merge the beta-header CSV rather than
        replace it. Both features active in the same turn need both
        betas in the header."""
        async def resolver(_k: str) -> str | None:
            return "tok"

        skills_extra = {
            "container": {
                "skills": [{"type": "custom", "skill_id": "x", "version": "1"}]
            },
            "extra_headers": {
                "anthropic-beta": (
                    "code-execution-2025-08-25,skills-2025-10-02,files-api-2025-04-14"
                )
            },
        }
        servers = (
            {
                "name": "linear",
                "url": "https://mcp.linear.app/mcp",
                "credential_key": "",
            },
        )
        out = await build_mcp_extra(
            servers=servers, token_resolver=resolver, base_extra=skills_extra
        )
        assert out is not None
        beta = out["extra_headers"]["anthropic-beta"]
        # All 4 betas present, in the right order, no dupes.
        assert beta == (
            "code-execution-2025-08-25,skills-2025-10-02,"
            "files-api-2025-04-14,mcp-client-2025-11-20"
        )
        # Skills container survives the merge.
        assert out["container"] == skills_extra["container"]
        # MCP servers attached.
        assert out["mcp_servers"][0]["name"] == "linear"

    async def test_server_without_credential_key_is_still_emitted(self) -> None:
        """Some MCP servers are public / token-less. If ``credential_key``
        is empty, the resolver is NOT called and the server gets emitted
        without ``authorization_token``."""
        called: list[str] = []

        async def resolver(key: str) -> str | None:
            called.append(key)
            return "should-not-be-used"

        servers = (
            {
                "name": "public",
                "url": "https://mcp.example/public",
                "credential_key": "",
            },
        )
        out = await build_mcp_extra(
            servers=servers, token_resolver=resolver, base_extra=None
        )
        assert out is not None
        assert called == []  # resolver not invoked
        assert "authorization_token" not in out["mcp_servers"][0]

    async def test_missing_name_or_url_dropped(self) -> None:
        async def resolver(_k: str) -> str | None:
            return "tok"

        servers = (
            {"name": "", "url": "https://x", "credential_key": ""},
            {"name": "no-url", "url": "", "credential_key": ""},
            {"name": "good", "url": "https://x", "credential_key": ""},
        )
        out = await build_mcp_extra(
            servers=servers, token_resolver=resolver, base_extra=None
        )
        assert out is not None
        assert [s["name"] for s in out["mcp_servers"]] == ["good"]
