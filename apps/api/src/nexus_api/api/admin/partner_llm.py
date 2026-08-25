"""Admin F2 — block/activar la VK LiteLLM del partner del path."""

from __future__ import annotations

import uuid
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.partners import _admin_actor, _get_partner_or_404
from nexus_api.api.deps import get_db_session
from nexus_api.core.llm_proxy import (
    LLM_PROXY_UNAVAILABLE,
    LLMProxyUnavailable,
    partner_key_is_blocked,
    partner_key_set_blocked,
    virtual_key_for,
)
from nexus_api.core.security import require_admin_token
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.admin_models import AdminLlmBlockIn, AdminLlmOut

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": LLM_PROXY_UNAVAILABLE},
    )


def _raise_admin(exc: LLMProxyUnavailable) -> NoReturn:
    """401 from OSS is fail-closed 401. Missing VK / down is 409."""
    if exc.reason == "proxy unauthorized":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "proxy_unauthorized"},
        ) from exc
    raise _unavailable() from exc


@router.get(
    "/{partner_id}/llm",
    response_model=AdminLlmOut,
    responses={409: {"description": "Sin VK o el proxy no responde."}},
)
async def get_partner_llm(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> AdminLlmOut:
    """Estado blocked de la VK del path. Sin keys."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
    if not virtual_key_for(partner_id):
        raise _unavailable()
    try:
        blocked = await partner_key_is_blocked(partner_id)
    except LLMProxyUnavailable as exc:
        _raise_admin(exc)
    return AdminLlmOut(blocked=blocked)


@router.post(
    "/{partner_id}/llm/block",
    response_model=AdminLlmOut,
    responses={
        409: {"description": "Sin VK o el proxy no responde."},
        422: {"description": "cuerpo extra o partner_id en body."},
    },
)
async def post_partner_llm_block(
    partner_id: uuid.UUID,
    body: AdminLlmBlockIn,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
) -> AdminLlmOut:
    """POST /key/block o /key/unblock de la VK del path. A no toca B."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
    if not virtual_key_for(partner_id):
        raise _unavailable()
    try:
        await partner_key_set_blocked(partner_id, body.blocked)
    except LLMProxyUnavailable as exc:
        _raise_admin(exc)

    action = "llm.block" if body.blocked else "llm.unblock"
    async with session.begin():
        await AuditRepository(session).record(
            actor=_admin_actor(actor),
            action=action,
            target=f"partner:{partner_id}",
            before={"blocked": not body.blocked},
            after={"blocked": body.blocked},
            platform=True,
        )
    return AdminLlmOut(blocked=body.blocked)
