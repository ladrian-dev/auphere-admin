"""LLM-as-judge for the eval suite (Block P).

For every ``judge_question`` declared on a case, we ask Haiku 4.5
(via LiteLLM) a yes/no question grounded in the transcript. Haiku is
~20x cheaper than Sonnet and entirely sufficient for binary
verification.

Output contract: the model must return JSON ``{"pass": bool, "reason":
str}``. We pin the response shape with a meta-prompt and parse with
``json.loads``. Any failure to parse becomes
:class:`JudgeError` — the runner records the assertion as ``error``
(distinct from ``pass``/``fail``) so the operator notices and refines
the question.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)


JUDGE_META_PROMPT_VERSION = "p.v1"


_SYSTEM_PROMPT = (
    "You are a strict QA judge for a multi-tenant AI agent platform.\n"
    "You receive: the operator's question, the agent's text response, and\n"
    "the list of tools the agent wanted to call (the sandbox doesn't run\n"
    "them, but you see what was requested).\n\n"
    "Decide if the agent BEHAVED CORRECTLY per the operator's question.\n"
    "Be strict — when in doubt, fail. Use the same language as the\n"
    "question for the reason.\n\n"
    "OUTPUT FORMAT — MANDATORY:\n"
    "Respond with ONE single JSON object, nothing else, no code fences:\n"
    '{"pass": true|false, "reason": "<short reason, <=200 chars>"}\n\n'
    f"Judge prompt version: {JUDGE_META_PROMPT_VERSION}."
)


class JudgeError(Exception):
    """The judge returned something unparseable or the LLM call failed."""


@dataclass(frozen=True)
class JudgeReply:
    passed: bool
    reason: str
    raw: str


class JudgeProvider(Protocol):
    async def judge(
        self,
        *,
        tenant_id: uuid.UUID,
        question: str,
        assistant_message: str,
        planned_tool_calls: list[dict[str, Any]],
        timeout_s: float,
    ) -> JudgeReply: ...


class LiteLLMJudgeProvider:
    """Production judge — Haiku 4.5 via LiteLLM with cache_control on
    the system block so subsequent questions reuse the prefix."""

    def __init__(self, model: str = "anthropic/claude-haiku-4-5") -> None:
        self._model = model

    async def judge(
        self,
        *,
        tenant_id: uuid.UUID,
        question: str,
        assistant_message: str,
        planned_tool_calls: list[dict[str, Any]],
        timeout_s: float,
    ) -> JudgeReply:
        import litellm  # local import — heavy dep

        user_block = (
            f"<question>{question}</question>\n"
            f"<assistant_message>\n{assistant_message}\n</assistant_message>\n"
            f"<planned_tool_calls>\n"
            f"{json.dumps(planned_tool_calls, ensure_ascii=False)}\n"
            f"</planned_tool_calls>"
        )
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=[
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
                max_tokens=400,
                timeout=timeout_s,
                metadata={
                    "tenant_id": str(tenant_id),
                    "role": "eval_judge",
                },
            )
        except Exception as exc:  # network / quota / etc.
            raise JudgeError(f"judge call failed: {exc}") from exc

        choice = response.choices[0]
        raw = (getattr(choice.message, "content", None) or "").strip()
        return _parse_judge_reply(raw)


@dataclass
class FakeJudgeProvider:
    """Test provider. Either a static reply (default ``pass``) or a
    ``responder(question, assistant_message, planned_tool_calls)``."""

    responder: Any = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def judge(
        self,
        *,
        tenant_id: uuid.UUID,
        question: str,
        assistant_message: str,
        planned_tool_calls: list[dict[str, Any]],
        timeout_s: float,
    ) -> JudgeReply:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "question": question,
                "assistant_message": assistant_message,
                "planned_tool_calls": planned_tool_calls,
            }
        )
        if self.responder is None:
            return JudgeReply(passed=True, reason="ok", raw="{}")
        raw = self.responder(question, assistant_message, planned_tool_calls)
        if isinstance(raw, JudgeReply):
            return raw
        if isinstance(raw, Exception):
            raise JudgeError(str(raw))
        return _parse_judge_reply(str(raw))


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_judge_reply(raw: str) -> JudgeReply:
    """Parse the model's JSON. We're lenient about leading/trailing
    chatter but strict about the schema: must have a boolean ``pass``."""
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        raise JudgeError(f"judge response had no JSON object: {raw[:200]!r}")
    try:
        body = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"judge JSON malformed: {exc}") from exc
    if not isinstance(body, dict) or "pass" not in body:
        raise JudgeError(f"judge JSON missing 'pass' key: {body!r}")
    passed = body.get("pass")
    if not isinstance(passed, bool):
        raise JudgeError(f"judge 'pass' must be bool, got {passed!r}")
    reason = str(body.get("reason") or "").strip()[:500]
    return JudgeReply(passed=passed, reason=reason, raw=raw)
