"""Lazy Langfuse client singleton with noop fallback.

The SDK initialises ONCE per process and is the destination for all
LangGraph traces. Because LiteLLM has a Langfuse integration that hooks
``litellm.success_callback``, the SDK MUST be initialised BEFORE the
first ``acompletion`` call — wire ``init_langfuse`` from the worker
``main`` before ``build_default_router`` runs.

When ``NEXUS_LANGFUSE_PUBLIC_KEY`` is unset the module returns a noop
client so tests + dev work without credentials. The noop is a Protocol
with the few methods the worker actually calls.
"""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog

if TYPE_CHECKING:
    from nexus_worker.config import WorkerSettings

log = structlog.get_logger(__name__)


@runtime_checkable
class LangfuseClientLike(Protocol):
    """The subset of the SDK we actually rely on.

    Both the real ``langfuse.Langfuse`` instance and the noop client
    below satisfy this protocol — call sites can stay agnostic.
    """

    enabled: bool

    def flush(self) -> None: ...
    def shutdown(self) -> None: ...


class _NoopClient:
    """Used in tests + when credentials are missing.

    Every method is a no-op so call sites stay clean. ``enabled=False``
    lets ``trace_turn``/``span`` short-circuit before doing work that
    only matters when telemetry is on.
    """

    enabled: bool = False

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        def _noop(*args: Any, **kwargs: Any) -> None:
            return None

        return _noop


_client: LangfuseClientLike | None = None
_client_lock = Lock()


def init_langfuse(settings: WorkerSettings | None = None) -> LangfuseClientLike:
    """Initialise the SDK. Idempotent — second call returns the cached
    client. Safe to call before any LiteLLM-ish code path."""
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        if settings is None:
            from nexus_worker.config import get_worker_settings

            settings = get_worker_settings()
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            log.info("langfuse.noop_mode", reason="public_or_secret_key_missing")
            _client = _NoopClient()
            return _client
        try:
            from langfuse import Langfuse

            real = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                environment=settings.langfuse_environment,
            )
            # Tag the SDK instance with the protocol's ``enabled`` flag so
            # callers can branch via ``is_enabled()`` without importing the
            # SDK type.
            real.enabled = True  # type: ignore[attr-defined]
            log.info(
                "langfuse.initialised",
                host=settings.langfuse_host,
                environment=settings.langfuse_environment,
            )
            _client = real  # type: ignore[assignment]
            assert _client is not None
            return _client
        except Exception as exc:
            log.warning("langfuse.init_failed", error=str(exc), falling_back_to="noop")
            _client = _NoopClient()
            return _client


def get_client() -> LangfuseClientLike:
    """Return the active client. ``init_langfuse`` lazily on first use."""
    if _client is None:
        return init_langfuse()
    return _client


def is_enabled() -> bool:
    return bool(getattr(get_client(), "enabled", False))


def shutdown() -> None:
    """Flush and close the SDK on worker stop."""
    global _client
    with _client_lock:
        if _client is None:
            return
        try:
            _client.flush()
            _client.shutdown()
        except Exception as exc:
            log.warning("langfuse.shutdown_failed", error=str(exc))
        _client = None


def reset_for_tests() -> None:
    """Test helper — drop the cached client."""
    global _client
    with _client_lock:
        _client = None
