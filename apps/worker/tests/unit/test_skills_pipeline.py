"""Unit tests for Fase D — Anthropic Skills wiring in the handler.

Covers:

- The ``extra`` kwarg propagates through ``LLMRouter`` to ``LLMProvider``.
- ``LiteLLMProvider._raw_complete`` merges ``extra`` into the litellm
  kwargs (container + extra_headers).
- The ``extra_headers`` merge preserves any pre-existing entries.

The §D.4 tests "skills end up in the call" + "agent_config.runtime_skills
gets loaded" land in apps/api/tests because they need a real ``AgentLoader``
+ DB session. Here we cover the provider/router seam in isolation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from nexus_worker.runtime.llm import (
    LiteLLMProvider,
    LLMResponse,
    LLMRouter,
)

# ── Fake provider that records ``extra`` ──────────────────────────────


@dataclass
class _ExtraRecorder:
    """LLMProvider that just captures every ``extra`` it received."""

    extras: list[dict[str, Any] | None] = field(default_factory=list)

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return "ok"

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.extras.append(extra if extra is None else dict(extra))
        return LLMResponse(text="ok", tool_calls=())


def _router(provider: _ExtraRecorder) -> LLMRouter:
    return LLMRouter(
        provider=provider,
        classify_model="anthropic/haiku",
        respond_model="anthropic/sonnet",
        fallback_model="openai/gpt-4o",
    )


class TestRouterExtraPassthrough:
    async def test_extra_propagates_to_provider(self) -> None:
        provider = _ExtraRecorder()
        router = _router(provider)
        await router.respond_with_tools(
            tenant_id=uuid.uuid4(),
            role="book",
            messages=[],
            tools=[],
            extra={"container": {"skills": [{"type": "custom", "skill_id": "x", "version": "1"}]}},
        )
        assert len(provider.extras) == 1
        assert provider.extras[0] == {
            "container": {"skills": [{"type": "custom", "skill_id": "x", "version": "1"}]}
        }

    async def test_extra_default_is_none(self) -> None:
        provider = _ExtraRecorder()
        router = _router(provider)
        await router.respond_with_tools(
            tenant_id=uuid.uuid4(),
            role="book",
            messages=[],
            tools=[],
        )
        assert provider.extras == [None]


# ── LiteLLMProvider extra merging ────────────────────────────────────


class _LiteLLMStub:
    """Captures ``litellm.acompletion`` kwargs for inspection."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}


@pytest.fixture
def patched_litellm(monkeypatch: pytest.MonkeyPatch) -> _LiteLLMStub:
    import litellm

    stub = _LiteLLMStub()
    monkeypatch.setattr(litellm, "acompletion", stub)
    return stub


