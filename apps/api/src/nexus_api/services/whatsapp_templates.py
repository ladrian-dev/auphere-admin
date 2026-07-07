"""Shared WhatsApp template (HSM) listing — used by the admin panel and
the embed surface (ADR-028).

Source of truth is Meta's Cloud API; the local
``whatsapp_template_status`` mirror only tracks approval webhooks.
Credentials come from ``tenant_credentials`` INSIDE the caller's scoped
session — RLS is the only authority on which row is read.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError, MetaClient
from nexus_channels.whatsapp_meta.credentials import (
    MetaCredentials,
    MetaCredentialsRepository,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings


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


async def fetch_templates(session: AsyncSession) -> tuple[list[TemplateOut], str]:
    """Live template list for the scoped tenant. Returns ``(templates,
    waba_id)``. Raises 409 without Meta credentials; Meta API errors map
    to 422/502."""
    creds = await require_meta_credentials(session)
    client = build_meta_client()
    try:
        try:
            payload = await client.list_templates(waba_id=creds.waba_id, access_token=creds.bisuat)
        except MetaAPIError as exc:
            raise meta_error_to_http(exc, context="el listado de plantillas") from exc
    finally:
        await client.close()

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
    return templates, creds.waba_id
