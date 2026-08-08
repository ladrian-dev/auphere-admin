"""WP-05: the SLI instruments record what the panel needs.

One test function on purpose: the OTel SDK only honours the FIRST global
``set_meter_provider`` per process, so install-once-and-assert-everything is
the only shape that stays deterministic under pytest ordering.
"""

from __future__ import annotations

from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from nexus_api.core import otel_metrics


def _collect(reader: InMemoryMetricReader) -> dict[str, list]:
    data = reader.get_metrics_data()
    out: dict[str, list] = {}
    if data is None:
        return out
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                out[metric.name] = list(metric.data.data_points)
    return out


def test_sli_instruments_record_and_export() -> None:
    reader = InMemoryMetricReader()
    otel_metrics.reset_for_tests()
    otel_metrics.install_metrics("nexus-test", extra_reader=reader)
    otel_metrics.ensure_queue_gauges()

    otel_metrics.record_turn(
        duration_ms=1234.5, tenant_id="t1", intent="book", channel="meta"
    )
    otel_metrics.record_turn_error(tenant_id="t1", stage="dispatch")
    otel_metrics.record_llm_call(
        model="anthropic/claude-sonnet-4-6",
        role="respond",
        duration_ms=800.0,
        usage={
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "cache_read_input_tokens": 900,
        },
    )
    otel_metrics.record_webhook_ack(provider="meta", duration_ms=12.0)
    otel_metrics.record_outbound_delivery(provider="meta", duration_ms=250.0)
    otel_metrics.record_meta_send_failure(code="131047")
    otel_metrics.set_queue_lag("nexus:inbound", entries=7, oldest_pending_s=3.5)

    metrics = _collect(reader)

    assert "turn_latency_ms" in metrics
    turn_point = metrics["turn_latency_ms"][0]
    assert turn_point.attributes["tenant"] == "t1"
    assert turn_point.attributes["intent"] == "book"

    assert metrics["turn_errors_total"][0].value == 1

    token_points = {
        p.attributes["type"]: p.value for p in metrics["llm_tokens_total"]
    }
    assert token_points == {"input": 1000, "output": 200, "cache_read": 900}

    assert "llm_call_ms" in metrics
    assert "webhook_ack_ms" in metrics
    assert "outbound_delivery_ms" in metrics
    assert metrics["meta_send_failures_total"][0].attributes["code"] == "131047"

    lag_points = {p.attributes["stream"]: p.value for p in metrics["queue_lag_entries"]}
    assert lag_points["nexus:inbound"] == 7
    oldest_points = {
        p.attributes["stream"]: p.value
        for p in metrics["queue_oldest_pending_seconds"]
    }
    assert oldest_points["nexus:inbound"] == 3.5


def test_recording_never_raises_without_install() -> None:
    # Helpers must be safe before install_metrics (e.g. unit tests importing
    # the consumer) — the API default meter hands out noop instruments.
    otel_metrics.record_turn(duration_ms=1.0, tenant_id="t", intent=None, channel="meta")
    otel_metrics.record_turn_error(tenant_id="t", stage="dispatch")
    otel_metrics.record_meta_send_failure(code="0")
