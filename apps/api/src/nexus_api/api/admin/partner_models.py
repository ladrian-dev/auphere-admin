"""Admin F2 — allowlist de modelos del partner del path."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.admin.partners import _admin_actor, _get_partner_or_404
from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.partner_allowlist import read_allowlist, reconcile_agents, replace_allowlist
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.respond_catalog import OFFERABLE_MODEL_ID_SET, OFFERABLE_MODELS
from nexus_api.core.security import require_admin_token
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.admin_models import AdminModelItemOut, AdminModelsIn, AdminModelsOut

log = structlog.get_logger(__name__)

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
            for model_id, display in OFFERABLE_MODELS
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
    redis: Redis = Depends(get_redis),
) -> AdminModelsOut:
    """Sustituye la allowlist y reconcilia las elecciones de los agentes (spec 016, R5.3;
    spec 065, 8.2).

    Los agentes con un modelo elegido por el partner que queda fuera pasan al modelo por
    defecto DESPUÉS de confirmar la lista nueva —desde su siguiente turno— y el partner
    recibe ``agent.model_reset`` por cada uno. Las elecciones de Auphere no cambian.
    """
    for model_id in body.model_ids:
        if model_id not in OFFERABLE_MODEL_ID_SET:
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
    # Spec 065 (8.2): los agentes con un modelo elegido por el partner que ya no está.
    for reset in await reconcile_agents(partner_id, allowed, actor=_admin_actor(actor)):
        try:
            await redis.publish(PROMOTE_CHANNEL, f"{reset.tenant_id}:{reset.agent_id}")
        except Exception as exc:
            log.warning(
                "partner_models.invalidate_failed", agent_id=str(reset.agent_id), error=str(exc)
            )
    return _models_out(allowed)