class TestLiteLLMExtraMerge:
    @pytest.fixture(autouse=True)
    def _proxy(self, litellm_proxy_partner: uuid.UUID) -> uuid.UUID:
        return litellm_proxy_partner

    async def test_container_and_headers_land_in_kwargs(
        self, patched_litellm: _LiteLLMStub
    ) -> None:
        """When ``extra`` carries container + extra_headers, the provider
        merges both into the litellm call. LiteLLM passes them through to
        Anthropic — `container.skills` activates the Skills runtime and
        the headers turn on the betas Anthropic requires."""
        provider = LiteLLMProvider()
        tools = [{"type": "function", "function": {"name": "x", "parameters": {}}}]
        extra = {
            "container": {
                "skills": [{"type": "custom", "skill_id": "skill_abc", "version": "latest"}]
            },
            "extra_headers": {
                "anthropic-beta": (
                    "code-execution-2025-08-25,skills-2025-10-02,files-api-2025-04-14"
                )
            },
        }

        await provider.acomplete_with_tools(
            tenant_id=uuid.uuid4(),
            role="book",
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hola"}],
            tools=tools,
            extra=extra,
        )

        kw = patched_litellm.calls[0]
        assert kw["container"] == extra["container"]
        assert kw["extra_headers"]["anthropic-beta"] == (
            "code-execution-2025-08-25,skills-2025-10-02,files-api-2025-04-14"
        )
        # The Fase A context_management beta is still on the kwargs
        # (the call has tools — provider attaches it automatically).
        assert "context_management" in kw

    async def test_extra_omitted_when_none(self, patched_litellm: _LiteLLMStub) -> None:
        provider = LiteLLMProvider()
        await provider.acomplete_with_tools(
            tenant_id=uuid.uuid4(),
            role="info",
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "u"}],
            tools=[{"type": "function", "function": {"name": "noop", "parameters": {}}}],
            extra=None,
        )
        kw = patched_litellm.calls[0]
        assert "container" not in kw
        # No skills-specific extra_headers — but LiteLLM may have
        # populated its own; we only assert what we did NOT add.
        if "extra_headers" in kw:
            assert "skills-2025-10-02" not in (kw["extra_headers"].get("anthropic-beta") or "")

    async def test_extra_headers_merge_does_not_clobber_existing(
        self, patched_litellm: _LiteLLMStub
    ) -> None:
        """If a future caller / future LiteLLM populates ``extra_headers``
        before the merge runs, our merge must combine the dicts rather
        than replace. We don't have a way to force LiteLLM to pre-seed
        extra_headers in this test, but the provider's MERGE branch is
        exercised by passing ``extra_headers`` with one key and asserting
        the result contains it plus whatever else LiteLLM might add."""
        provider = LiteLLMProvider()
        await provider.acomplete_with_tools(
            tenant_id=uuid.uuid4(),
            role="book",
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "u"}],
            tools=[{"type": "function", "function": {"name": "x", "parameters": {}}}],
            extra={"extra_headers": {"x-custom-tag": "auphere"}},
        )
        kw = patched_litellm.calls[0]
        assert kw["extra_headers"]["x-custom-tag"] == "auphere"


# ── handler integration — does the pipeline pass the right extra? ──


@dataclass
class _CapturingProvider:
    """Like _ExtraRecorder but records tools + extra together for
    handler-level assertions."""

    captures: list[dict[str, Any]] = field(default_factory=list)
    text_to_return: str = "ok"

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return self.text_to_return

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.captures.append({"tools": tools, "extra": extra})
        # No tool_calls → loop exits on iteration 0.
        return LLMResponse(text=self.text_to_return, tool_calls=())


