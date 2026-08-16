"""``/console/clients/{ref}/channels/whatsapp/templates`` — CP-18.

Meta is the source of truth for the template list
(``services/whatsapp_templates.fetch_templates``); the local
``whatsapp_template_status`` mirror — fed by the
``message_template_status_update`` webhook — is what holds the **literal
rejection reason** Meta attaches to a verdict. This router joins the two
so a partner sees, per template: state, quality, Meta's exact words and a
short ``suggested_action`` code the UI translates.

Writes (create / delete) go straight to the Cloud API with the tenant's
own BISUAT (read under RLS) and leave ``console.template.create|delete``
audit rows. Without Meta credentials every route answers 409 with the
"connect WhatsApp first" message — never 500.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.conversation import WhatsAppTemplateStatus
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.whatsapp_templates import (
    TemplateOut,
    build_meta_client,
    fetch_templates,
    invalidate_template_cache,
    meta_error_to_http,
    require_meta_credentials,
)

from .deps import ClientScope, client_scope
from .schemas_channels import (
    SuggestedAction,
    TemplateCreateIn,
    TemplateCreateOut,
    TemplateDeleteOut,
    TemplateListOut,
    TemplateRowOut,
)

router = APIRouter(prefix="/clients/{ref}/channels/whatsapp/templates")

_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")

#: Verdicts that carry a reason worth showing (Meta's + the mirror's
#: lowercase vocabulary, compared upper-cased).
NEGATIVE_STATUSES = frozenset({"REJECTED", "PAUSED", "DISABLED", "FLAGGED"})

# Meta rejection reasons (``reason`` of message_template_status_update)
# → what the partner should do next. Unknown reasons fall back to
# ``contact_support`` when the template is rejected, ``none`` otherwise.
_SUGGESTED: dict[str, SuggestedAction] = {
    "INVALID_FORMAT": "fix_format",
    "INCORRECT_CATEGORY": "change_category",
    "TAG_CONTENT_MISMATCH": "change_category",
    "PROMOTIONAL": "remove_promotional",
    "ABUSIVE_CONTENT": "rewrite_content",
    "SCAM": "rewrite_content",
    "NONE": "none",
}


def suggested_action_for(status_value: str | None, rejection_reason: str | None) -> SuggestedAction:
    """Pure mapping, unit-tested without network."""
    st = (status_value or "").upper()
    if st in {"PENDING", "IN_APPEAL"}:
        return "wait_review"
    if st not in NEGATIVE_STATUSES:
        return "none"
    key = (rejection_reason or "").strip().upper()
    if key in _SUGGESTED:
        return _SUGGESTED[key]
    # Meta sometimes sends free text ("... variable ... sample ...").
    if "VARIABLE" in key or "SAMPLE" in key or "PARAMETER" in key:
        return "add_variables_samples"
    if "FORMAT" in key:
        return "fix_format"
    if "CATEGORY" in key:
        return "change_category"
    if "PROMOTION" in key or "MARKETING" in key:
        return "remove_promotional"
    return "contact_support"


def merge_rows(
    templates: list[TemplateOut], verdicts: dict[tuple[str, str], WhatsAppTemplateStatus]
) -> list[TemplateRowOut]:
    """Join Meta's live list with the local verdict mirror. Pure."""
    rows: list[TemplateRowOut] = []
    for tpl in templates:
        v = verdicts.get((tpl.name, tpl.language))
        # The mirror only carries a reason for negative verdicts; if Meta
        # now reports APPROVED the old reason is stale and must not show.
        st = (tpl.status or (v.status if v else None) or "").upper() or None
        rejection = v.reason if v is not None and st in NEGATIVE_STATUSES else None
        rows.append(
            TemplateRowOut(
                id=tpl.id,
                name=tpl.name,
                language=tpl.language,
                category=tpl.category,
                status=st,
                quality_score=tpl.quality_score,
                components=tpl.components,
                rejection_reason=rejection or None,
                suggested_action=suggested_action_for(st, rejection),
                last_event_at=v.last_event_at if v is not None else None,
            )
        )
    return rows


async def load_verdicts(
    session: AsyncSession, waba_id: str
) -> dict[tuple[str, str], WhatsAppTemplateStatus]:
    result = await session.execute(
        sa.select(WhatsAppTemplateStatus).where(WhatsAppTemplateStatus.waba_id == waba_id)
    )
    return {(r.template_name, r.language): r for r in result.scalars()}


def _summary(rows: list[TemplateRowOut]) -> TemplateListOut:
    return TemplateListOut(
        items=rows,
        approved=sum(1 for r in rows if r.status == "APPROVED"),
        rejected=sum(1 for r in rows if r.status in NEGATIVE_STATUSES),
        pending=sum(1 for r in rows if r.status in {"PENDING", "IN_APPEAL"}),
    )


@router.get(
    "",
    response_model=TemplateListOut,
    responses={409: {"description": "WhatsApp is not connected for this client."}},
)
async def list_templates(
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> TemplateListOut:
    # The console is where a human checks whether Meta approved — no cache.
    templates, waba_id = await fetch_templates(scope.session, use_cache=False)
    verdicts = await load_verdicts(scope.session, waba_id)
    return _summary(merge_rows(templates, verdicts))


@router.post("", response_model=TemplateCreateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreateIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> TemplateCreateOut:
    creds = await require_meta_credentials(scope.session)
    components = body.to_components()
    client = build_meta_client()
    try:
        try:
            result = await client.create_template(
                waba_id=creds.waba_id,
                access_token=creds.bisuat,
                name=body.name,
                language=body.language,
                category=body.category,
                components=components,
            )
        except MetaAPIError as exc:
            raise meta_error_to_http(exc, context="la creación de la plantilla") from exc
    finally:
        await client.close()
    invalidate_template_cache(creds.waba_id)
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.template.create",
        target=f"template:{body.name}",
        after={
            "name": body.name,
            "language": body.language,
            "category": body.category,
            "meta_id": result.get("id"),
            "status": result.get("status"),
        },
    )
    return TemplateCreateOut(
        id=result.get("id"),
        name=body.name,
        status=result.get("status"),
        category=result.get("category") or body.category,
    )


@router.delete("/{name}", response_model=TemplateDeleteOut)
async def delete_template(
    name: str,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> TemplateDeleteOut:
    if not _TEMPLATE_NAME_RE.match(name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid template name")
    creds = await require_meta_credentials(scope.session)
    client = build_meta_client()
    try:
        try:
            result = await client.delete_template(
                waba_id=creds.waba_id, access_token=creds.bisuat, name=name
            )
        except MetaAPIError as exc:
            raise meta_error_to_http(exc, context="el borrado de la plantilla") from exc
    finally:
        await client.close()
    invalidate_template_cache(creds.waba_id)
    deleted = bool(result.get("success", True))
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.template.delete",
        target=f"template:{name}",
        before={"name": name},
        after={"deleted": deleted},
    )
    return TemplateDeleteOut(name=name, deleted=deleted)


__all__ = ["merge_rows", "router", "suggested_action_for"]
