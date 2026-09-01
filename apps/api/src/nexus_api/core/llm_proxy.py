"""LiteLLM OSS proxy resolver — partner virtual key, fail-closed.

Fase 1 cut: every live hop goes to ``LITELLM_PROXY_API_BASE`` with ONE
virtual key for the **partner** (G2). Mapping is server-side only. The
console body never carries ``partner_id`` or ``api_key``. ``metadata.tenant_id``
is stripped before the proxy sees the kwargs.

Not the master key. Not ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``.
Retries stay on the same ``api_base``; there is no vendor fallback.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

import httpx
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


def proxy_required() -> bool:
    """¿El proxy es un requisito para responder? (ADR-036)

    Env primero, igual que el resto del módulo; luego settings. Por defecto
    **no**: la ausencia de proxy es una decisión de despliegue, no un fallo.
    """
    raw = _env("LITELLM_PROXY_REQUIRED", "NEXUS_LLM_PROXY_REQUIRED")
    if raw:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    try:
        from nexus_api.config import get_settings

        return bool(getattr(get_settings(), "llm_proxy_required", False))
    except Exception:
        return False


def resolve_litellm_proxy_optional(partner_id: uuid.UUID | None) -> LiteLLMProxyTarget | None:
    """Target del proxy, o ``None`` si este despliegue va a vendor directo.

    Con ``llm_proxy_required`` la ausencia sigue siendo ``LLMProxyUnavailable``
    — ruidosa, y el llamador la trata como el error de configuración que es.
    Sin él, ``None`` significa «sin salto»: el hop sale al vendor con las
    claves del entorno, que es lo que producción lleva haciendo desde el
    rollback del 31-ago.
    """
    if proxy_required():
        return resolve_litellm_proxy(partner_id)
    try:
        return resolve_litellm_proxy(partner_id)
    except LLMProxyUnavailable:
        return None


def _strip_injected(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in _CLIENT_INJECTED}


def apply_litellm_proxy_kwargs(
    kwargs: dict[str, Any], *, partner_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Stamp proxy auth and drop console-injected / tenant metadata.

    La limpieza es incondicional: ni ``partner_id``/``api_key``/``api_base``
    inyectados por el cliente ni ``metadata.tenant_id`` pueden salir de aquí,
    vaya el hop al proxy o al vendor. Lo único condicional es el estampado:
    sin proxy (ADR-036) no se toca ``api_base``/``api_key`` y litellm usa las
    credenciales de vendor del entorno.
    """
    target = resolve_litellm_proxy_optional(
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
    if target is None:
        return kwargs
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


_ADMIN_TIMEOUT_S = 10.0


def _admin_secret_arn() -> str:
    """ARN string only. Cloud injects ``LITELLM_ADMIN_SECRET_ARN``, not the master."""
    return _env("LITELLM_ADMIN_SECRET_ARN", "NEXUS_LITELLM_ADMIN_SECRET_ARN")


def _parse_master_secret(raw: str) -> str:
    """SecretString is ``{"LITELLM_MASTER_KEY": "..."}``. Never log."""
    stripped = raw.strip()
    if not stripped:
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    value = parsed.get("LITELLM_MASTER_KEY")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _fetch_litellm_admin_secret() -> str:
    """GetSecretValue of ``LITELLM_ADMIN_SECRET_ARN``. Request-time. Not for tests."""
    arn = _admin_secret_arn()
    if not arn:
        return ""
    try:
        import boto3
    except Exception:
        return ""
    try:
        region = _env("AWS_REGION", "AWS_DEFAULT_REGION")
        kwargs: dict[str, Any] = {}
        if region:
            kwargs["region_name"] = region
        client = boto3.client("secretsmanager", **kwargs)
        resp = client.get_secret_value(SecretId=arn)
    except Exception as exc:
        log.warning("llm_proxy.admin_secret_unreadable", error=type(exc).__name__)
        return ""
    secret = resp.get("SecretString")
    if not isinstance(secret, str):
        return ""
    return _parse_master_secret(secret)


def litellm_admin_master() -> str:
    """Master for ``/key/block`` / ``/key/unblock``. Tests mock this helper.

    ``LITELLM_ADMIN_SECRET_ARN`` is the ARN. The process calls GetSecretValue
    at request time. The master is never read from env (no valueFrom).
    """
    return _fetch_litellm_admin_secret()


async def litellm_admin_call(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    """Internal hop to the proxy. Master never leaves this process."""
    master = await asyncio.to_thread(litellm_admin_master)
    if not master:
        raise LLMProxyUnavailable("missing litellm admin master")
    base = proxy_api_base()
    if not base:
        raise LLMProxyUnavailable("missing LITELLM_PROXY_API_BASE")
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=_ADMIN_TIMEOUT_S) as client:
            resp = await client.request(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {master}",
                    "Content-Type": "application/json",
                },
                json=json_body,
                params=params,
            )
    except (httpx.HTTPError, TimeoutError, OSError) as exc:
        raise LLMProxyUnavailable("proxy unreachable", retryable=True) from exc
    if resp.status_code == 401:
        raise LLMProxyUnavailable("proxy unauthorized")
    return resp


def _blocked_from_info(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    info = payload.get("info")
    if isinstance(info, dict) and isinstance(info.get("blocked"), bool):
        return bool(info["blocked"])
    if isinstance(payload.get("blocked"), bool):
        return bool(payload["blocked"])
    return False


async def partner_key_is_blocked(partner_id: uuid.UUID) -> bool:
    """``/key/info`` for this partner's VK. Missing VK → unavailable."""
    key = virtual_key_for(partner_id)
    if not key:
        raise LLMProxyUnavailable("missing partner virtual key")
    resp = await litellm_admin_call("GET", "/key/info", params={"key": key})
    if resp.status_code >= 400:
        raise LLMProxyUnavailable(
            "proxy unauthorized" if resp.status_code == 401 else "proxy rejected"
        )
    try:
        payload: object = resp.json()
    except ValueError as exc:
        raise LLMProxyUnavailable("proxy rejected") from exc
    return _blocked_from_info(payload)


async def partner_key_set_blocked(partner_id: uuid.UUID, blocked: bool) -> None:
    """``/key/block`` or ``/key/unblock`` for this partner's VK only."""
    key = virtual_key_for(partner_id)
    if not key:
        raise LLMProxyUnavailable("missing partner virtual key")
    path = "/key/block" if blocked else "/key/unblock"
    resp = await litellm_admin_call("POST", path, json_body={"key": key})
    if resp.status_code >= 400:
        raise LLMProxyUnavailable(
            "proxy unauthorized" if resp.status_code == 401 else "proxy rejected"
        )