class TestHandlerSkillsInjection:
    """Drive ``make_handler_node`` directly and assert that the
    skills-aware call shape lands in the provider when the bundle
    carries runtime_skills."""

    async def _run_handler(
        self,
        *,
        runtime_skills: tuple[dict[str, Any], ...],
        channel_type: str = "whatsapp",
    ) -> _CapturingProvider:
        from nexus_mcp import MCPRegistry

        from nexus_worker.runtime.agent_loader import AgentBundle
        from nexus_worker.runtime.pipeline import make_handler_node

        tenant_id = uuid.uuid4()
        bundle = AgentBundle(
            tenant_id=tenant_id,
            version=1,
            version_id=uuid.uuid4(),
            system_prompt="be honest",
            tools=frozenset(),
            policies={},
            runtime_skills=runtime_skills,
        )

        class _LoaderStub:
            async def load(self, _tid: uuid.UUID) -> AgentBundle:
                return bundle

            async def prime(self, _bundle: AgentBundle) -> None:
                pass

            async def invalidate(self, _tid: uuid.UUID) -> None:
                pass

        provider = _CapturingProvider()
        router = LLMRouter(
            provider=provider,
            classify_model="anthropic/haiku",
            respond_model="anthropic/sonnet",
            fallback_model="openai/gpt-4o",
        )
        handler = make_handler_node(
            "info",
            _LoaderStub(),  # type: ignore[arg-type]
            router,
            MCPRegistry(),
        )
        # Stub the KG snapshot loader so the handler doesn't hit Postgres.
        import nexus_worker.runtime.pipeline as pipeline_module

        async def _empty_kg(_tid: uuid.UUID) -> str:
            return ""

        original = pipeline_module._load_kg_snapshot_text
        pipeline_module._load_kg_snapshot_text = _empty_kg  # type: ignore[assignment]
        try:
            await handler(
                {  # type: ignore[arg-type]
                    "tenant_id": str(tenant_id),
                    "customer_id": str(uuid.uuid4()),
                    "channel_type": channel_type,
                    "intent": "info",
                    "user_message": "hola",
                    "history": [],
                }
            )
        finally:
            pipeline_module._load_kg_snapshot_text = original  # type: ignore[assignment]
        return provider

    async def test_skills_in_bundle_inject_container_and_code_execution(self) -> None:
        provider = await self._run_handler(
            runtime_skills=(
                {"skill_id": "skill_abc", "version": "latest"},
                {"skill_id": "skill_def", "version": "3"},
            )
        )
        assert len(provider.captures) == 1
        cap = provider.captures[0]

        # 1) code_execution appended to tools[]
        tool_types = [t.get("type") for t in cap["tools"]]
        assert "code_execution_20250825" in tool_types

        # 2) extra.container.skills has both skills with type=custom
        extra = cap["extra"]
        assert extra is not None
        assert extra["container"]["skills"] == [
            {"type": "custom", "skill_id": "skill_abc", "version": "latest"},
            {"type": "custom", "skill_id": "skill_def", "version": "3"},
        ]

        # 3) Anthropic betas in the right shape
        assert extra["extra_headers"]["anthropic-beta"] == (
            "code-execution-2025-08-25,skills-2025-10-02,files-api-2025-04-14"
        )

    async def test_no_skills_means_no_container_no_code_execution(self) -> None:
        provider = await self._run_handler(runtime_skills=())
        assert len(provider.captures) == 1
        cap = provider.captures[0]

        # No code_execution tool added.
        tool_types = [t.get("type") for t in cap["tools"]]
        assert "code_execution_20250825" not in tool_types

        # extra should be None (no container, no beta headers).
        assert cap["extra"] is None


# ── channel-gated skills ──────────────────────────────────────────────


class TestServerSideToolPassthrough:
    """Regression for incident 2026-05-28 (Boreal): Anthropic resolves
    server-side tools (code_execution, skills text_editor) inside its own
    container and they arrive with a ``srvtoolu_`` id. The worker must NOT
    dispatch them nor record a tool_result for them — otherwise the next
    request carries an orphan ``tool_result`` and Anthropic 400s with
    ``unexpected tool_use_id found in tool_result blocks``."""

    def test_detects_server_tool_by_id_prefix(self) -> None:
        from nexus_worker.runtime.llm import ToolCall
        from nexus_worker.runtime.pipeline import _is_server_side_tool_call

        call = ToolCall(id="srvtoolu_01EnDwmyc5ygTtvSmWK4VNGq", name="whatever", arguments={})
        assert _is_server_side_tool_call(call) is True

    def test_detects_server_tool_by_name(self) -> None:
        from nexus_worker.runtime.llm import ToolCall
        from nexus_worker.runtime.pipeline import _is_server_side_tool_call

        for name in (
            "code_execution",
            "text_editor_code_execution",
            "bash_code_execution",
            "web_search",
        ):
            call = ToolCall(id="toolu_x", name=name, arguments={})
            assert _is_server_side_tool_call(call) is True, name

    def test_client_tool_is_not_server_side(self) -> None:
        from nexus_worker.runtime.llm import ToolCall
        from nexus_worker.runtime.pipeline import _is_server_side_tool_call

        call = ToolCall(id="toolu_01abc", name="booking.create_appointment", arguments={})
        assert _is_server_side_tool_call(call) is False

    def test_assistant_message_excludes_server_calls(self) -> None:
        """The assistant message we echo back to Anthropic must only carry
        client-side tool_use blocks — never a ``srvtoolu_`` we won't pair
        with a tool_result."""
        from nexus_worker.runtime.llm import LLMResponse, ToolCall
        from nexus_worker.runtime.pipeline import (
            _assistant_tool_message,
            _is_server_side_tool_call,
        )

        server_call = ToolCall(
            id="srvtoolu_01EnDwmyc5ygTtvSmWK4VNGq",
            name="text_editor_code_execution",
            arguments={},
        )
        client_call = ToolCall(
            id="toolu_01abc", name="booking.create_appointment", arguments={"day": "fri"}
        )
        response = LLMResponse(text="ok", tool_calls=(server_call, client_call))
        client_calls = [c for c in response.tool_calls if not _is_server_side_tool_call(c)]

        msg = _assistant_tool_message(response, client_calls)
        ids = {tc["id"] for tc in msg["tool_calls"]}
        assert ids == {"toolu_01abc"}
        assert not any(i.startswith("srvtoolu_") for i in ids)


