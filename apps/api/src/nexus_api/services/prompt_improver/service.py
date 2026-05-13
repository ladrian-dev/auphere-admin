"""Block N — prompt improver service.

The endpoint hands us a draft + a mode + the tenant's agent context.
We build the meta-prompt, call the LLM, parse the XML response and
return a structured result the panel can render in a diff view.

The LLM call is abstracted behind :class:`PromptImproverProvider` so
tests can pin behaviour without touching litellm.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from nexus_api.services.prompt_improver.meta_prompt import (
    META_PROMPT_VERSION,
    SUPPORTED_MODES,
    build_meta_messages,
)

log = structlog.get_logger(__name__)


# ── public dataclasses ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentContext:
    """Everything the meta-prompt knows about the tenant.

    Built from the tenant + agent_config in the admin endpoint. Pure
    data — no DB session leaks down into the service layer.
    """

    tenant_name: str
    use_case: str  # vertical / seed_template_ref
    channel: str  # whatsapp | voice | web
    language: str  # es-VE / es-CL / en-US / ...
    available_tools: tuple[str, ...] = ()
    business_hours: str | None = None
    agent_name: str | None = None
    timezone: str | None = None
    market: str | None = None

    def to_block(self) -> dict[str, object]:
        return {
            "tenant_name": self.tenant_name,
            "use_case": self.use_case,
            "channel": self.channel,
            "language": self.language,
            "agent_name": self.agent_name,
            "timezone": self.timezone,
            "market": self.market,
            "business_hours": self.business_hours,
            "available_tools": list(self.available_tools),
        }


@dataclass(frozen=True)
class ImproveResult:
    improved_prompt: str
    summary_of_changes: tuple[str, ...]
    mode: str
    meta_prompt_version: str
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    raw_response: str = field(repr=False)


# ── errors ──────────────────────────────────────────────────────────────────


class PromptImproverError(Exception):
    """Base error class — endpoint maps to HTTP 502 unless a subtype
    declares its own mapping."""


class PromptTooLongError(PromptImproverError):
    """Pre-LLM guard: the draft exceeds ``improve_prompt_max_input_chars``."""


class MalformedResponseError(PromptImproverError):
    """The model returned something we cannot parse. The raw response is
    surfaced verbatim in the HTTPException so the operator can retry."""

    def __init__(self, raw: str, reason: str) -> None:
        super().__init__(reason)
        self.raw = raw
        self.reason = reason


# ── provider protocol + impls ───────────────────────────────────────────────


@dataclass(frozen=True)
class _LLMReply:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None


class PromptImproverProvider(Protocol):
    """Thin shim around the LLM. Returns text + usage."""

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        timeout_s: float,
    ) -> _LLMReply: ...


class LiteLLMPromptImproverProvider:
    """Production provider — calls Anthropic (or OpenAI fallback) via
    LiteLLM. The system message in :func:`build_meta_messages` already
    carries ``cache_control={"type": "ephemeral"}`` so we get the
    Anthropic prompt-cache savings on the second call of an iteration."""

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        timeout_s: float,
    ) -> _LLMReply:
        import litellm  # local import — heavy dep

        response = await litellm.acompletion(
            model=model,
            messages=messages,
            max_tokens=max_output_tokens,
            timeout=timeout_s,
            metadata={"tenant_id": str(tenant_id), "role": "improve_prompt"},
        )
        # LiteLLM normalises Anthropic + OpenAI usage into the OpenAI
        # shape: ``choices[0].message.content`` + ``usage.prompt_tokens``
        # + ``usage.completion_tokens``. For Anthropic, cached input
        # tokens land in ``usage.prompt_tokens_details.cached_tokens``.
        choice = response.choices[0]
        text = getattr(choice.message, "content", None) or ""
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached = getattr(details, "cached_tokens", None) if details else None
        return _LLMReply(
            text=str(text),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
        )


@dataclass
class FakePromptImproverProvider:
    """Test provider — scripted responses.

    Tests register a ``responder(messages, mode) -> str`` callback to
    return whatever XML they need. Default returns a deterministic
    well-formed XML so the contract tests can verify the parser without
    each test having to script the response.
    """

    responder: Any = None  # callable(messages, mode) -> str
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        model: str,
        messages: list[dict[str, Any]],
        max_output_tokens: int,
        timeout_s: float,
    ) -> _LLMReply:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "model": model,
                "messages": messages,
                "max_output_tokens": max_output_tokens,
                "timeout_s": timeout_s,
            }
        )
        if self.responder is None:
            text = (
                "<improved_prompt>\n"
                "Sos el asistente de Test Tenant. Respondé corto y claro.\n"
                "</improved_prompt>\n"
                "<summary>\n"
                "- Reescribí el prompt con tono directo.\n"
                "- Añadí una instrucción sobre cómo manejar fechas ambiguas.\n"
                "- Aclaré la política de cancelación.\n"
                "</summary>"
            )
        else:
            text = self.responder(messages, "general")
        return _LLMReply(
            text=text,
            input_tokens=3120,
            output_tokens=820,
            cached_input_tokens=0,
        )


# ── parsing ─────────────────────────────────────────────────────────────────

_PROMPT_RE = re.compile(r"<improved_prompt>\s*(?P<body>.*?)\s*</improved_prompt>", re.DOTALL)
_SUMMARY_RE = re.compile(r"<summary>\s*(?P<body>.*?)\s*</summary>", re.DOTALL)
_BULLET_RE = re.compile(r"^\s*[-•*]\s*(.+?)\s*$", re.MULTILINE)


def _parse_response(raw: str) -> tuple[str, tuple[str, ...]]:
    prompt_match = _PROMPT_RE.search(raw)
    if prompt_match is None:
        raise MalformedResponseError(
            raw=raw,
            reason="missing <improved_prompt> block",
        )
    improved = prompt_match.group("body").strip()
    if not improved:
        raise MalformedResponseError(raw=raw, reason="<improved_prompt> block was empty")

    summary_match = _SUMMARY_RE.search(raw)
    if summary_match is None:
        bullets: tuple[str, ...] = ()
    else:
        bullets = tuple(
            m.group(1).strip() for m in _BULLET_RE.finditer(summary_match.group("body"))
        )
    return improved, bullets


# ── orchestrator ────────────────────────────────────────────────────────────


async def improve_prompt(
    *,
    tenant_id: uuid.UUID,
    draft_prompt: str,
    mode: str,
    feedback: str | None,
    context: AgentContext,
    provider: PromptImproverProvider,
    model: str,
    timeout_s: float,
    max_input_chars: int,
    max_output_tokens: int,
) -> ImproveResult:
    """The single public entrypoint. Validation, meta-prompt build,
    LLM call, response parse — in that order."""
    draft = draft_prompt.strip()
    if not draft:
        raise PromptImproverError("draft_prompt is empty")
    if len(draft) > max_input_chars:
        raise PromptTooLongError(
            f"draft is {len(draft)} chars; cap is {max_input_chars}. "
            "Trim the prompt or split it before improving."
        )
    if mode not in SUPPORTED_MODES:
        raise PromptImproverError(f"unsupported mode {mode!r}; supported: {SUPPORTED_MODES}")

    messages = build_meta_messages(
        draft_prompt=draft,
        mode=mode,
        feedback=feedback,
        context=context.to_block(),
    )
    started = time.perf_counter()
    reply = await provider.acomplete(
        tenant_id=tenant_id,
        model=model,
        messages=messages,
        max_output_tokens=max_output_tokens,
        timeout_s=timeout_s,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    improved, bullets = _parse_response(reply.text)

    log.info(
        "prompt_improver.complete",
        tenant_id=str(tenant_id),
        mode=mode,
        meta_prompt_version=META_PROMPT_VERSION,
        model=model,
        latency_ms=latency_ms,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        cached_input_tokens=reply.cached_input_tokens,
        input_chars=len(draft),
        output_chars=len(improved),
        bullets=len(bullets),
    )

    return ImproveResult(
        improved_prompt=improved,
        summary_of_changes=bullets,
        mode=mode,
        meta_prompt_version=META_PROMPT_VERSION,
        model=model,
        latency_ms=latency_ms,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        cached_input_tokens=reply.cached_input_tokens,
        raw_response=reply.text,
    )
