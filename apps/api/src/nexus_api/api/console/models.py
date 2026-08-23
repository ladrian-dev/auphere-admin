"""``/console/models`` y el binding ``respond`` de un cliente.

Catálogo cerrado de tres ids. El PUT hace upsert en
``tenant_model_bindings`` (rol ``respond``) y no habla con LiteLLM: la
virtual key del partner ya tiene los tres modelos.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.respond_catalog import (
    RESPOND_MODEL_ID_SET,
    RESPOND_MODELS,
    RESPOND_ROLE,
)
from nexus_api.core.tenant_context import apply_tenant_to_session

from .deps import ClientRef, resolve_mapping
from .schemas_models import ClientModelOut, ConsoleModelOut, ModelIn

router = APIRouter()
log = structlog.get_logger(__name__)


def _unknown_model(model_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "unknown_model", "model_id": model_id},
    )


@router.get("/models", response_model=list[ConsoleModelOut])
async def list_console_models(
    _: ConsolePrincipal = Depends(require_console_principal("agents:read")),
) -> list[ConsoleModelOut]:
    """Los tres ids del catálogo cerrado. Sin ``partner_id`` ni tarifas."""
    return [
        ConsoleModelOut(model_id=model_id, display_name=display)
        for model_id, display in RESPOND_MODELS
    ]


@router.get(
    "/clients/{ref}/model",
    response_model=ClientModelOut,
    responses={404: {"description": "Unknown client reference."}},
)
async def get_client_model(
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("agents:read")),
    session: AsyncSession = Depends(get_db_session),
) -> ClientModelOut:
    """Binding ``respond`` de un cliente propio. El de otro partner es 404."""
    mapping = await resolve_mapping(session, principal, ref)
    async with session.begin():
        await apply_tenant_to_session(session, mapping.tenant_id)
        row = (
            (
                await session.execute(
                    sa.text(
                        """
                        SELECT p.model_id, p.display_name
                          FROM tenant_model_bindings b
                          JOIN model_profiles p ON p.id = b.model_profile_id
                         WHERE b.role = :role
                        """
                    ),
                    {"role": RESPOND_ROLE},
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        return ClientModelOut(client_ref=ref, role=RESPOND_ROLE, is_bound=False)
    return ClientModelOut(
        client_ref=ref,
        role=RESPOND_ROLE,
        model_id=str(row["model_id"]),
        display_name=str(row["display_name"]),
        is_bound=True,
    )


@router.put(
    "/clients/{ref}/model",
    response_model=ClientModelOut,
    responses={
        404: {"description": "Unknown client reference."},
        422: {"description": "model_id is not in the closed catalog, or extra keys."},
    },
)
async def put_client_model(
    body: ModelIn,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("agents:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ClientModelOut:
    """Fija el modelo ``respond`` de un cliente propio. No llama a LiteLLM."""
    if body.model_id not in RESPOND_MODEL_ID_SET:
        raise _unknown_model(body.model_id)
    mapping = await resolve_mapping(session, principal, ref)
    async with session.begin():
        await apply_tenant_to_session(session, mapping.tenant_id)
        profile = (
            (
                await session.execute(
                    sa.text(
                        "SELECT id, model_id, display_name FROM model_profiles "
                        "WHERE model_id = :m AND status = 'active'"
                    ),
                    {"m": body.model_id},
                )
            )
            .mappings()
            .first()
        )
        if profile is None:
            raise _unknown_model(body.model_id)
        await session.execute(
            sa.text(
                """
                INSERT INTO tenant_model_bindings
                    (tenant_id, role, model_profile_id, fallback_chain)
                VALUES (:t, :r, :p, CAST(:fc AS jsonb))
                ON CONFLICT (tenant_id, role) DO UPDATE
                   SET model_profile_id = EXCLUDED.model_profile_id,
                       updated_at = now()
                """
            ),
            {
                "t": str(mapping.tenant_id),
                "r": RESPOND_ROLE,
                "p": profile["id"],
                "fc": json.dumps([]),
            },
        )
    await _invalidate(redis, mapping.tenant_id)
    return ClientModelOut(
        client_ref=ref,
        role=RESPOND_ROLE,
        model_id=str(profile["model_id"]),
        display_name=str(profile["display_name"]),
        is_bound=True,
    )


async def _invalidate(redis: Redis, tenant_id: uuid.UUID) -> None:
    """Mismo canal que el promote: el binding viaja en el ``AgentBundle``."""
    try:
        await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    except Exception as exc:
        log.warning("console_model.invalidate_failed", tenant_id=str(tenant_id), error=str(exc))
