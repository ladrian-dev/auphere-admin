"""The grader LLM — independent voice that judges the agent's draft.

The pipeline calls :class:`OutcomeGrader.grade` with the rubric body,
the agent's draft response, and the tool envelopes from this turn. The
grader runs Claude Haiku 4.5 (cheap, fast) with a strict JSON schema
and returns a :class:`GraderVerdict`. The grader has NO access to the
agent's system prompt — that anti-correlation is the whole point: if
both the agent and the judge saw the same instructions, they would be
prone to the same blind spots.

Output shape (the grader is instructed to return exactly this JSON):

```json
{
  "<criterion>": "pass|fail",
  ...
  "overall": "pass|fail",
  "feedback": "string when overall=fail; concise + actionable"
}
```

Robustness:

- If the grader returns malformed JSON, the verdict is ``overall=fail``
  with a feedback string explaining the parse error. Conservative
  fallback (Anthropic's "unknown" → fail in our taxonomy).
- If the underlying LLM call raises after all retries, the verdict is
  also ``fail`` (so the customer never receives an un-validated
  response when the operator opted into the guardrail).

The fallback message shown to the customer when the grader exhausts
retries is :data:`GRADER_FALLBACK_RESPONSE` — kept identical across
tenants so we can spot it in traces.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import structlog

from nexus_worker.runtime.llm import LLMProvider

log = structlog.get_logger(__name__)


# Customer-facing message used when the grader's retries are exhausted
# AND the operator has not configured a tenant-specific fallback. The
# wording is deliberately neutral and offers escalation; this is the
# best UX we can give when the agent could not produce a verified
# response in three attempts.
GRADER_FALLBACK_RESPONSE: str = (
    "Disculpa, tuve dificultades para confirmarte esto ahora mismo. "
    "Un miembro del equipo te contactará a la brevedad. "
    "Gracias por tu paciencia."
)

# Max grader retries. The original draft counts as attempt 0; each fail
# triggers one retry of the AGENT (not of the grader). After
# ``MAX_GRADER_RETRIES`` consecutive fails we degrade.
MAX_GRADER_RETRIES: int = 2

# Grader model — cheap + fast. Latency budget: p95 ≤ 800ms for one
# grading pass (§C.6). On retries we accept the doubled latency
# because the alternative is shipping an alucinated answer.
DEFAULT_GRADER_MODEL: str = "anthropic/claude-haiku-4-5"


@dataclass(frozen=True)
class GraderVerdict:
    """The verdict the grader emits per draft response.

    ``criteria`` carries every per-criterion pass/fail the rubric
    declared — kept for traces / Langfuse / future per-criterion
    metrics. ``overall`` is the only field the pipeline acts on
    operationally. ``feedback`` is the string the pipeline injects into
    the agent's retry context when ``overall == "fail"``.
    """

    overall: Literal["pass", "fail"]
    criteria: dict[str, Literal["pass", "fail"]]
    feedback: str
    raw_response: str | None = None  # for debugging — never logged at INFO+


# Strict prompt the grader sees. Kept in code (not in the rubric files)
# so each rubric stays focused on its content. Filled with the rubric
# body verbatim, then the draft response + tool envelopes serialised
# as JSON. We do NOT include the agent's system prompt — anti-correlation.
_GRADER_SYSTEM_TEMPLATE: str = """\
You are an independent QA grader. You DID NOT write the response you
are about to evaluate, and you have not seen the system prompt that
produced it. Your only job is to apply the rubric below to the
candidate response and the tool results that informed it, then return
a verdict as STRICT JSON.

Rules:
- Reply with ONLY the JSON object. No prose before, no prose after.
- For every criterion in the rubric, emit "pass" or "fail".
- The "overall" field is "pass" iff every criterion is "pass".
- The "feedback" field is required and must be a string — empty string
  when overall=pass, a single short actionable sentence when fail.
  No markdown, no quotes, no apologies. Tell the agent what to change.

If you cannot evaluate confidently (rubric ambiguous, missing context),
respond with overall=fail and feedback="Insufficient evidence to grade
confidently — re-check the tool results."

Rubric (verbatim):

{rubric_body}
"""

_GRADER_USER_TEMPLATE: str = """\
Candidate response:

\"\"\"
{draft_response}
\"\"\"

Tool envelopes from this turn (JSON):

{tool_envelopes_json}

