"""Regression tests for the trace_turn / span context managers.

Bug: both were ``@contextmanager`` generators that ``yield``-ed a second
time from an ``except`` after the ``with`` body raised. That makes
``__exit__`` raise ``RuntimeError("generator didn't stop after throw()")``,
which masked the real turn error and broke clean unwinding (leaking the
LLM's httpx connection → pool exhaustion → instant litellm timeouts).

These tests exercise the ENABLED path (the buggy one): a body exception
must propagate as itself, and the span must still be ended.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_worker.observability import tracing

pytestmark = [pytest.mark.unit]


class _FakeSpan:
    def __init__(self) -> None:
        self.ended = False

    def end(self) -> None:
        self.ended = True


class _FakeClient:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def trace(self, **_: object) -> str:
        return "trace-stub"

    def span(self, **_: object) -> _FakeSpan:
        s = _FakeSpan()
        self.spans.append(s)
        return s


@pytest.fixture
def _enabled(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(tracing, "is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_client", lambda: client)
    return client


def test_trace_turn_propagates_body_exception_cleanly(_enabled: _FakeClient) -> None:
    with (
        pytest.raises(ValueError, match="boom"),
        tracing.trace_turn(tenant_id=uuid.uuid4()) as trace,
    ):
        assert trace == "trace-stub"  # enabled path really ran
        raise ValueError("boom")


def test_span_propagates_body_exception_and_still_ends(_enabled: _FakeClient) -> None:
    with pytest.raises(ValueError, match="boom"), tracing.span("unit") as s:
        assert isinstance(s, _FakeSpan)
        raise ValueError("boom")
    # The span must have been closed even though the body raised.
    assert _enabled.spans[0].ended is True


def test_trace_turn_happy_path_yields_trace(_enabled: _FakeClient) -> None:
    with tracing.trace_turn(tenant_id=uuid.uuid4()) as trace:
        assert trace == "trace-stub"


def test_trace_turn_survives_client_setup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        def trace(self, **_: object) -> str:
            raise RuntimeError("sdk down")

    monkeypatch.setattr(tracing, "is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_client", lambda: _Boom())
    # Setup failure must degrade to a None trace, not blow up the turn.
    with tracing.trace_turn(tenant_id=uuid.uuid4()) as trace:
        assert trace is None
