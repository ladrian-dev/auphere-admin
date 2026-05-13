"""Block P — judge response parser tests."""

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


def test_parse_pass_true() -> None:
    reply = _parse_judge_reply('{"pass": true, "reason": "ok"}')
    assert reply.passed is True
    assert reply.reason == "ok"


def test_parse_pass_false() -> None:
    reply = _parse_judge_reply('{"pass": false, "reason": "missed the date"}')
    assert reply.passed is False


def test_parse_tolerates_surrounding_chatter() -> None:
    """Some models prefix their JSON with a sentence even when told not
    to. The parser scans for the first JSON object."""
    raw = 'Sure thing:\n{"pass": true, "reason": "ok"}'
    assert _parse_judge_reply(raw).passed is True


def test_parse_rejects_missing_pass() -> None:
    with pytest.raises(JudgeError, match="missing 'pass'"):
        _parse_judge_reply('{"reason": "ok"}')


def test_parse_rejects_non_bool_pass() -> None:
    with pytest.raises(JudgeError):
        _parse_judge_reply('{"pass": "yes", "reason": "ok"}')


def test_parse_rejects_malformed_json() -> None:
    with pytest.raises(JudgeError):
        _parse_judge_reply("{pass true reason ok}")


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
            planned_tool_calls=[],
            timeout_s=5.0,
        )
    )
    assert reply.passed is True
    assert reply.reason == "ok"


def test_fake_judge_can_inject_failure() -> None:
    provider = FakeJudgeProvider(
        responder=lambda q, m, t: JudgeReply(passed=False, reason="too short", raw="{}")
    )
    reply = asyncio.run(
        provider.judge(
            tenant_id=uuid.uuid4(),
            question="¿saludó?",
            assistant_message="Hola",
            planned_tool_calls=[],
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
                planned_tool_calls=[],
                timeout_s=5.0,
            )
        )
