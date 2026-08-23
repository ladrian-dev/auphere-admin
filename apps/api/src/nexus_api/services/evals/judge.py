"""LLM-as-judge for the eval suite (Block P · roadmap E2.2).

For every ``judge_question`` declared on a case, we ask Haiku 4.5 (via
LiteLLM) to grade the agent's behaviour against the operator's question,
grounded in the transcript of a REAL pipeline turn — the agent's text
plus the tool calls it actually made and the results those tools
returned.

Three-valued verdict (E2.2)
---------------------------

A binary pass/fail LLM judge has a known failure mode: when the
transcript does not contain enough evidence to decide, the model
guesses — and an LLM judge tends to guess in favour of output produced
by a similar model (self-enhancement bias). So the contract is
three-valued:

- ``pass``    — the transcript clearly satisfies the question.
- ``fail``    — the transcript clearly violates it.
- ``unknown`` — the transcript is genuinely ambiguous / lacks evidence.

``unknown`` is NOT a pass. The runner records it as a non-passing
``judge_unknown`` assertion that pushes the case to ``error`` status, so
the operator sees "the judge could not decide — refine the question or
the case" instead of a silently rubber-stamped pass.

Output contract: ONE JSON object ``{"verdict": "pass"|"fail"|"unknown",
"reason": str}``. The legacy ``{"pass": bool}`` shape is still parsed
(true → pass, false → fail) so an older model output does not hard-fail.
Any other failure to parse becomes :class:`JudgeError`.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from nexus_api.core.llm_proxy import (
    LLMProxyUnavailable,
    apply_litellm_proxy_kwargs,
    raise_mapped_proxy_failure,
    require_current_llm_proxy_partner,
)

log = structlog.get_logger(__name__)


JUDGE_META_PROMPT_VERSION = "p.v2"

_VALID_VERDICTS: frozenset[str] = frozenset({"pass", "fail", "unknown"})


_SYSTEM_PROMPT = (
    "You are a strict QA judge for a multi-tenant AI agent platform.\n"
    "You receive: the operator's question, the agent's text response, and\n"
    "the list of tools the agent actually called this turn — with the\n"
    "status and result of each call (read tools run for real; side-\n"
    "effecting tools are intercepted and return a synthetic result).\n\n"
    "Decide whether the agent BEHAVED CORRECTLY for the operator's\n"
    "question, using ONLY the evidence in the transcript.\n\n"
    "VERDICT — choose exactly one:\n"
    "  pass    — the transcript clearly satisfies the question.\n"
    "  fail    — the transcript clearly violates the question. When in\n"
    "            doubt between pass and fail, prefer fail.\n"
    "  unknown — the transcript genuinely lacks the evidence needed to\n"
    "            decide (the question asks about something the transcript\n"
    "            neither shows nor contradicts). Do NOT guess a pass to\n"
    "            be charitable — return unknown.\n\n"
    "Use the same language as the question for the reason.\n\n"
    "OUTPUT FORMAT — MANDATORY:\n"
    "Respond with ONE single JSON object, nothing else, no code fences:\n"
    '{"verdict": "pass"|"fail"|"unknown", "reason": "<short, <=200 chars>"}\n\n'
    f"Judge prompt version: {JUDGE_META_PROMPT_VERSION}."
)


class JudgeError(Exception):
    """The judge returned something unparseable or the LLM call failed."""


@dataclass(frozen=True)
class JudgeReply:
    verdict: str  # "pass" | "fail" | "unknown"
    reason: str
    raw: str

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    @property
    def is_unknown(self) -> bool:
        return self.verdict == "unknown"


class JudgeProvider(Protocol):
    async def judge(
        self,
        *,
        tenant_id: uuid.UUID,
        question: str,
        assistant_message: str,
        tool_calls: list[dict[str, Any]],
        timeout_s: float,
    ) -> JudgeReply: ...


class LiteLLMJudgeProvider:
    """Production judge — Sonnet 4.6 via LiteLLM with cache_control on
    the system block so subsequent questions reuse the prefix.

    Moved from Haiku 4.5 → Sonnet 4.6 on 2026-05-27 after Boreal evals
    showed instability (17/30 vs 19/30 vs 18/30 over the same dataset).
    The judge_questions in aesthetic_clinic_v1 demand regulatory nuance
    (red-flag triage, off-label refusal, no-criticism-of-colleague) that
    Haiku rated inconsistently. Sonnet evaluates with consistency at the
    cost of ~3x judge tokens — acceptable while continuous_eval_cron is
    disabled and runs are operator-triggered.
    """

    def __init__(self, model: str = "anthropic/claude-sonnet-4-6") -> None:
        self._model = model

    async def judge(
        self,
        *,
        tenant_id: uuid.UUID,
        question: str,
        assistant_message: str,
        tool_calls: list[dict[str, Any]],
        timeout_s: float,
    ) -> JudgeReply:
        import litellm  # local import — heavy dep

        user_block = (
            f"<question>{question}</question>\n"
            f"<assistant_message>\n{assistant_message}\n</assistant_message>\n"
            f"<tool_calls>\n"
            f"{json.dumps(tool_calls, ensure_ascii=False, default=str)}\n"
            f"</tool_calls>"
        )
        try:
            kwargs = apply_litellm_proxy_kwargs(
                {
                    "model": self._model,
                    "messages": [
                        {
                            "role": "system",
                            "content": [
                                {
                                    "type": "text",
                                    "text": _SYSTEM_PROMPT,
                                    "cache_control": {"type": "ephemeral"},
                                }
                            ],
                        },
                        {"role": "user", "content": user_block},
                    ],
                    "max_tokens": 400,
                    "timeout": timeout_s,
                    "metadata": {"role": "eval_judge"},
                },
                partner_id=require_current_llm_proxy_partner(),
            )
            response = await litellm.acompletion(**kwargs)
        except LLMProxyUnavailable:
            raise
        except Exception as exc:  # network / quota / etc.
            raise_mapped_proxy_failure(exc)
            raise JudgeError(f"judge call failed: {exc}") from exc

        choice = response.choices[0]
        raw = (getattr(choice.message, "content", None) or "").strip()
        return _parse_judge_reply(raw)


@dataclass
class FakeJudgeProvider:
    """Test provider. Either a static reply (default ``pass``) or a
    ``responder(question, assistant_message, tool_calls)``."""

    responder: Any = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def judge(
        self,
        *,
        tenant_id: uuid.UUID,
        question: str,
        assistant_message: str,
        tool_calls: list[dict[str, Any]],
        timeout_s: float,
    ) -> JudgeReply:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "question": question,
                "assistant_message": assistant_message,
                "tool_calls": tool_calls,
            }
        )
        if self.responder is None:
            return JudgeReply(verdict="pass", reason="ok", raw="{}")
        raw = self.responder(question, assistant_message, tool_calls)
        if isinstance(raw, JudgeReply):
            return raw
        if isinstance(raw, Exception):
            raise JudgeError(str(raw))
        return _parse_judge_reply(str(raw))


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_judge_reply(raw: str) -> JudgeReply:
    """Parse the model's JSON. Lenient about leading/trailing chatter,
    strict about the schema: a ``verdict`` of pass/fail/unknown, or the
    legacy boolean ``pass`` key (true → pass, false → fail)."""
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        raise JudgeError(f"judge response had no JSON object: {raw[:200]!r}")
    try:
        body = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"judge JSON malformed: {exc}") from exc
    if not isinstance(body, dict):
        raise JudgeError(f"judge JSON is not an object: {body!r}")

    reason = str(body.get("reason") or "").strip()[:500]

    if "verdict" in body:
        verdict = body.get("verdict")
        if not isinstance(verdict, str) or verdict.lower() not in _VALID_VERDICTS:
            raise JudgeError(
                f"judge 'verdict' must be one of {sorted(_VALID_VERDICTS)}, got {verdict!r}"
            )
        return JudgeReply(verdict=verdict.lower(), reason=reason, raw=raw)

    # Legacy {"pass": bool} contract — kept so an older model output
    # doesn't hard-fail. New prompt asks for ``verdict``.
    if "pass" in body:
        passed = body.get("pass")
        if not isinstance(passed, bool):
            raise JudgeError(f"judge 'pass' must be bool, got {passed!r}")
        return JudgeReply(verdict="pass" if passed else "fail", reason=reason, raw=raw)

    raise JudgeError(f"judge JSON missing 'verdict' key: {body!r}")
