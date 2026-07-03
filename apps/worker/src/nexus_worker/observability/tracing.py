"""Trace + span helpers wrapping Langfuse.

``trace_turn`` opens a per-pipeline-turn trace with ``user_id =
str(tenant_id)`` (so the Langfuse UI groups by tenant) and yields a
context whose attributes the pipeline + tool dispatch decorate.

``span(name)`` wraps a node or tool call with input/output captured.
Both are no-ops when Langfuse is in noop mode — the runtime should
treat the helpers as zero-cost when telemetry is off.

Input redaction: bodies that may contain PII (customer messages,
prompts) are passed through ``_redact`` before persisting. Phase 1 is a
conservative regex set; richer redaction is Phase 2 work.
"""

from __future__ import annotations

import contextlib
import re
import uuid
from collections.abc import Iterator
from typing import Any

import structlog

from nexus_worker.observability.langfuse_client import get_client, is_enabled

log = structlog.get_logger(__name__)

_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{6,}\d")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _redact(value: Any) -> Any:
    """Replace plausible phone numbers and emails. Conservative — leaves
    structure intact so Langfuse spans remain readable."""
    if value is None:
        return None
    if isinstance(value, str):
        out = _PHONE_RE.sub("[redacted-phone]", value)
        out = _EMAIL_RE.sub("[redacted-email]", out)
        return out
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


@contextlib.contextmanager
def trace_turn(
    *,
    tenant_id: uuid.UUID | str,
    channel_id: uuid.UUID | str | None = None,
    user_id_inside_channel: str | None = None,
    name: str = "agent.turn",
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Open a top-level Langfuse trace. ``user_id`` is the tenant_id so
    the Langfuse UI's user filter doubles as a tenant filter.

    Yields the underlying ``trace`` object (or a noop stub). Pipeline
    code does not need to attach to it — the SDK uses
    contextvars internally.
    """
    if not is_enabled():
        yield None
        return
    client = get_client()
    tags = ["agent.turn"]
    if channel_id is not None:
        tags.append(f"channel:{channel_id}")
    # SETUP ONLY inside the try. A ``@contextmanager`` must ``yield`` exactly
    # once; yielding again from an ``except`` after the body raised makes
    # ``__exit__`` throw ``RuntimeError("generator didn't stop after throw()")``,
    # which masks the real turn error AND breaks clean unwinding (leaking the
    # LLM's httpx connection → pool exhaustion → instant litellm timeouts).
    # So we only guard trace creation here; the body's exceptions propagate
    # through the single ``yield`` below untouched.
    trace: Any = None
    try:
        # The v3 SDK exposes ``trace()`` on the client; attribute access
        # tolerates older minor versions that exposed it as a context.
        start_trace = getattr(client, "trace", None) or getattr(client, "start_span", None)
        if start_trace is not None:
            trace = start_trace(
                name=name,
                user_id=str(tenant_id),
                metadata=_redact(
                    {
                        "tenant_id": str(tenant_id),
                        "channel_id": str(channel_id) if channel_id else None,
                        "user_id_inside_channel": user_id_inside_channel,
                        **(metadata or {}),
                    }
                ),
                tags=tags,
            )
    except Exception as exc:
        log.warning("langfuse.trace_failed", error=str(exc))
        trace = None
    yield trace


@contextlib.contextmanager
def span(
    name: str,
    *,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Open a span under the current trace. No-op when disabled."""
    if not is_enabled():
        yield None
        return
    client = get_client()
    # SETUP ONLY inside the try (see trace_turn): yield exactly once so a
    # body exception unwinds cleanly instead of triggering "generator didn't
    # stop after throw()".
    s: Any = None
    try:
        start_span = getattr(client, "span", None) or getattr(client, "start_span", None)
        if start_span is not None:
            s = start_span(
                name=name,
                input=_redact(input),
                metadata=_redact(metadata or {}),
            )
    except Exception as exc:
        log.warning("langfuse.span_failed", name=name, error=str(exc))
        s = None
    try:
        yield s
    finally:
        end = getattr(s, "end", None)
        if callable(end):
            try:
                end()
            except Exception as exc:
                log.warning("langfuse.span_end_failed", name=name, error=str(exc))


def update_trace(*, output: Any = None, level: str | None = None) -> None:
    """Attach the final output / outcome level to the current trace."""
    if not is_enabled():
        return
    client = get_client()
    try:
        upd = getattr(client, "update_current_trace", None)
        if callable(upd):
            upd(output=_redact(output), level=level)
    except Exception as exc:
        log.warning("langfuse.update_trace_failed", error=str(exc))
