from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_redis, scoped_session_from_path
from nexus_api.core.errors import AgentConfigConflict
from nexus_api.core.security import require_admin_token
from nexus_api.schemas.agent_config import (
    AgentConfigBundle,
    AgentConfigOut,
    AgentConfigStageIn,
)
from nexus_api.services import AgentConfigService
from nexus_api.services.templating import (
    SeedTemplateNotFound,
    SeedTemplatePlaceholderMissing,
    list_seed_templates,
    load_seed_template,
    render_seed_template,
)

router = APIRouter()
log = structlog.get_logger()


# Pub/sub channel that the worker subscribes to in order to invalidate its
# AgentLoader cache. Centralised here so the worker imports the same constant
# (architecture/agent-isolation.md, garantía 5 — promote without redeploy).
PROMOTE_CHANNEL = "nexus:agent_config:promote"


async def _publish_promote(redis: Redis, tenant_id: uuid.UUID) -> None:
    try:
        await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    except Exception as exc:
        # Stale-cache risk only — log and move on. The promote already
        # committed; worst case the worker keeps the previous version until
        # its next miss.
        log.warning("agent_config.promote_publish_failed", tenant_id=str(tenant_id), error=str(exc))


@router.get(
    "/tenants/{tenant_id}/agent-config",
    response_model=AgentConfigBundle,
    dependencies=[Depends(require_admin_token)],
)
async def get_agent_config(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> AgentConfigBundle:
    svc = AgentConfigService(session)
    versions = await svc.list_versions()
    active = await svc.get_active()
    return AgentConfigBundle(
        active=AgentConfigOut.model_validate(active) if active else None,
        versions=[AgentConfigOut.model_validate(v) for v in versions],
    )


@router.put(
    "/tenants/{tenant_id}/agent-config",
    response_model=AgentConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def stage_agent_config(
    tenant_id: uuid.UUID,
    body: AgentConfigStageIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.stage_new_version(
            actor=f"admin:{actor[:8]}",
            system_prompt_rendered=body.system_prompt_rendered,
            channels=body.channels,
            tools=body.tools,
            policies=body.policies,
            seed_template_ref=body.seed_template_ref,
            kg_schema_id=body.kg_schema_id,
        )
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentConfigOut.model_validate(config)


@router.post(
    "/tenants/{tenant_id}/agent-config/{version}/promote",
    response_model=AgentConfigOut,
)
async def promote_agent_config(
    tenant_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.promote(version, actor=f"admin:{actor[:8]}")
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    out = AgentConfigOut.model_validate(config)
    # Notify any running worker so its AgentLoader cache picks up the new
    # active version on the next turn. Best-effort; see _publish_promote.
    await _publish_promote(redis, tenant_id)
    return out


@router.post(
    "/tenants/{tenant_id}/agent-config/{version}/rollback",
    response_model=AgentConfigOut,
)
async def rollback_agent_config(
    tenant_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.rollback(version, actor=f"admin:{actor[:8]}")
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    out = AgentConfigOut.model_validate(config)
    await _publish_promote(redis, tenant_id)
    return out


# ── Seed-template bootstrap (Block J) ──────────────────────────────────────
#
# Phase 1 onboarding: after the wizard creates the tenant + connects
# WhatsApp, Lee opens /tenants/[id]/agent and clicks "Aplicar plantilla
# barbershop_v1". The panel posts the placeholders gathered by the form
# (tenant.address, tenant.business_hours_label, optional overrides) and
# the backend renders the seed prompt + recommended tools + merged
# policies, then stages the result as agent_config v1. Lee reviews and
# promotes from the same UI. There is no auto-promote — the operator
# always has the last word.


class SeedTemplateOut(BaseModel):
    name: str
    version: str
    display_name: str
    tools_required: list[str]
    policies_default: dict[str, Any]


class FromSeedIn(BaseModel):
    """POST /agent-config/from-seed payload."""

    model_config = ConfigDict(extra="forbid")

    seed_template_ref: str = Field(min_length=1, max_length=80)
    placeholders: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/seed-templates",
    response_model=list[SeedTemplateOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_seed_templates_endpoint() -> list[SeedTemplateOut]:
    """List the seed templates the wizard can apply.

    Phase 1 ships only ``barbershop_v1`` (Cultor Barber). New verticals
    drop YAML files in ``services/templating/seeds/`` — no code change.
    """
    out: list[SeedTemplateOut] = []
    for name in list_seed_templates():
        tpl = load_seed_template(name)
        out.append(
            SeedTemplateOut(
                name=tpl.name,
                version=tpl.version,
                display_name=tpl.display_name,
                tools_required=tpl.tools_required,
                policies_default=tpl.policies_default,
            )
        )
    return out


@router.post(
    "/tenants/{tenant_id}/agent-config/from-seed",
    response_model=AgentConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def stage_agent_config_from_seed(
    tenant_id: uuid.UUID,
    body: FromSeedIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    """Render the seed template and stage the result as a new version.

    The output is ``status='staged'`` — Lee promotes from /tenants/[id]/
    agent after reviewing the rendered prompt. ``seed_template_ref`` is
    persisted on the row so future audits know which template seeded it.
    """
    try:
        template = load_seed_template(body.seed_template_ref)
    except SeedTemplateNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"seed template {body.seed_template_ref!r} not found",
        ) from exc

    try:
        rendered = render_seed_template(template, placeholders=body.placeholders)
    except SeedTemplatePlaceholderMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    svc = AgentConfigService(session)
    try:
        config = await svc.stage_new_version(
            actor=f"admin:{actor[:8]}",
            system_prompt_rendered=rendered.system_prompt,
            channels=[],
            tools=rendered.tools,
            policies=rendered.policies,
            seed_template_ref=rendered.seed_template_ref,
        )
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentConfigOut.model_validate(config)