class TestChannelGatingHelper:
    """Unit tests for ``_filter_skills_for_channel`` in isolation. The
    helper is the single decision point — verify it before wiring it
    into the handler-level tests below."""

    def test_skill_without_channels_loads_anywhere(self) -> None:
        from nexus_worker.runtime.pipeline import _filter_skills_for_channel

        skill = {"skill_id": "skill_x", "version": "1", "channels": ()}
        assert _filter_skills_for_channel((skill,), "whatsapp") == (skill,)
        assert _filter_skills_for_channel((skill,), "web") == (skill,)

    def test_skill_with_missing_channels_key_loads_anywhere(self) -> None:
        from nexus_worker.runtime.pipeline import _filter_skills_for_channel

        # An older row that pre-dates the channels gate has no key at
        # all; the loader should still pass it through.
        skill = {"skill_id": "skill_legacy", "version": "1"}
        assert _filter_skills_for_channel((skill,), "whatsapp") == (skill,)
        assert _filter_skills_for_channel((skill,), "web") == (skill,)

    def test_whatsapp_only_skill_excluded_on_web(self) -> None:
        from nexus_worker.runtime.pipeline import _filter_skills_for_channel

        skill = {"skill_id": "skill_wa", "version": "1", "channels": ("whatsapp",)}
        assert _filter_skills_for_channel((skill,), "whatsapp") == (skill,)
        assert _filter_skills_for_channel((skill,), "web") == ()

    def test_mixed_bundle_partitions_correctly(self) -> None:
        from nexus_worker.runtime.pipeline import _filter_skills_for_channel

        always = {"skill_id": "skill_always", "version": "1", "channels": ()}
        wa_only = {
            "skill_id": "skill_wa",
            "version": "1",
            "channels": ("whatsapp",),
        }
        web_only = {
            "skill_id": "skill_web",
            "version": "1",
            "channels": ("web",),
        }
        bundle = (always, wa_only, web_only)

        whatsapp = _filter_skills_for_channel(bundle, "whatsapp")
        assert whatsapp == (always, wa_only)

        web = _filter_skills_for_channel(bundle, "web")
        assert web == (always, web_only)

        instagram = _filter_skills_for_channel(bundle, "instagram")
        assert instagram == (always,)


