"""Block P — judge response parser tests (roadmap E2.2 — verdict)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from nexus_api.services.evals.judge import (
    FakeJudgeProvider,
    JudgeError,
    JudgeReply,
    _parse_judge_reply,
)


def test_parse_verdict_pass() -> None:
    reply = _parse_judge_reply('{"verdict": "pass", "reason": "ok"}')
    assert reply.verdict == "pass"
    assert reply.passed is True
    assert reply.is_unknown is False
    assert reply.reason == "ok"


def test_parse_verdict_fail() -> None:
    reply = _parse_judge_reply('{"verdict": "fail", "reason": "missed the date"}')
    assert reply.verdict == "fail"
    assert reply.passed is False
    assert reply.is_unknown is False


def test_parse_verdict_unknown() -> None:
    """E2.2 — an ambiguous transcript escapes to ``unknown``: not a pass,
    not a fail."""
    reply = _parse_judge_reply('{"verdict": "unknown", "reason": "no evidence"}')
    assert reply.verdict == "unknown"
    assert reply.is_unknown is True
    assert reply.passed is False


def test_parse_verdict_is_case_insensitive() -> None:
    assert _parse_judge_reply('{"verdict": "PASS"}').verdict == "pass"


def test_parse_legacy_pass_bool_still_accepted() -> None:
    """A model that emits the old ``{"pass": bool}`` shape is mapped onto
    the verdict contract instead of hard-failing."""
    assert _parse_judge_reply('{"pass": true, "reason": "ok"}').verdict == "pass"
    assert _parse_judge_reply('{"pass": false, "reason": "no"}').verdict == "fail"


def test_parse_tolerates_surrounding_chatter() -> None:
    raw = 'Sure thing:\n{"verdict": "pass", "reason": "ok"}'
    assert _parse_judge_reply(raw).passed is True


def test_parse_rejects_invalid_verdict() -> None:
    with pytest.raises(JudgeError, match="verdict"):
        _parse_judge_reply('{"verdict": "maybe", "reason": "ok"}')


def test_parse_rejects_missing_verdict() -> None:
    with pytest.raises(JudgeError, match="missing 'verdict'"):
        _parse_judge_reply('{"reason": "ok"}')


def test_parse_rejects_non_bool_legacy_pass() -> None:
    with pytest.raises(JudgeError):
        _parse_judge_reply('{"pass": "yes", "reason": "ok"}')


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(JudgeError):
        _parse_judge_reply("{verdict pass reason ok}")


def test_parse_rejects_no_json_at_all() -> None:
    with pytest.raises(JudgeError, match="no JSON object"):
        _parse_judge_reply("nope")


def test_fake_judge_default_returns_pass() -> None:
    provider = FakeJudgeProvider()
    reply = asyncio.run(
        provider.judge(
            tenant_id=uuid.uuid4(),
            question="¿saludó al cliente?",
            assistant_message="Hola.",
            tool_calls=[],
            timeout_s=5.0,
        )
    )
    assert reply.verdict == "pass"
    assert reply.passed is True


def test_fake_judge_can_inject_unknown() -> None:
    provider = FakeJudgeProvider(
        responder=lambda q, m, t: JudgeReply(verdict="unknown", reason="ambiguo", raw="{}")
    )
    reply = asyncio.run(
        provider.judge(
            tenant_id=uuid.uuid4(),
            question="¿usó la tool?",
            assistant_message="Hola",
            tool_calls=[],
            timeout_s=5.0,
        )
    )
    assert reply.is_unknown is True


def test_fake_judge_can_inject_failure() -> None:
    provider = FakeJudgeProvider(
        responder=lambda q, m, t: JudgeReply(verdict="fail", reason="too short", raw="{}")
    )
    reply = asyncio.run(
        provider.judge(
            tenant_id=uuid.uuid4(),
            question="¿saludó?",
            assistant_message="Hola",
            tool_calls=[],
            timeout_s=5.0,
        )
    )
    assert reply.passed is False


def test_fake_judge_can_raise_judge_error() -> None:
    provider = FakeJudgeProvider(responder=lambda q, m, t: JudgeError("upstream 500"))
    with pytest.raises(JudgeError):
        asyncio.run(
            provider.judge(
                tenant_id=uuid.uuid4(),
                question="?",
                assistant_message="x",
                tool_calls=[],
                timeout_s=5.0,
            )
        )
