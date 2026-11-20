"""``/console/models`` y el binding ``respond`` de un cliente.

Catálogo cerrado de tres ids. El PUT hace upsert en
``tenant_model_bindings`` (rol ``respond``) y no habla con LiteLLM: la
virtual key del partner ya tiene los tres modelos.

Spec 016 (US4): la lista trae los pesos de cuota y un coste relativo en
créditos (el más económico es x1) para que el partner elija sabiendo lo que
gasta; el binding dice si el plan todavía lo permite y qué responde si no;
cambiarlo deja ``console.model.update`` en la auditoría del cliente.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_allowlist import read_allowlist
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.respond_catalog import (
    RESPOND_MODEL_IDS,
    RESPOND_MODELS,
    SOL_MODEL_ID,
)
from nexus_api.db.models.model_profile import ModelProfile
from nexus_api.services.agent_model import LINES

from .deps import ClientRef, resolve_mapping
from .schemas_models import ConsoleModelOut, ModelWeightsOut

router = APIRouter()
log = structlog.get_logger(__name__)


def _unknown_model(model_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "unknown_model", "model_id": model_id},
    )


def _catalog_display() -> dict[str, str]:
    """Spec 047: the offer is data, refreshed at start; read it when used."""
    return dict(RESPOND_MODELS)


#: Lo que responde sin binding: el defecto del worker (``llm_respond_model``).
FALLBACK_MODEL_ID = SOL_MODEL_ID


def _fallback_display() -> str:
    return _catalog_display().get(FALLBACK_MODEL_ID, FALLBACK_MODEL_ID)


async def _profiles(session: AsyncSession, model_ids: list[str]) -> dict[str, ModelProfile]:
    """``model_profiles`` de los ids pedidos (tabla de plataforma, sin RLS)."""
    if not model_ids:
        return {}
    rows = (
        await session.scalars(
            sa.select(ModelProfile).where(
                ModelProfile.model_id.in_(model_ids), ModelProfile.status == "active"
            )
        )
    ).all()
    return {str(p.model_id): p for p in rows}


def _weights(profile: ModelProfile | None) -> ModelWeightsOut:
    """Pesos por carril; sin perfil o sin pesos, el neutro (1)."""
    if profile is None:
        return ModelWeightsOut(input=1.0, cache_read=1.0, output=1.0)
    legacy = float(profile.quota_weight) if profile.quota_weight is not None else 1.0
    return ModelWeightsOut(
        input=float(profile.quota_weight_input)
        if profile.quota_weight_input is not None
        else legacy,
        cache_read=float(profile.quota_weight_cache_read)
        if profile.quota_weight_cache_read is not None
        else legacy,
        output=float(profile.quota_weight_output)
        if profile.quota_weight_output is not None
        else legacy,
    )


def relative_costs(weights: dict[str, ModelWeightsOut]) -> dict[str, int]:
    """Peso de salida normalizado al menor de la lista, redondeado: el más
    económico es x1. Es la cifra que el partner ve antes de elegir (R5.1)."""
    positive = [w.output for w in weights.values() if w.output > 0]
    floor = min(positive) if positive else 1.0
    return {
        model_id: max(1, round(w.output / floor)) if w.output > 0 else 1
        for model_id, w in weights.items()
    }


@router.get("/models", response_model=list[ConsoleModelOut])
async def list_console_models(
    principal: ConsolePrincipal = Depends(require_console_principal("agents:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConsoleModelOut]:
    """Catálogo cerrado ∩ allowlist del partner, con su coste en créditos."""
    async with session.begin():
        await apply_partner_to_session(session, principal.partner.id)
        allowed = await read_allowlist(session, principal.partner.id)
        listed = [model_id for model_id in RESPOND_MODEL_IDS if model_id in allowed]
        profiles = await _profiles(session, listed)
    weights = {model_id: _weights(profiles.get(model_id)) for model_id in listed}
    costs = relative_costs(weights)
    return [
        ConsoleModelOut(
            model_id=model_id,
            display_name=str(profiles[model_id].display_name)
            if model_id in profiles
            else _catalog_display()[model_id],
            relative_cost=costs[model_id],
            weights=weights[model_id],
            provider=model_id.split("/", 1)[0],
            line=LINES.get(model_id),
        )
        for model_id in listed
    ]


@router.put(
    "/clients/{ref}/model",
    responses={
        404: {"description": "Unknown client reference."},
        410: {"description": "client_model_retired: the model is chosen per agent (spec 065)."},
    },
)
async def put_client_model(
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("agents:write")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Spec 065 (requisito 12.4): retirado. El modelo de respuesta es de cada agente
    (``PUT …/agents/{agent_id}/model``). El cliente se resuelve antes, para que el de otro
    partner siga siendo el 404 opaco."""
    await resolve_mapping(session, principal, ref)
    raise HTTPException(status_code=status.HTTP_410_GONE, detail={"code": "client_model_retired"})


async def _invalidate(redis: Redis, tenant_id: uuid.UUID) -> None:
    """Mismo canal que el promote: el binding viaja en el ``AgentBundle``."""
    try:
        await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    except Exception as exc:
        log.warning("console_model.invalidate_failed", tenant_id=str(tenant_id), error=str(exc))
