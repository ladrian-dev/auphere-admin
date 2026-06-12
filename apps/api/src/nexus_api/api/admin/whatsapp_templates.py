"""Admin endpoints — WhatsApp message template (HSM) management.

The operator manages the tenant's pre-approved templates from the panel
instead of the Meta Business Manager UI:

- ``GET    /admin/tenants/{id}/whatsapp/templates`` — live list from the
  Cloud API (source of truth is Meta; the local
  ``whatsapp_template_status`` mirror only tracks approval webhooks).
- ``POST   /admin/tenants/{id}/whatsapp/templates`` — submit a new
  template for Meta review (status starts at PENDING).
- ``DELETE /admin/tenants/{id}/whatsapp/templates/{name}`` — delete a
  template (all languages of that name, per the Cloud API contract).

Credentials: the tenant's ``waba_id`` + BISUAT come from
``tenant_credentials`` (integration="meta_whatsapp") INSIDE the scoped
session — RLS is the only authority on which row is read. A tenant
without Meta credentials gets a 409 telling the operator to run
Embedded Signup first.

Every mutation writes an ``AuditLog`` row.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError, MetaClient
from nexus_channels.whatsapp_meta.credentials import (
    MetaCredentials,
    MetaCredentialsRepository,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.config import get_settings
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog

router = APIRouter()
log = structlog.get_logger()

# Meta template names: lowercase alphanumeric + underscores, max 512.
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")

_VALID_CATEGORIES = ("MARKETING", "UTILITY", "AUTHENTICATION")


class TemplateOut(BaseModel):
    """One template as Meta reports it. ``components`` is passed through
    verbatim — the panel renders body text + buttons from it."""

    id: str | None = None
    name: str
    language: str
    category: str | None = None
    status: str | None = None
    quality_score: str | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)


class TemplateListOut(BaseModel):
    templates: list[TemplateOut]
    waba_id: str


class TemplateCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=512)
    language: str = Field(default="es", min_length=2, max_length=15)
    category: str = Field(default="UTILITY")
    components: list[dict[str, Any]] = Field(
        min_length=1,
        description=(
            "Cloud API native components — e.g. "
            '[{"type":"BODY","text":"Hola {{nombre}} ..."}]'
        ),
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _TEMPLATE_NAME_RE.match(v):
            raise ValueError(
                "name must be lowercase letters, digits and underscores "
                "(e.g. reminder_24h)"
            )
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _VALID_CATEGORIES:
            raise ValueError(f"category must be one of {list(_VALID_CATEGORIES)}")
        return upper


class TemplateCreateOut(BaseModel):
    id: str | None
    name: str
    status: str | None
    category: str | None
    audit_log_id: uuid.UUID


class TemplateDeleteOut(BaseModel):
    name: str
    deleted: bool
    audit_log_id: uuid.UUID


async def _require_meta_credentials(session: AsyncSession) -> MetaCredentials:
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


def _build_client() -> MetaClient:
    settings = get_settings()
    return MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )


def _meta_error_to_http(exc: MetaAPIError, *, context: str) -> HTTPException:
    """Map a Cloud API error to a clean operator-facing HTTPException."""
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


@router.get(
    "/tenants/{tenant_id}/whatsapp/templates",
    response_model=TemplateListOut,
    dependencies=[Depends(require_admin_token)],
)
async def list_whatsapp_templates(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> TemplateListOut:
    creds = await _require_meta_credentials(session)
    client = _build_client()
    try:
        try:
            payload = await client.list_templates(
                waba_id=creds.waba_id, access_token=creds.bisuat
            )
        except MetaAPIError as exc:
            raise _meta_error_to_http(exc, context="el listado de plantillas") from exc
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
                components=[
                    c for c in (raw.get("components") or []) if isinstance(c, dict)
                ],
            )
        )
    return TemplateListOut(templates=templates, waba_id=creds.waba_id)


@router.post(
    "/tenants/{tenant_id}/whatsapp/templates",
    response_model=TemplateCreateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_whatsapp_template(
    tenant_id: uuid.UUID,
    body: TemplateCreateIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TemplateCreateOut:
    creds = await _require_meta_credentials(session)
    client = _build_client()
    try:
        try:
            result = await client.create_template(
                waba_id=creds.waba_id,
                access_token=creds.bisuat,
                name=body.name,
                language=body.language,
                category=body.category,
                components=body.components,
            )
        except MetaAPIError as exc:
            raise _meta_error_to_http(exc, context="la creación de la plantilla") from exc
    finally:
        await client.close()

    audit = AuditLog(
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
        action="channel.whatsapp.template_created",
        target=f"template:{body.name}",
        before_json=None,
        after_json={
            "name": body.name,
            "language": body.language,
            "category": body.category,
            "meta_id": result.get("id"),
            "status": result.get("status"),
        },
    )
    session.add(audit)
    await session.flush()
    log.info(
        "whatsapp_templates.created",
        tenant_id=str(tenant_id),
        name=body.name,
        status=result.get("status"),
    )
    return TemplateCreateOut(
        id=result.get("id"),
        name=body.name,
        status=result.get("status"),
        category=result.get("category") or body.category,
        audit_log_id=audit.id,
    )


@router.delete(
    "/tenants/{tenant_id}/whatsapp/templates/{name}",
    response_model=TemplateDeleteOut,
)
async def delete_whatsapp_template(
    tenant_id: uuid.UUID,
    name: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TemplateDeleteOut:
    if not _TEMPLATE_NAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="nombre de plantilla inválido",
        )
    creds = await _require_meta_credentials(session)
    client = _build_client()
    try:
        try:
            result = await client.delete_template(
                waba_id=creds.waba_id, access_token=creds.bisuat, name=name
            )
        except MetaAPIError as exc:
            raise _meta_error_to_http(exc, context="el borrado de la plantilla") from exc
    finally:
        await client.close()

    audit = AuditLog(
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
        action="channel.whatsapp.template_deleted",
        target=f"template:{name}",
        before_json={"name": name},
        after_json={"success": bool(result.get("success", True))},
    )
    session.add(audit)
    await session.flush()
    log.info(
        "whatsapp_templates.deleted", tenant_id=str(tenant_id), name=name
    )
    return TemplateDeleteOut(
        name=name,
        deleted=bool(result.get("success", True)),
        audit_log_id=audit.id,
    )
