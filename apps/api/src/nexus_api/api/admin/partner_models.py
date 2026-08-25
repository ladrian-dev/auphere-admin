"""Admin F2 — allowlist de modelos del partner del path."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.partners import _admin_actor, _get_partner_or_404
from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_allowlist import read_allowlist, replace_allowlist
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.respond_catalog import RESPOND_MODEL_ID_SET, RESPOND_MODELS
from nexus_api.core.security import require_admin_token
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.admin_models import AdminModelItemOut, AdminModelsIn, AdminModelsOut

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


def _unknown_catalog(model_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "unknown_model", "model_id": model_id},
    )


def _models_out(allowed: frozenset[str]) -> AdminModelsOut:
    return AdminModelsOut(
        items=[
            AdminModelItemOut(
                model_id=model_id,
                display_name=display,
                allowed=model_id in allowed,
            )
            for model_id, display in RESPOND_MODELS
        ]
    )


@router.get("/{partner_id}/models", response_model=AdminModelsOut)
async def get_partner_models(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> AdminModelsOut:
    """Catálogo cerrado con ``allowed`` según la allowlist del path."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        allowed = await read_allowlist(session, partner_id)
    return _models_out(allowed)


@router.put(
    "/{partner_id}/models",
    response_model=AdminModelsOut,
    responses={
        422: {"description": "id fuera del catálogo cerrado, o campos extra."},
    },
)
async def put_partner_models(
    partner_id: uuid.UUID,
    body: AdminModelsIn,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
) -> AdminModelsOut:
    """Sustituye la allowlist. No toca ``tenant_model_bindings``."""
    for model_id in body.model_ids:
        if model_id not in RESPOND_MODEL_ID_SET:
            raise _unknown_catalog(model_id)

    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        before = sorted(await read_allowlist(session, partner_id))
        after = sorted(await replace_allowlist(session, partner_id, body.model_ids))
        await AuditRepository(session).record(
            actor=_admin_actor(actor),
            action="partner_models.set",
            target=f"partner:{partner_id}",
            before={"model_ids": before},
            after={"model_ids": after},
            platform=True,
        )
        allowed = frozenset(after)
    return _models_out(allowed)
