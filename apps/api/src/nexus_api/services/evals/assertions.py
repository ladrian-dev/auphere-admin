"""Deterministic checks for the eval suite (Block P).

The assertion DSL is intentionally narrow:

- ``must_contain``         — every string must appear in the agent's text.
- ``must_not_contain``     — none of these may appear.
- ``expected_tools_called`` — every tool name must show up in
                              ``planned_tool_calls``. Order doesn't matter.
- ``tools_must_not_call``  — none of these may appear.
- ``must_emit_text``       — when ``True``, ``assistant_message`` must be
                              non-empty after strip.
- ``judge_questions``      — each yes/no question is sent to an LLM judge;
                              ``yes`` means pass. Handled outside this
                              module — see :mod:`runner`.

Cases must declare at least one assertion (deterministic OR judge) — an
empty assertions object is rejected at schema-validation time so the
runner never wastes an LLM call on a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class AssertionValidationError(ValueError):
    """The case's ``assertions`` payload is empty or malformed."""


@dataclass(frozen=True)
class AssertionResult:
    kind: str
    passed: bool
    detail: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "pass": self.passed,
            "detail": self.detail,
            "payload": self.payload,
        }


_KNOWN_KEYS: frozenset[str] = frozenset(
    {
        "must_contain",
        "must_not_contain",
        "expected_tools_called",
        "tools_must_not_call",
        "must_emit_text",
        "judge_questions",
    }
)


def validate_assertions(assertions: dict[str, Any]) -> None:
    """Raise :class:`AssertionValidationError` if the case payload is
    unusable. Called by the endpoint *before* persistence so a bad case
    never reaches the runner."""
    if not isinstance(assertions, dict):
        raise AssertionValidationError("assertions must be an object")

    extra = set(assertions) - _KNOWN_KEYS
    if extra:
        raise AssertionValidationError(f"unknown assertion keys: {sorted(extra)}")

    has_anything = False
    for key in ("must_contain", "must_not_contain"):
        v = assertions.get(key)
        if v is None:
            continue
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise AssertionValidationError(f"{key} must be a list of strings")
        if v:
            has_anything = True

    for key in ("expected_tools_called", "tools_must_not_call"):
        v = assertions.get(key)
        if v is None:
            continue
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise AssertionValidationError(f"{key} must be a list of tool names")
        if v:
            has_anything = True

    must_emit = assertions.get("must_emit_text")
    if must_emit is not None:
        if not isinstance(must_emit, bool):
            raise AssertionValidationError("must_emit_text must be a bool")
        has_anything = has_anything or must_emit

    judge = assertions.get("judge_questions")
    if judge is not None:
        if not isinstance(judge, list) or not all(isinstance(x, str) for x in judge):
            raise AssertionValidationError("judge_questions must be a list of strings")
        if judge:
            has_anything = True

    if not has_anything:
        raise AssertionValidationError("case must declare at least one non-empty assertion")


def evaluate_assertions(
    *,
    assertions: dict[str, Any],
    assistant_message: str,
    planned_tool_calls: list[dict[str, Any]],
) -> list[AssertionResult]:
    """Apply the deterministic checks. Judge-question results are
    appended by the runner after this returns."""
    out: list[AssertionResult] = []
    lower = assistant_message.lower()

    for needle in assertions.get("must_contain") or []:
        present = needle.lower() in lower
        out.append(
            AssertionResult(
                kind="must_contain",
                passed=present,
                detail=(
                    f"text contains {needle!r}" if present else f"text does NOT contain {needle!r}"
                ),
                payload={"needle": needle},
            )
        )

    for needle in assertions.get("must_not_contain") or []:
        present = needle.lower() in lower
        out.append(
            AssertionResult(
                kind="must_not_contain",
                passed=not present,
                detail=(
                    f"text contains forbidden {needle!r}"
                    if present
                    else f"text does NOT contain {needle!r}"
                ),
                payload={"needle": needle},
            )
        )

    called = {call.get("name", "") for call in planned_tool_calls}

    for expected in assertions.get("expected_tools_called") or []:
        ok = expected in called
        out.append(
            AssertionResult(
                kind="expected_tools_called",
                passed=ok,
                detail=(f"agent called {expected!r}" if ok else f"agent did NOT call {expected!r}"),
                payload={"tool": expected, "actual": sorted(called)},
            )
        )

    for forbidden in assertions.get("tools_must_not_call") or []:
        ok = forbidden not in called
        out.append(
            AssertionResult(
                kind="tools_must_not_call",
                passed=ok,
                detail=(
                    f"agent did NOT call {forbidden!r}"
                    if ok
                    else f"agent called forbidden {forbidden!r}"
                ),
                payload={"tool": forbidden, "actual": sorted(called)},
            )
        )

    if assertions.get("must_emit_text"):
        ok = bool(assistant_message.strip())
        out.append(
            AssertionResult(
                kind="must_emit_text",
                passed=ok,
                detail="assistant produced text" if ok else "assistant text was empty",
            )
        )

    return out
