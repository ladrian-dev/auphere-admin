"""Shared WhatsApp template (HSM) listing — used by the admin panel and
the embed surface (ADR-028).

Source of truth is Meta's Cloud API; the local
``whatsapp_template_status`` mirror only tracks approval webhooks.
Credentials come from ``tenant_credentials`` INSIDE the caller's scoped
session — RLS is the only authority on which row is read.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError, MetaClient
from nexus_channels.whatsapp_meta.credentials import (
    MetaCredentials,
    MetaCredentialsRepository,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings

log = structlog.get_logger(__name__)


class TemplateOut(BaseModel):
    """One template as Meta reports it. ``components`` is passed through
    verbatim — clients render body text + variables + buttons from it."""

    id: str | None = None
    name: str
    language: str
    category: str | None = None
    status: str | None = None
    quality_score: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)


# Per-WABA template cache. A single-recipient send resolves the template
# live on every call, so a campaign of N recipients meant N Graph API
# round-trips fired back-to-back — 141 of them in the New Air run, which
# exhausted the HTTP pool and failed the batch mid-way.
#
# Keyed by waba_id (never by tenant alone): the value is derived purely
# from that WABA, and the key comes from credentials already resolved
# under RLS, so one tenant cannot read another's entry.
#
# The TTL is deliberately short. ``resolve_template`` treats Meta as the
# source of truth precisely so a template paused between listing and
# sending is caught; caching for minutes would trade that guarantee away.
# Seconds collapse the burst while keeping the window small enough that a
# pause is caught on the next batch rather than the next hour.
_TEMPLATE_CACHE_TTL_SECONDS = 30.0
_template_cache: dict[str, tuple[float, list[TemplateOut]]] = {}


def invalidate_template_cache(waba_id: str | None = None) -> None:
    """Drop cached templates — all of them, or one WABA's.

    Call after any write that changes what Meta would return (create,
    delete, or an approval webhook), so the panel never shows a template
    the operator just changed in its stale state.
    """
    if waba_id is None:
        _template_cache.clear()
    else:
        _template_cache.pop(waba_id, None)


async def require_meta_credentials(session: AsyncSession) -> MetaCredentials:
    creds = await MetaCredentialsRepository(session).get()
    if creds is None or not creds.waba_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este cliente no tiene WhatsApp conectado por Meta. "
                "Conectá el número con Embedded Signup primero."
            ),
        )
    return creds


def build_meta_client() -> MetaClient:
    settings = get_settings()
    return MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )


def meta_error_to_http(exc: MetaAPIError, *, context: str) -> HTTPException:
    """Map a Cloud API error to a clean client-facing HTTPException."""
    code = getattr(exc, "code", None)
    status_code = getattr(exc, "status_code", None) or 502
    detail = f"Meta rechazó {context}: {exc}"
    if code is not None:
        detail += f" (code {code})"
    http_status = (
        status.HTTP_422_UNPROCESSABLE_ENTITY
        if 400 <= int(status_code) < 500
        else status.HTTP_502_BAD_GATEWAY
    )
    return HTTPException(status_code=http_status, detail=detail)


async def fetch_templates(
    session: AsyncSession, *, use_cache: bool = True
) -> tuple[list[TemplateOut], str]:
    """Live template list for the scoped tenant. Returns ``(templates,
    waba_id)``. Raises 409 without Meta credentials; Meta API errors map
    to 422/502.

    Results are cached per WABA for a few seconds (see
    ``_TEMPLATE_CACHE_TTL_SECONDS``) so a fan-out of sends does not fire
    one Graph API call per recipient. Pass ``use_cache=False`` where a
    stale read would be wrong — right after creating or deleting a
    template, for instance.
    """
    creds = await require_meta_credentials(session)

    if use_cache:
        cached = _template_cache.get(creds.waba_id)
        if cached is not None and (time.monotonic() - cached[0]) < _TEMPLATE_CACHE_TTL_SECONDS:
            log.debug(
                "templates.fetch.cache_hit",
                waba_id=creds.waba_id,
                count=len(cached[1]),
                age_seconds=round(time.monotonic() - cached[0], 2),
            )
            return list(cached[1]), creds.waba_id

    # Every miss is one Graph API round-trip made while the caller holds
    # an open DB transaction. A run of these in quick succession is the
    # shape of the pool exhaustion that aborted the New Air campaign, so
    # the miss — not the hit — is the event worth seeing at INFO.
    started = time.monotonic()
    client = build_meta_client()
    try:
        try:
            payload = await client.list_templates(waba_id=creds.waba_id, access_token=creds.bisuat)
        except MetaAPIError as exc:
            log.warning(
                "templates.fetch.failed",
                waba_id=creds.waba_id,
                status_code=getattr(exc, "status_code", None),
                code=getattr(exc, "code", None),
                error=str(exc),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            raise meta_error_to_http(exc, context="el listado de plantillas") from exc
    finally:
        await client.close()
    log.info(
        "templates.fetch.cache_miss",
        waba_id=creds.waba_id,
        use_cache=use_cache,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )

    templates: list[TemplateOut] = []
    for raw in payload.get("data") or []:
        if not isinstance(raw, dict):
            continue
        templates.append(
            TemplateOut(
                id=raw.get("id"),
                name=str(raw.get("name") or ""),
                language=str(raw.get("language") or ""),
                category=raw.get("category"),
                status=raw.get("status"),
                quality_score=(
                    (raw.get("quality_score") or {}).get("score")
                    if isinstance(raw.get("quality_score"), dict)
                    else raw.get("quality_score")
                ),
                components=[c for c in (raw.get("components") or []) if isinstance(c, dict)],
            )
        )

    _template_cache[creds.waba_id] = (time.monotonic(), list(templates))
    return templates, creds.waba_id
