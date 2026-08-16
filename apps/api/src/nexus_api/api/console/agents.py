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
from nexus_api.services.agent_console_policy import (
    has_disclosure_decision,
    with_disclosure_default,
)

from .agent_drafts import copy_runtime_fields
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
    """Stage a new (non-active) version. Channels, policies and runtime
    capabilities are copied from the active version so a partner editing
    the prompt cannot accidentally drop the runtime wiring.

    CP-31: a version staged from the console always carries an explicit
    AI-disclosure decision — the default (``enabled=true``) is written
    here, attributed to the actor, unless the policies already have one.
    """
    service = AgentConfigService(scope.session)
    active = await service.get_active()
    actor = scope.principal.actor
    # Policies are never accepted raw from the console (platform keys such
    # as ``admin_access``/``llm`` live there); the partner edits ONLY
    # ``policies.console`` through the validated settings endpoint.
    policies = dict(active.policies) if active else {}
    try:
        cfg = await service.stage_new_version(
            actor=actor,
            system_prompt_rendered=body.system_prompt,
            channels=list(active.channels) if active else [],
            tools=(body.tools if body.tools is not None else list(active.tools) if active else []),
            policies=with_disclosure_default(policies, actor=actor),
            seed_template_ref=active.seed_template_ref if active else None,
            kg_schema_id=active.kg_schema_id if active else None,
        )
    except AgentConfigConflict as exc:
        # Unknown tools / invalid combination — the draft is not storable.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    copy_runtime_fields(active, cfg)
    return _version_out(cfg)


DISCLOSURE_REQUIRED_DETAIL = (
    "This version has no AI-disclosure decision (AI Act art. 50). Open the agent "
    "settings, choose whether the assistant discloses it is an AI (default: yes) "
    "and save — that creates a draft you can publish."
)
EMPTY_PROMPT_DETAIL = "This version has an empty system prompt. Write the prompt before publishing."


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
    """Make ``version`` the active one.

    CP-31 hard rule: a version without an explicit ``policies.console.
    ai_disclosure`` decision cannot go live from the console — 409 with an
    actionable message. Versions staged through the console always have
    one (default ``enabled=true``); the rule catches versions staged
    elsewhere (backoffice, seeds) so the partner takes the decision.
    """
    service = AgentConfigService(scope.session)
    target = await service.configs.get_by_version(version)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    if not has_disclosure_decision(target.policies):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DISCLOSURE_REQUIRED_DETAIL)
    if not (target.system_prompt_rendered or "").strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMPTY_PROMPT_DETAIL)
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
