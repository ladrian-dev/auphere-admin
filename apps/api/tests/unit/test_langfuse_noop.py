"""Block H: Langfuse client falls back to noop without credentials.

In tests we never want a real Langfuse Cloud connection — the noop
client must satisfy the protocol so call sites don't have to gate
every span/trace behind an ``if enabled`` check.
"""

from __future__ import annotations

import pytest


def test_init_returns_noop_when_keys_missing():
    from nexus_worker.config import WorkerSettings
    from nexus_worker.observability import langfuse_client

    langfuse_client.reset_for_tests()
    settings = WorkerSettings(
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )
    client = langfuse_client.init_langfuse(settings)
    assert client.enabled is False
    assert langfuse_client.is_enabled() is False


def test_noop_client_methods_dont_raise():
    from nexus_worker.observability import langfuse_client

    langfuse_client.reset_for_tests()
    client = langfuse_client.init_langfuse(
        type(
            "S",
            (),
            {
                "langfuse_public_key": None,
                "langfuse_secret_key": None,
                "langfuse_host": "x",
                "langfuse_environment": "x",
            },
        )()
    )
    client.flush()
    client.shutdown()
    # Arbitrary attribute access returns a callable noop.
    client.trace(name="x")
    client.span(name="y")


def test_trace_turn_is_noop_when_disabled():
    from nexus_worker.observability import langfuse_client, tracing

    langfuse_client.reset_for_tests()
    settings = type(
        "S",
        (),
        {
            "langfuse_public_key": None,
            "langfuse_secret_key": None,
            "langfuse_host": "x",
            "langfuse_environment": "x",
        },
    )()
    langfuse_client.init_langfuse(settings)

    with tracing.trace_turn(tenant_id="00000000-0000-0000-0000-000000000000") as t:
        assert t is None
    with tracing.span("any") as s:
        assert s is None


def test_redaction_strips_emails_and_phones():
    from nexus_worker.observability.tracing import _redact

    redacted = _redact(
        {
            "input": "Mensaje de prueba +56999990001 ping@example.com",
            "nested": [
                "+1 234 567 8901",
                "another@email.io",
                {"deep": "no PII here"},
            ],
        }
    )
    assert "+56999990001" not in redacted["input"]
    assert "ping@example.com" not in redacted["input"]
    assert "[redacted-phone]" in redacted["input"]
    assert "[redacted-email]" in redacted["input"]
    assert "+1 234 567 8901" not in redacted["nested"][0]
    assert "[redacted-email]" in redacted["nested"][1]
    assert redacted["nested"][2]["deep"] == "no PII here"


@pytest.fixture(autouse=True)
def _reset_after():
    yield
    from nexus_worker.observability import langfuse_client

    langfuse_client.reset_for_tests()
