"""Admin endpoints — WhatsApp message template (HSM) management.

The operator manages the tenant's pre-approved templates from the panel
instead of the Meta Business Manager UI:

- ``GET    /admin/tenants/{id}/whatsapp/templates`` — live list from the
  Cloud API (source of truth is Meta; the local
  ``whatsapp_template_status`` mirror only tracks approval webhooks).
- ``POST   /admin/tenants/{id}/whatsapp/templates`` — submit a new
  template for Meta review (status starts at PENDING). Since spec 075
  (requisito 10) it takes the console's ``TemplateCreateIn`` and goes to
  Meta the console's way (``submit_template``): one shape, one builder.
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

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.console.schemas_channels import (
    SystemVariablesOut,
    TemplateCreateIn,
    TemplateEditIn,
    TemplateEditOut,
)
from nexus_api.api.console.templates import (
    NEGATIVE_STATUSES,
    load_verdicts,
    suggested_action_for,
)
from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog, OperatorAccount
from nexus_api.schemas.whatsapp_templates import TemplateContentIn, TemplateContentOut
from nexus_api.services.whatsapp_template_edit import edit_template, row_extras
from nexus_api.services.whatsapp_templates import (
    TemplateOut,
    fetch_templates,
    invalidate_template_cache,
    submit_template,
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


class AdminTemplateOut(TemplateOut):
    """Spec 075: the same per-row edit facts the console gets (9.3)."""

    edit_blocker: str | None = None
    draft: TemplateContentOut | None = None
    version: str | None = None
    system_variables: SystemVariablesOut | None = None
    #: Meta's literal reason for a negative verdict (the webhook mirror) and
    #: the short code of what to fix: the panel shows them while editing (1.2).
    rejection_reason: str | None = None
    suggested_action: str = "none"


class TemplateListOut(BaseModel):
    templates: list[AdminTemplateOut]
    waba_id: str


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
    # The operator panel is the one surface that must never show a stale
    # list — it is where a human goes to check whether Meta approved a
    # template. The send path takes the cached read; this one does not.
    templates, waba_id = await fetch_templates(session, use_cache=False)
    verdicts = await load_verdicts(session, waba_id)
    rows: list[AdminTemplateOut] = []
    for t in templates:
        v = verdicts.get((t.name, t.language))
        st = (t.status or (v.status if v is not None else None) or "").upper()
        reason = v.reason if v is not None and st in NEGATIVE_STATUSES else None
        rows.append(
            AdminTemplateOut(
                **t.model_dump(),
                **row_extras(t),
                rejection_reason=reason or None,
                suggested_action=suggested_action_for(st, reason),
            )
        )
    return TemplateListOut(templates=rows, waba_id=waba_id)


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
    # Spec 075 (10.5): the console's shape and the console's way to Meta (9.3).
    result = await submit_template(session, body)

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

    invalidate_template_cache(creds.waba_id)

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
    log.info("whatsapp_templates.deleted", tenant_id=str(tenant_id), name=name)
    return TemplateDeleteOut(
        name=name,
        deleted=bool(result.get("success", True)),
        audit_log_id=audit.id,
    )


@router.put(
    "/tenants/{tenant_id}/whatsapp/templates/{name}/{language}",
    response_model=TemplateEditOut,
    dependencies=[Depends(require_admin_token)],
)
async def edit_whatsapp_template(
    tenant_id: uuid.UUID,
    name: str,
    language: str,
    body: TemplateEditIn,
    # Before the scoped session: both share the request's DB session, and
    # ``require_operator`` opens (and closes) its own transaction on it.
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> TemplateEditOut:
    """Spec 075: the operator edits with the console's rules (9.1, 9.3). The
    audit names the person behind the panel session (``X-Operator-Id``),
    never the shared admin token (8.4)."""
    if not _TEMPLATE_NAME_RE.match(name) or not re.match(
        r"^[A-Za-z]{2,3}(_[A-Za-z0-9]{2,8})?$", language
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="nombre de plantilla inválido"
        )
    content = TemplateContentIn(**body.model_dump(exclude={"version", "confirm"}))
    result = await edit_template(
        session,
        name=name,
        language=language,
        body=content,
        version=body.version,
        confirm=body.confirm,
        actor=operator_actor(operator),
        audit_action="admin.template.edit",
    )
    return TemplateEditOut(
        name=result.name,
        language=result.language,
        changed=result.changed,
        status=result.status,
        category=result.category,
    )
