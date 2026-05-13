"""Block P — pure-Python tests for the assertion evaluator + validator.

These cover the DSL surface; the runner integration lives in a
separate test file with a FakeJudgeProvider.
"""

from __future__ import annotations

import pytest

from nexus_api.services.evals.assertions import (
    AssertionValidationError,
    evaluate_assertions,
    validate_assertions,
)


def test_validate_rejects_empty_object() -> None:
    with pytest.raises(AssertionValidationError):
        validate_assertions({})


def test_validate_rejects_unknown_key() -> None:
    with pytest.raises(AssertionValidationError, match="unknown assertion keys"):
        validate_assertions({"must_contain": ["x"], "should_yodel": True})


def test_validate_rejects_wrong_types() -> None:
    with pytest.raises(AssertionValidationError):
        validate_assertions({"must_contain": "not a list"})  # type: ignore[arg-type]
    with pytest.raises(AssertionValidationError):
        validate_assertions({"must_emit_text": "yes"})  # type: ignore[arg-type]


def test_validate_accepts_only_must_emit_text_true() -> None:
    """A case can declare just ``must_emit_text=true`` and that counts as
    "at least one non-empty assertion"."""
    validate_assertions({"must_emit_text": True})


def test_validate_rejects_no_real_assertions() -> None:
    """All keys present but empty / false → still rejected."""
    with pytest.raises(AssertionValidationError):
        validate_assertions(
            {
                "must_contain": [],
                "judge_questions": [],
                "must_emit_text": False,
            }
        )


def test_must_contain_passes_when_substring_present() -> None:
    results = evaluate_assertions(
        assertions={"must_contain": ["disponibilidad", "10"]},
        assistant_message="Tenemos disponibilidad mañana a las 10.",
        planned_tool_calls=[],
    )
    assert all(r.passed for r in results)
    assert len(results) == 2


def test_must_contain_fails_when_missing() -> None:
    results = evaluate_assertions(
        assertions={"must_contain": ["disponibilidad"]},
        assistant_message="No tenemos turnos hoy.",
        planned_tool_calls=[],
    )
    assert len(results) == 1
    assert results[0].passed is False
    assert "does NOT contain" in results[0].detail


def test_must_not_contain_inverts() -> None:
    """The check passes when the forbidden substring is absent."""
    results = evaluate_assertions(
        assertions={"must_not_contain": ["error"]},
        assistant_message="Todo bien.",
        planned_tool_calls=[],
    )
    assert results[0].passed is True

    results = evaluate_assertions(
        assertions={"must_not_contain": ["error"]},
        assistant_message="Hubo un error.",
        planned_tool_calls=[],
    )
    assert results[0].passed is False


def test_expected_tools_called_passes_when_present() -> None:
    results = evaluate_assertions(
        assertions={"expected_tools_called": ["booking.check_availability"]},
        assistant_message="",
        planned_tool_calls=[{"name": "booking.check_availability", "arguments": {}}],
    )
    assert results[0].passed is True


def test_expected_tools_called_fails_when_missing() -> None:
    results = evaluate_assertions(
        assertions={"expected_tools_called": ["booking.create_appointment"]},
        assistant_message="ok",
        planned_tool_calls=[{"name": "booking.check_availability", "arguments": {}}],
    )
    assert results[0].passed is False
    assert "did NOT call" in results[0].detail


def test_tools_must_not_call_inverts() -> None:
    results = evaluate_assertions(
        assertions={"tools_must_not_call": ["booking.create_appointment"]},
        assistant_message="ok",
        planned_tool_calls=[{"name": "booking.check_availability", "arguments": {}}],
    )
    assert results[0].passed is True

    results = evaluate_assertions(
        assertions={"tools_must_not_call": ["booking.create_appointment"]},
        assistant_message="ok",
        planned_tool_calls=[{"name": "booking.create_appointment", "arguments": {}}],
    )
    assert results[0].passed is False


def test_must_emit_text_passes_when_non_empty() -> None:
    results = evaluate_assertions(
        assertions={"must_emit_text": True},
        assistant_message="Hola.",
        planned_tool_calls=[],
    )
    assert results[0].passed is True


def test_must_emit_text_fails_when_whitespace_only() -> None:
    results = evaluate_assertions(
        assertions={"must_emit_text": True},
        assistant_message="   ",
        planned_tool_calls=[],
    )
    assert results[0].passed is False


def test_case_insensitive_must_contain() -> None:
    results = evaluate_assertions(
        assertions={"must_contain": ["DISPONIBILIDAD"]},
        assistant_message="hay disponibilidad",
        planned_tool_calls=[],
    )
    assert results[0].passed is True
