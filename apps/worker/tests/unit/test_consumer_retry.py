"""Unit tests for the transient-DB-error retry in the inbound consumer.

The managed Postgres / proxy drops connections, surfacing as
"the connection is closed" / SSL EOF. Before the retry, a single such
failure left the Redis entry pending forever (no reclaim loop is wired),
so the customer never got a reply (barbersupply outage 2026-08-14). These
tests pin the retry contract: transient DB errors are retried in-place and
the entry is acked on eventual success; a non-transient error is not
retried and the entry is left pending (not acked).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy.exc import InterfaceError, OperationalError

import nexus_worker.streams.consumer as consumer
from nexus_worker.streams.consumer import _is_transient_db_error, run_inbound_consumer


class TestTransientDetection:
    def test_interface_error_is_transient(self) -> None:
        exc = InterfaceError("SELECT 1", {}, Exception("the connection is closed"))
        assert _is_transient_db_error(exc) is True

    def test_operational_error_is_transient(self) -> None:
        exc = OperationalError("SELECT 1", {}, Exception("server closed the connection"))
        assert _is_transient_db_error(exc) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "the connection is closed",
            "SSL error: unexpected eof while reading",
            "consuming input failed: SSL error",
            "connection reset by peer",
        ],
    )
    def test_message_substring_is_transient(self, msg: str) -> None:
        assert _is_transient_db_error(RuntimeError(msg)) is True

    def test_ordinary_error_is_not_transient(self) -> None:
        assert _is_transient_db_error(ValueError("bad input")) is False


class _FakeRedis:
    """Serves one batch of entries once, then signals stop and returns empty."""

    def __init__(self, entries: list[tuple[str, dict[str, str]]], stop: asyncio.Event) -> None:
        self._entries = entries
        self._stop = stop
        self._served = False
        self.acked: list[str] = []

    async def xgroup_create(self, *a: Any, **k: Any) -> None:
        return None

    async def xreadgroup(self, **k: Any) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        if self._served:
            self._stop.set()
            return []
        self._served = True
        return [("nexus:inbound", self._entries)]

    async def xack(self, stream: str, group: str, entry_id: str) -> None:
        self.acked.append(entry_id)


def _fields() -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "channel_id": str(uuid.uuid4()),
        "user_id": "56990000000",
        "content": "hola",
    }


async def _run(fake_redis: _FakeRedis, stop: asyncio.Event) -> None:
    await run_inbound_consumer(
        fake_redis,  # type: ignore[arg-type]
        pipeline=object(),
        stream="nexus:inbound",
        group="nexus-worker",
        consumer_name="test-1",
        block_ms=1,
        stop=stop,
    )


@pytest.mark.asyncio
class TestRetry:
    async def test_transient_error_is_retried_then_acked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consumer, "_DISPATCH_RETRY_BASE_DELAY", 0.0)
        attempts = {"n": 0}

        async def fake_process(event: Any, *, pipeline: Any) -> None:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise InterfaceError("q", {}, Exception("the connection is closed"))
            return None

        monkeypatch.setattr(consumer, "process_inbound", fake_process)

        stop = asyncio.Event()
        redis = _FakeRedis([("1-0", _fields())], stop)
        await _run(redis, stop)

        assert attempts["n"] == 3  # failed twice, succeeded on the third
        assert redis.acked == ["1-0"]  # acked after eventual success

    async def test_non_transient_error_is_not_retried_nor_acked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consumer, "_DISPATCH_RETRY_BASE_DELAY", 0.0)
        attempts = {"n": 0}

        async def fake_process(event: Any, *, pipeline: Any) -> None:
            attempts["n"] += 1
            raise ValueError("boom")

        monkeypatch.setattr(consumer, "process_inbound", fake_process)

        stop = asyncio.Event()
        redis = _FakeRedis([("1-0", _fields())], stop)
        await _run(redis, stop)

        assert attempts["n"] == 1  # no retry for a non-transient error
        assert redis.acked == []  # left pending (not acked)

    async def test_transient_error_exhausts_attempts_then_left_pending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consumer, "_DISPATCH_RETRY_BASE_DELAY", 0.0)
        attempts = {"n": 0}

        async def fake_process(event: Any, *, pipeline: Any) -> None:
            attempts["n"] += 1
            raise InterfaceError("q", {}, Exception("the connection is closed"))

        monkeypatch.setattr(consumer, "process_inbound", fake_process)

        stop = asyncio.Event()
        redis = _FakeRedis([("1-0", _fields())], stop)
        await _run(redis, stop)

        assert attempts["n"] == consumer._MAX_DISPATCH_ATTEMPTS  # tried the max
        assert redis.acked == []  # still pending after exhausting retries