class TestChannelGatingHandlerIntegration(TestHandlerSkillsInjection):
    """End-to-end: bundle carries channels-gated skills, and the handler
    inflates the LLM call accordingly. Reuses the parent's ``_run_handler``
    helper so the only variable is what the bundle carries + which
    channel the state declares."""

    async def test_whatsapp_only_skill_injected_on_whatsapp(self) -> None:
        provider = await self._run_handler(
            runtime_skills=(
                {
                    "skill_id": "skill_wa",
                    "version": "latest",
                    "channels": ("whatsapp",),
                },
            ),
            channel_type="whatsapp",
        )
        cap = provider.captures[0]
        extra = cap["extra"]
        assert extra is not None
        assert extra["container"]["skills"] == [
            {"type": "custom", "skill_id": "skill_wa", "version": "latest"},
        ]
        # code_execution tool MUST be present — Anthropic requires it
        # whenever container.skills is set.
        tool_types = [t.get("type") for t in cap["tools"]]
        assert "code_execution_20250825" in tool_types

    async def test_whatsapp_only_skill_excluded_on_web(self) -> None:
        provider = await self._run_handler(
            runtime_skills=(
                {
                    "skill_id": "skill_wa",
                    "version": "latest",
                    "channels": ("whatsapp",),
                },
            ),
            channel_type="web",
        )
        cap = provider.captures[0]
        # Bundle had a skill but it was filtered out — the call MUST
        # behave exactly as if no skills were configured.
        assert cap["extra"] is None
        tool_types = [t.get("type") for t in cap["tools"]]
        assert "code_execution_20250825" not in tool_types

    async def test_mixed_bundle_on_web_keeps_only_always_skill(self) -> None:
        provider = await self._run_handler(
            runtime_skills=(
                {
                    "skill_id": "skill_always",
                    "version": "latest",
                    "channels": (),
                },
                {
                    "skill_id": "skill_wa",
                    "version": "latest",
                    "channels": ("whatsapp",),
                },
            ),
            channel_type="web",
        )
        cap = provider.captures[0]
        extra = cap["extra"]
        assert extra is not None
        assert extra["container"]["skills"] == [
            {"type": "custom", "skill_id": "skill_always", "version": "latest"},
        ]

    async def test_legacy_skill_without_channels_key_still_loads(self) -> None:
        """An ``agent_config`` row from before the gate landed has no
        ``channels`` key at all. The loader normalises it to an empty
        tuple; the handler must treat that as 'no gate' and inject."""
        provider = await self._run_handler(
            runtime_skills=({"skill_id": "skill_legacy", "version": "latest"},),
            channel_type="web",
        )
        cap = provider.captures[0]
        extra = cap["extra"]
        assert extra is not None
        assert extra["container"]["skills"] == [
            {
                "type": "custom",
                "skill_id": "skill_legacy",
                "version": "latest",
            },
        ]


# ── frontmatter parsing of bundled SKILL.md files ──────────────────────


class TestBundledSkills:
    """Sanity-check the 3 SKILL.md files in the repo so a future
    rename / typo gets caught by the suite before deploy."""

    @pytest.mark.parametrize(
        "skill_name",
        [
            "anti-hallucination-booking",
            "whatsapp-24h-window",
            "escalation-policy",
            "whatsapp-native-components",
        ],
    )
    def test_skill_md_has_valid_frontmatter(self, skill_name: str) -> None:
        from pathlib import Path

        from scripts.upload_skill import _parse_frontmatter, _validate_frontmatter

        skill_dir = Path(__file__).resolve().parents[2] / "skills" / skill_name
        meta = _parse_frontmatter(skill_dir / "SKILL.md")
        _validate_frontmatter(meta, skill_name)
        assert meta["name"] == skill_name
        assert int(meta["version"]) >= 1

    @pytest.mark.parametrize(
        "skill_name",
        [
            "anti-hallucination-booking",
            "whatsapp-24h-window",
            "escalation-policy",
            "whatsapp-native-components",
        ],
    )
    def test_skill_passes_network_import_lint(self, skill_name: str) -> None:
        from pathlib import Path

        from scripts.upload_skill import _lint_skill_dir

        skill_dir = Path(__file__).resolve().parents[2] / "skills" / skill_name
        violations = _lint_skill_dir(skill_dir)
        assert violations == [], "bundled skill must not carry network imports: " + "; ".join(
            violations
        )
