"""LiteLLM OSS proxy resolver — partner virtual key, fail-closed.

Fase 1 cut: every live hop goes to ``LITELLM_PROXY_API_BASE`` with ONE
virtual key for the **partner** (G2). Mapping is server-side only. The
console body never carries ``partner_id`` or ``api_key``. ``metadata.tenant_id``
is stripped before the proxy sees the kwargs.

Not the master key. Not ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``.
Retries stay on the same ``api_base``; there is no vendor fallback.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger(__name__)

LLM_PROXY_UNAVAILABLE = "llm_proxy_unavailable"

_CLIENT_INJECTED = frozenset({"partner_id", "api_key", "api_base"})

_current_partner_id: ContextVar[uuid.UUID | None] = ContextVar("llm_proxy_partner_id", default=None)


class LLMProxyUnavailable(Exception):
    """Proxy cannot be used. Distinct from ``wallet_empty``."""

    code = LLM_PROXY_UNAVAILABLE

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


@dataclass(frozen=True)
class LiteLLMProxyTarget:
    api_base: str
    api_key: str
    partner_id: uuid.UUID


def current_llm_proxy_partner() -> uuid.UUID | None:
    return _current_partner_id.get()


def bind_llm_proxy_partner(partner_id: uuid.UUID) -> Token[uuid.UUID | None]:
    return _current_partner_id.set(partner_id)


def reset_llm_proxy_partner(token: Token[uuid.UUID | None]) -> None:
    _current_partner_id.reset(token)


@contextmanager
def llm_proxy_partner_scope(partner_id: uuid.UUID) -> Iterator[uuid.UUID]:
    token = bind_llm_proxy_partner(partner_id)
    try:
        yield partner_id
    finally:
        reset_llm_proxy_partner(token)


def require_current_llm_proxy_partner() -> uuid.UUID:
    partner_id = current_llm_proxy_partner()
    if partner_id is None:
        raise LLMProxyUnavailable("missing partner virtual key")
    return partner_id


def _env(*names: str) -> str:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return ""


def _settings_base_and_keys() -> tuple[str, str]:
    try:
        from nexus_api.config import get_settings

        settings = get_settings()
    except Exception:
        return "", ""
    return (
        (getattr(settings, "litellm_proxy_api_base", "") or "").strip(),
        (getattr(settings, "litellm_proxy_virtual_keys", "") or "").strip(),
    )


def proxy_api_base() -> str:
    base = _env("LITELLM_PROXY_API_BASE", "NEXUS_LITELLM_PROXY_API_BASE")
    if not base:
        base, _ = _settings_base_and_keys()
    return base.rstrip("/")


def _virtual_keys_raw() -> str:
    raw = _env("LITELLM_PROXY_VIRTUAL_KEYS", "NEXUS_LITELLM_PROXY_VIRTUAL_KEYS")
    if raw:
        return raw
    _, keys = _settings_base_and_keys()
    return keys


def virtual_key_for(partner_id: uuid.UUID) -> str:
    raw = _virtual_keys_raw()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("llm_proxy.virtual_keys_invalid_json")
        return ""
    if not isinstance(parsed, dict):
        return ""
    key = parsed.get(str(partner_id))
    if key is None:
        key = parsed.get(str(partner_id).lower())
    if not isinstance(key, str):
        return ""
    return key.strip()


def resolve_litellm_proxy(partner_id: uuid.UUID | None) -> LiteLLMProxyTarget:
    """Fail-closed: missing base or partner virtual key → no hop."""
    if partner_id is None:
        raise LLMProxyUnavailable("missing partner virtual key")
    base = proxy_api_base()
    if not base:
        raise LLMProxyUnavailable("missing LITELLM_PROXY_API_BASE")
    key = virtual_key_for(partner_id)
    if not key:
        raise LLMProxyUnavailable("missing partner virtual key")
    return LiteLLMProxyTarget(api_base=base, api_key=key, partner_id=partner_id)


def require_litellm_proxy(partner_id: uuid.UUID | None) -> LiteLLMProxyTarget:
    return resolve_litellm_proxy(partner_id)


def _strip_injected(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in _CLIENT_INJECTED}


def apply_litellm_proxy_kwargs(
    kwargs: dict[str, Any], *, partner_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Stamp proxy auth and drop console-injected / tenant metadata."""
    target = resolve_litellm_proxy(
        partner_id if partner_id is not None else current_llm_proxy_partner()
    )
    for injected in _CLIENT_INJECTED:
        kwargs.pop(injected, None)
    extra_body = kwargs.get("extra_body")
    if isinstance(extra_body, dict):
        kwargs["extra_body"] = _strip_injected(extra_body)
    metadata = kwargs.get("metadata")
    if isinstance(metadata, dict):
        cleaned = _strip_injected(metadata)
        cleaned.pop("tenant_id", None)
        kwargs["metadata"] = cleaned
    kwargs["api_base"] = target.api_base
    kwargs["api_key"] = target.api_key
    return kwargs


def _exc_status(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        raw = getattr(exc, attr, None)
        if isinstance(raw, int):
            return raw
    response = getattr(exc, "response", None)
    if response is not None:
        raw = getattr(response, "status_code", None)
        if isinstance(raw, int):
            return raw
    return None


def _exc_text(exc: BaseException) -> str:
    parts = [str(exc), type(exc).__name__]
    for attr in ("message", "body", "code"):
        value = getattr(exc, attr, None)
        if value is not None:
            parts.append(str(value))
    return " ".join(parts).lower()


def map_proxy_failure(exc: BaseException) -> LLMProxyUnavailable | None:
    """Map proxy-down / auth / budget signals. None = not a proxy-closed hop."""
    if isinstance(exc, LLMProxyUnavailable):
        return exc
    name = type(exc).__name__
    text = _exc_text(exc)
    status = _exc_status(exc)
    if name in {
        "Timeout",
        "APITimeoutError",
        "APIConnectionError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
    } or isinstance(exc, TimeoutError | OSError):
        return LLMProxyUnavailable("proxy unreachable", retryable=True)
    if status == 401 or "unauthorized" in text:
        return LLMProxyUnavailable("proxy unauthorized", retryable=False)
    if status == 400 and ("budget" in text or "exceeded" in text or "max_budget" in text):
        return LLMProxyUnavailable("proxy budget exceeded", retryable=False)
    if status == 503 and ("fail_closed_budget_enforcement" in text or "fail_closed" in text):
        return LLMProxyUnavailable("proxy budget enforcement unavailable", retryable=False)
    return None


def raise_mapped_proxy_failure(exc: BaseException) -> None:
    mapped = map_proxy_failure(exc)
    if mapped is not None:
        raise mapped from exc


async def partner_id_for_tenant_standalone(tenant_id: uuid.UUID) -> uuid.UUID | None:
    """Partner of a tenant, or None. Fail-closed on an unreadable book."""
    try:
        from nexus_api.db.base import get_sessionmaker
        from nexus_api.metering.wallet import partner_id_for_tenant

        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            return await partner_id_for_tenant(session, tenant_id)
    except Exception as exc:
        log.warning(
            "llm_proxy.partner_lookup_failed",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        return None
