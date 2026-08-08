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


# ── WP-02: record_generation ──────────────────────────────────────────────────


class _FakeGeneration:
    def __init__(self) -> None:
        self.end_kwargs: dict[str, object] | None = None

    def end(self, **kwargs: object) -> None:
        self.end_kwargs = kwargs


class _GenClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.generations: list[_FakeGeneration] = []

    def start_generation(self, **kwargs: object) -> _FakeGeneration:
        self.calls.append(kwargs)
        gen = _FakeGeneration()
        self.generations.append(gen)
        return gen


def test_record_generation_emits_tokens_and_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _GenClient()
    monkeypatch.setattr(tracing, "is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_client", lambda: client)
    tenant = uuid.uuid4()

    tracing.record_generation(
        tenant_id=tenant,
        role="respond",
        model="anthropic/claude-sonnet-4-6",
        usage={
            "prompt_tokens": 1200,
            "completion_tokens": 240,
            "cache_read_input_tokens": 1000,
            "cache_creation_input_tokens": 0,
        },
        latency_ms=987,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["name"] == "llm.respond"
    assert call["model"] == "anthropic/claude-sonnet-4-6"
    metadata = call["metadata"]
    assert metadata["tenant_id"] == str(tenant)
    assert metadata["latency_ms"] == 987
    usage_details = client.generations[0].end_kwargs["usage_details"]
    assert usage_details == {
        "input": 1200,
        "output": 240,
        "cache_read_input_tokens": 1000,
        "cache_creation_input_tokens": 0,
    }


def test_record_generation_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        def start_generation(self, **_: object) -> None:
            raise RuntimeError("sdk down")

    monkeypatch.setattr(tracing, "is_enabled", lambda: True)
    monkeypatch.setattr(tracing, "get_client", lambda: _Boom())
    # Must not propagate — instrumentation can never break a turn.
    tracing.record_generation(
        tenant_id=uuid.uuid4(), role="classify", model="m", usage={}, latency_ms=1
    )


def test_record_generation_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    monkeypatch.setattr(tracing, "is_enabled", lambda: False)
    monkeypatch.setattr(tracing, "get_client", lambda: called.append(True))
    tracing.record_generation(
        tenant_id=uuid.uuid4(), role="classify", model="m", usage={}, latency_ms=1
    )
    assert called == []
