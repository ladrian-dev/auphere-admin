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
from nexus_channels.whatsapp_meta import MetaAPIError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog
from nexus_api.services.whatsapp_templates import (
    TemplateOut,
    fetch_templates,
)
from nexus_api.services.whatsapp_templates import (
    build_meta_client as _build_client,
)
from nexus_api.services.whatsapp_templates import (
    meta_error_to_http as _meta_error_to_http,
)
from nexus_api.services.whatsapp_templates import (
    require_meta_credentials as _require_meta_credentials,
)

router = APIRouter()
log = structlog.get_logger()

# Meta template names: lowercase alphanumeric + underscores, max 512.
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")

_VALID_CATEGORIES = ("MARKETING", "UTILITY", "AUTHENTICATION")


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


@router.get(
    "/tenants/{tenant_id}/whatsapp/templates",
    response_model=TemplateListOut,
    dependencies=[Depends(require_admin_token)],
)
async def list_whatsapp_templates(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> TemplateListOut:
    templates, waba_id = await fetch_templates(session)
    return TemplateListOut(templates=templates, waba_id=waba_id)


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