Return the verdict JSON now.
"""


class OutcomeGrader:
    """Async grader callable. Wraps a single :class:`LLMProvider`.

    The grader uses ``provider.acomplete`` directly (no ``LLMRouter``):
    we want the grader's retry policy to be DIFFERENT from the main
    router (the grader has no fallback chain to a different model — if
    Haiku can't grade, we treat the verdict as fail and the customer
    gets the neutral message). Going through the router would also
    propagate any future feature-router stack that might not be safe
    to apply to a guardrail call.

    The instance is constructed once at worker startup and reused
    across turns. The provider must be safe under concurrent use (the
    ``LiteLLMProvider`` is).
    """

    def __init__(
        self,
        *,
        provider: LLMProvider,
        model: str = DEFAULT_GRADER_MODEL,
    ) -> None:
        self._provider = provider
        self._model = model

    async def grade(
        self,
        *,
        tenant_id: uuid.UUID,
        intent: str,
        rubric_body: str,
        draft_response: str,
        tool_envelopes: list[dict[str, Any]],
    ) -> GraderVerdict:
        """Run one grading pass and return the verdict.

        On any failure (LLM error, parse error, missing fields) the
        verdict is ``fail`` with a feedback string the pipeline can
        surface either to the agent (for retry) or — at max retries —
        to the operator's alert.
        """
        try:
            tool_json = json.dumps(
                [_envelope_for_grader(e) for e in tool_envelopes],
                ensure_ascii=False,
                default=str,
            )
        except (TypeError, ValueError):
            tool_json = "[]"

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": _GRADER_SYSTEM_TEMPLATE.format(rubric_body=rubric_body),
            },
            {
                "role": "user",
                "content": _GRADER_USER_TEMPLATE.format(
                    draft_response=draft_response,
                    tool_envelopes_json=tool_json,
                ),
            },
        ]
        try:
            raw = await self._provider.acomplete(
                tenant_id=tenant_id,
                role="grader",
                model=self._model,
                messages=messages,
            )
        except Exception as exc:
            log.warning(
                "outcome_grader.llm_failed",
                tenant_id=str(tenant_id),
                intent=intent,
                error=str(exc),
            )
            return GraderVerdict(
                overall="fail",
                criteria={},
                feedback=(
                    "Grader could not be reached — defaulting to fail. "
                    "Manual review recommended."
                ),
            )

        return _parse_verdict(raw)


def _envelope_for_grader(env: dict[str, Any]) -> dict[str, Any]:
    """Reshape a tool envelope for the grader's eyes.

    The grader sees: tool name, status, intent, and a *summary* of the
    result. We do NOT pass the full result through because some
    envelopes carry tens of KB (catalog dumps, memory file contents)
    that would balloon the grader's token cost. The summary is what
    matters: the grader checks *whether* a successful booking happened,
    not the booking's payload.
    """
    summary = env.get("result")
    if isinstance(summary, dict):
        # Keep keys that look load-bearing for grading; drop the rest.
        summary = {
            k: v
            for k, v in summary.items()
            if k in {"status", "id", "command", "path", "summary", "confirmed", "amount"}
        }
    return {
        "tool": env.get("tool"),
        "intent": env.get("intent"),
        "status": env.get("status"),
        "result": summary,
    }


def _parse_verdict(raw: str) -> GraderVerdict:
    """Parse the grader's JSON response into a :class:`GraderVerdict`.

    Robust to:
    - Leading / trailing whitespace.
    - A leading markdown fence (``\\`\\`\\`json``) — some models emit
      it even when told not to.
    - Missing ``overall`` — derived from the per-criterion fields.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Strip a fence: keep what is between the first newline and the
        # last ``` if present.
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return GraderVerdict(
            overall="fail",
            criteria={},
            feedback=f"Grader returned unparseable JSON ({exc.msg}). Treated as fail.",
            raw_response=raw,
        )

    if not isinstance(payload, dict):
        return GraderVerdict(
            overall="fail",
            criteria={},
            feedback="Grader did not return a JSON object. Treated as fail.",
            raw_response=raw,
        )

    # Collect per-criterion verdicts (any key whose value is
    # exactly "pass" or "fail" and is not ``overall`` / ``feedback``).
    criteria: dict[str, Literal["pass", "fail"]] = {}
    for key, value in payload.items():
        if key in ("overall", "feedback"):
            continue
        if value == "pass" or value == "fail":
            criteria[key] = value

    overall_raw = payload.get("overall")
    if overall_raw not in ("pass", "fail"):
        # Derive: pass iff every recorded criterion is pass AND we have
        # at least one. Conservative fallback when the grader omits the
        # field entirely.
        overall: Literal["pass", "fail"] = (
            "pass" if criteria and all(v == "pass" for v in criteria.values()) else "fail"
        )
    else:
        overall = overall_raw

    feedback = payload.get("feedback", "")
    if not isinstance(feedback, str):
        feedback = str(feedback)
    if overall == "fail" and not feedback:
        feedback = (
            "Response failed grading; no feedback provided by grader. "
            "Re-check rubric criteria."
        )

    return GraderVerdict(
        overall=overall,
        criteria=criteria,
        feedback=feedback,
        raw_response=raw,
    )


__all__ = [
    "DEFAULT_GRADER_MODEL",
    "GRADER_FALLBACK_RESPONSE",
    "MAX_GRADER_RETRIES",
    "GraderVerdict",
    "OutcomeGrader",
]
