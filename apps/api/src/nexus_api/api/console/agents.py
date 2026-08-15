"""``/console/clients/{ref}/agent`` — the client's agent: versions, draft,
publish, rollback (CP-11/CP-12 backend).

Built on ``AgentConfigService`` — the same service the backoffice uses,
so promotion semantics (one ACTIVE version, audit rows, worker cache
reload) are identical. What the partner gets is a *view* on it: no
runtime capability toggles (memory tool, grader, MCP servers — platform
decisions), no seed re-apply, no eval override.

Every stage/publish/rollback leaves its ``agent_config.*`` row in
``audit_log`` (written by the service) with the console actor
(``console:<email>``) — the audit page renders it as "maría@… published
agent version 7 for Clínica X" (CP-12 acceptance). No second row is
written here: one event, one row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.core.errors import AgentConfigConflict
from nexus_api.db.models import AgentConfig
from nexus_api.services.agent_config_service import AgentConfigService

from .deps import ClientScope, client_scope
from .schemas import AgentBundleOut, AgentDraftIn, AgentVersionOut

router = APIRouter(prefix="/clients/{ref}/agent")


def _version_out(cfg: AgentConfig) -> AgentVersionOut:
    return AgentVersionOut(
        version=cfg.version,
        status=cfg.status.value,
        system_prompt=cfg.system_prompt_rendered,
        tools=list(cfg.tools or []),
        seed_template_ref=cfg.seed_template_ref,
        created_by=cfg.created_by,
        created_at=cfg.created_at,
        promoted_at=cfg.promoted_at,
        promoted_by=cfg.promoted_by,
    )


async def _bundle(scope: ClientScope) -> AgentBundleOut:
    service = AgentConfigService(scope.session)
    versions = await service.list_versions()
    active = await service.get_active()
    return AgentBundleOut(
        active_version=active.version if active else None,
        versions=[_version_out(v) for v in versions],
    )


def _conflict_status(exc: AgentConfigConflict) -> int:
    """The service raises one exception type for "no such version" and for
    real conflicts; the message tells them apart. 404 vs 409 matters to a
    UI that offers a retry."""
    return status.HTTP_404_NOT_FOUND if "not found" in str(exc) else status.HTTP_409_CONFLICT


async def _publish_promote(redis: Redis, scope: ClientScope) -> None:
    # Same channel the backoffice uses — a worker with a warm cache for
    # this tenant reloads without a redeploy.
    from nexus_api.api.admin.agent_configs import _publish_promote as publish

    await publish(redis, scope.tenant.id)


@router.get("", response_model=AgentBundleOut)
async def get_agent(scope: ClientScope = Depends(client_scope("agents:read"))) -> AgentBundleOut:
    return await _bundle(scope)


@router.post(
    "/versions",
    response_model=AgentVersionOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Draft conflicts with the current state."}},
)
async def stage_version(
    body: AgentDraftIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> AgentVersionOut:
    """Stage a new (non-active) version. Channels and policies are copied
    from the active version so a partner editing the prompt cannot
    accidentally drop the runtime wiring."""
    service = AgentConfigService(scope.session)
    active = await service.get_active()
    try:
        cfg = await service.stage_new_version(
            actor=scope.principal.actor,
            system_prompt_rendered=body.system_prompt,
            channels=list(active.channels) if active else [],
            tools=(body.tools if body.tools is not None else list(active.tools) if active else []),
            policies=(
                body.policies
                if body.policies is not None
                else dict(active.policies)
                if active
                else {}
            ),
            seed_template_ref=active.seed_template_ref if active else None,
            kg_schema_id=active.kg_schema_id if active else None,
        )
    except AgentConfigConflict as exc:
        # Unknown tools / invalid combination — the draft is not storable.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _version_out(cfg)


@router.post(
    "/versions/{version}/publish",
    response_model=AgentVersionOut,
    responses={404: {"description": "No such version."}, 409: {"description": "Conflict."}},
)
async def publish_version(
    version: int,
    scope: ClientScope = Depends(client_scope("agents:write")),
    redis: Redis = Depends(get_redis),
) -> AgentVersionOut:
    """Make ``version`` the active one."""
    service = AgentConfigService(scope.session)
    try:
        cfg = await service.promote(version, actor=scope.principal.actor)
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=_conflict_status(exc), detail=str(exc)) from exc
    await _publish_promote(redis, scope)
    return _version_out(cfg)


@router.post(
    "/versions/{version}/rollback",
    response_model=AgentVersionOut,
    responses={404: {"description": "No such version."}, 409: {"description": "Already active."}},
)
async def rollback_version(
    version: int,
    scope: ClientScope = Depends(client_scope("agents:write")),
    redis: Redis = Depends(get_redis),
) -> AgentVersionOut:
    service = AgentConfigService(scope.session)
    try:
        cfg = await service.rollback(version, actor=scope.principal.actor)
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=_conflict_status(exc), detail=str(exc)) from exc
    await _publish_promote(redis, scope)
    return _version_out(cfg)
