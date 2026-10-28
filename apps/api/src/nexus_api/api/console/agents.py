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
from nexus_api.services.agent_console_policy import has_disclosure_decision

from .agent_drafts import draft_diff, draft_screens, draft_written, ensure_draft, load_view
from .deps import ClientScope, agent_scope
from .schemas import AgentBundleOut, AgentDraftIn, AgentPublishIn, AgentVersionOut, DraftDiffOut

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
    versions = await service.list_versions(agent_id=scope.agent_id)
    active = await service.get_active(agent_id=scope.agent_id)
    return AgentBundleOut(
        active_version=active.version if active else None,
        versions=[_version_out(v) for v in versions],
        # Spec 017 R3.1: la ficha necesita saber DÓNDE está el cambio sin
        # abrir cada pantalla a ver si difiere.
        draft_screens=draft_screens(await load_view(scope)),
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
async def get_agent(scope: ClientScope = Depends(agent_scope("agents:read"))) -> AgentBundleOut:
    return await _bundle(scope)


@router.get(
    "/draft-diff",
    response_model=DraftDiffOut,
    responses={404: {"description": "There is no draft to compare."}},
)
async def get_draft_diff(scope: ClientScope = Depends(agent_scope("agents:read"))) -> DraftDiffOut:
    """What the draft changes against the version serving right now (R3.2).

    Reading it is a read: an analyst who cannot publish still has to be able
    to see what someone else staged. Publishing is a different permission on
    a different route.
    """
    view = await load_view(scope)
    if view.draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_draft")
    return DraftDiffOut.model_validate(draft_diff(view))


@router.post(
    "/versions",
    response_model=AgentVersionOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Draft conflicts with the current state."}},
)
async def stage_version(
    body: AgentDraftIn,
    scope: ClientScope = Depends(agent_scope("agents:write")),
) -> AgentVersionOut:
    """Write the prompt (and, if sent, the tools) into the agent's draft.

    Spec 047 (R3.1): this used to stage a NEW version copied from the
    active one, so the settings saved a minute earlier stayed behind in a
    version nobody would publish. Now it writes into THE draft — created
    on demand as a full copy of the active version, runtime wiring
    included — and everything else in it stays.

    Policies are never accepted raw from the console (platform keys such
    as ``admin_access``/``llm`` live there). CP-31: a draft written from
    the console always carries an explicit AI-disclosure decision.
    """
    if body.tools is not None:
        try:
            await AgentConfigService(scope.session)._validate_tools(body.tools)
        except AgentConfigConflict as exc:
            # Unknown tools / invalid combination — the draft is not storable.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
    draft, _created = await ensure_draft(scope)
    draft.system_prompt_rendered = body.system_prompt
    if body.tools is not None:
        draft.tools = list(dict.fromkeys(body.tools))
    await draft_written(scope, draft)
    return _version_out(draft)


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
    body: AgentPublishIn | None = None,
    scope: ClientScope = Depends(agent_scope("agents:write")),
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
    if target is None or (scope.agent_id is not None and target.agent_id != scope.agent_id):
        # Spec 030: with ``?agent=``, a version of another agent does not exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    if not has_disclosure_decision(target.policies):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DISCLOSURE_REQUIRED_DETAIL)
    if not (target.system_prompt_rendered or "").strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMPTY_PROMPT_DETAIL)
    # Spec 047 (T093, 23.7): the same gate as «Guardar» in the new console,
    # the operator panel and the partner API.
    from nexus_api.services import publishing

    payload = body or AgentPublishIn()
    try:
        done = await publishing.publish(
            scope.session,
            agent_id=target.agent_id,
            version=target,
            actor=scope.principal.actor,
            role=scope.principal.role,
            partner_id=scope.principal.partner.id,
            accept_normal_failures=payload.accept_normal_failures,
            override_reason=payload.override_reason,
            origin=payload.origin,
        )
    except publishing.GateBlocked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "gate_blocked", "gate": exc.gate.to_json()},
        ) from exc
    except publishing.OverrideForbidden as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "override_forbidden"}
        ) from exc
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=_conflict_status(exc), detail=str(exc)) from exc
    cfg = done.version
    await _publish_promote(redis, scope)
    return _version_out(cfg)


@router.post(
    "/versions/{version}/rollback",
    response_model=AgentVersionOut,
    responses={404: {"description": "No such version."}, 409: {"description": "Already active."}},
)
async def rollback_version(
    version: int,
    scope: ClientScope = Depends(agent_scope("agents:write")),
    redis: Redis = Depends(get_redis),
) -> AgentVersionOut:
    service = AgentConfigService(scope.session)
    if scope.agent_id is not None:
        target = await service.configs.get_by_version(version)
        if target is None or target.agent_id != scope.agent_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    try:
        cfg = await service.rollback(version, actor=scope.principal.actor)
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=_conflict_status(exc), detail=str(exc)) from exc
    await _publish_promote(redis, scope)
    return _version_out(cfg)
