"""Qué cuenta como «el modelo no respondió» y qué rastro deja (bug
``el-probador-tapa-los-fallos-del-modelo``)."""

from __future__ import annotations

import time
import uuid

import pytest
from fakeredis import aioredis as fakeaioredis
from nexus_api.core import redis_client
from structlog.testing import capture_logs

from nexus_worker.simulation.failures import (
    COUNTER_PREFIX,
    ModelFailure,
    failure_of_call,
    failure_of_turn,
    note_model_failure,
)


def test_a_healthy_turn_has_no_failure() -> None:
    assert failure_of_turn({"response": "Abrimos a las 10.", "turn_failure": None}) is None
    assert failure_of_turn({}) is None


def test_the_provider_failed() -> None:
    failure = failure_of_turn({"turn_failure": {"kind": "llm_failed", "detail": "boom"}})
    assert failure == ModelFailure("agent", "llm_failed", "boom")


def test_there_is_no_model_for_this_client() -> None:
    failure = failure_of_turn(
        {"turn_failure": {"kind": "llm_failed", "reason": "no_model", "detail": None}}
    )
    assert failure == ModelFailure("agent", "no_model")


def test_the_model_answered_nothing() -> None:
    assert failure_of_turn({"turn_failure": {"kind": "empty_response"}}) == ModelFailure(
        "agent", "empty_response"
    )


@pytest.mark.parametrize(
    "turn_failure",
    [
        {"kind": "handoff", "reason": "escalated"},
        {"kind": "handoff", "reason": "turn_limit"},
        {"kind": "llm_failed", "reason": "turn_limit", "detail": "budget"},
        {"kind": "llm_failed", "reason": "escalated", "detail": None},
    ],
)
def test_what_the_router_decided_is_not_a_failure_of_the_model(
    turn_failure: dict[str, str | None],
) -> None:
    assert failure_of_turn({"turn_failure": turn_failure}) is None


def test_what_the_console_reads_never_carries_the_provider_error() -> None:
    failure = failure_of_call("customer", RuntimeError("sk-secret"))
    assert failure.detail == "RuntimeError: sk-secret"
    assert "sk-secret" not in failure.why
    assert "cliente simulado" in failure.why


@pytest.mark.asyncio
async def test_noting_it_leaves_the_log_and_the_counter_of_the_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fakeaioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake)
    tenant = uuid.uuid4()
    with capture_logs() as logs:
        await note_model_failure(tenant, ModelFailure("agent", "llm_failed", "x" * 500))
    window = int(time.time()) // 600
    assert await fake.get(f"{COUNTER_PREFIX}:{tenant}:{window}") == "1"
    (entry,) = [e for e in logs if e["event"] == "simulation.model_failed"]
    assert entry["tenant_id"] == str(tenant)
    assert entry["who"] == "agent" and entry["reason"] == "llm_failed"
    assert len(entry["detail"]) == 200
    assert await fake.keys("nexus:alert:turn_errors:*") == [], "turn_error_burst no lo ve"


@pytest.mark.asyncio
async def test_a_redis_that_fails_does_not_break_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> None:
        raise ConnectionError("redis")

    monkeypatch.setattr(redis_client, "get_redis", broken)
    await note_model_failure(uuid.uuid4(), ModelFailure("judge", "llm_failed"))
