"""``/console/clients/{ref}/agents/{agent_id}/draft`` — the agent's one draft
(spec 047, historia 2; ``contracts/console-api.md`` §4).

- ``GET`` answers the draft — or the version a draft would start from —
  with its ``revision`` and an ``ETag``.
- ``PATCH`` writes into it and **requires** ``If-Match`` with the revision
  the screen read. A stale one gets ``412`` with ``current`` (the draft as it
  is now) and ``changes`` (who changed which fields since): nothing of the
  refused write lands and nothing of the first one is lost (R3.3).
- ``DELETE`` discards it: the agent goes back to its active version, which
  nobody touches (R3.5).
- ``GET …/versions`` is the history, «v{n} de {agente}» with author, date,
  note and the version each one started from (R3.4, R3.6).

The agent is always one of the client's (garantía 9): an agent of another
client, or an archived one, is the same opaque 404 as one that does not
exist. Writes queue on the agent row (``AgentConfigService.lock_draft``).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response, status

from nexus_api.core.errors import AgentConfigConflict
from nexus_api.db.models import Agent, AgentConfig, AgentStatus
from nexus_api.services.agent_audience import (
    AudienceError,
    AudienceLocked,
    AudienceNumber,
    apply_audience,
    is_locked_template,
)
from nexus_api.services.agent_config_service import (
    AgentConfigService,
    DraftRevisionConflict,
    NoDraft,
)
from nexus_api.services.agent_console_policy import merge_console_policy
from nexus_api.services.agent_payment_review import Reviewer, ReviewerError, apply_reviewers
from nexus_api.services.agent_spec.schema import dump

from .agent_drafts import draft_screens, draft_written, ensure_draft, load_view
from .agent_settings import _audience_out, _payment_review_out, _settings_of
from .audit import _human_actor
from .deps import ClientScope, client_scope
from .schemas_agent_draft import (
    AgentDraftOut,
    AgentDraftPatchIn,
    AgentVersionEntryOut,
    DraftAction,
    DraftChangeOut,
    DraftConflictOut,
    DraftTestsOut,
)

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")

AgentIdPath = Path(..., description="One of the client's agents.")


def agent_in_path(*required: str) -> Callable[..., Awaitable[ClientScope]]:
    """``client_scope`` plus the agent of the path: an active agent of THIS
    client or a 404. RLS already hides another client's agent; the tenant is
    checked too so the guarantee never rests on one layer alone."""
    client_dep = client_scope(*required)

    async def _dependency(
        agent_id: uuid.UUID = AgentIdPath,
        scope: ClientScope = Depends(client_dep),
    ) -> ClientScope:
        found = await scope.session.get(Agent, agent_id)
        if (
            found is None
            or found.tenant_id != scope.tenant.id
            or found.status != AgentStatus.ACTIVE.value
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
        return replace(scope, agent_id=agent_id)

    return _dependency


# ── If-Match ───────────────────────────────────────────────────────────


def etag(revision: int) -> str:
    return f'"{revision}"'


def parse_revision(if_match: str | None) -> int | None:
    """``"5"``, ``W/"5"`` or ``5`` → 5; absent → ``None``; anything else → 400."""
    if if_match is None:
        return None
    raw = if_match.strip()
    if raw.startswith("W/"):
        raw = raw[2:]
    raw = raw.strip().strip('"')
    if not raw.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "revision_invalid"}
        )
    return int(raw)


def _required_revision(if_match: str | None) -> int:
    revision = parse_revision(if_match)
    if revision is None:
        # Contract §Convenciones: writes require If-Match.
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={"code": "revision_required"},
        )
    return revision


# ── reading ────────────────────────────────────────────────────────────


def _who(actor: str | None) -> str | None:
    return _human_actor(actor) if actor else None


async def _agent(scope: ClientScope) -> Agent:
    assert scope.agent_id is not None  # agent_in_path set it
    agent = await scope.session.get(Agent, scope.agent_id)
    assert agent is not None
    return agent


async def _number_of(scope: ClientScope, config_id: uuid.UUID | None) -> int | None:
    if config_id is None:
        return None
    base = await scope.session.get(AgentConfig, config_id)
    return base.agent_version_number if base is not None else None


async def draft_out(scope: ClientScope) -> AgentDraftOut:
    agent = await _agent(scope)
    view = await load_view(scope)
    target = view.target
    revision = await AgentConfigService(scope.session).draft_revision(agent.id)
    allowed: list[DraftAction] = []
    if "agents:write" in scope.principal.permissions:
        allowed = ["edit", "discard"] if view.draft is not None else ["edit"]
    return AgentDraftOut(
        agent_id=agent.id,
        agent_name=agent.name,
        revision=revision,
        exists=view.draft is not None,
        number=target.agent_version_number if target else None,
        version=target.version if target else None,
        status=cast(Any, target.status.value) if target else None,
        base_number=await _number_of(scope, target.base_version_id if target else None),
        active_number=view.active.agent_version_number if view.active else None,
        active_version=view.active.version if view.active else None,
        author=_who(target.created_by) if target else None,
        created_at=target.created_at if target else None,
        updated_at=target.updated_at if target else None,
        change_note=target.note if target else None,
        system_prompt=target.system_prompt_rendered if target else "",
        tools=list(target.tools or []) if target else [],
        skills=[str(s["skill_id"]) for s in (target.runtime_skills or []) if s.get("skill_id")]
        if target
        else [],
        settings=_settings_of(target),
        audience=_audience_out(target),
        payment_review=_payment_review_out(target),
        screens=draft_screens(view),
        allowed=allowed,
        spec=_spec_doc(target, agent),
        tests=await _tests_out(scope, agent.id),
    )


def _spec_doc(target: AgentConfig | None, agent: Agent) -> dict[str, Any] | None:
    from .agent_spec_drafts import spec_of

    try:
        spec = spec_of(target, agent)
    except Exception:  # pragma: no cover - a stored spec that no longer validates
        return dict(target.spec) if target is not None and target.spec else None
    return dump(spec) if spec is not None else None


async def _tests_out(scope: ClientScope, agent_id: uuid.UUID) -> DraftTestsOut | None:
    from nexus_api.services.testing.suites import get_suite, list_tests

    suite = await get_suite(scope.session, agent_id)
    if suite is None:
        return None
    tests = [t for t in await list_tests(scope.session, suite) if t.not_applicable_reason is None]
    return DraftTestsOut(
        total=len(tests),
        stale=sum(1 for t in tests if t.stale),
        case=sum(1 for t in tests if t.kind == "case"),
        sector=sum(1 for t in tests if t.kind == "sector"),
    )


async def _conflict(scope: ClientScope, expected: int) -> HTTPException:
    """The 412 of R3.3: the draft as it is now and what changed after the
    revision the writer read. Raised before anything was written."""
    current = await draft_out(scope)
    changes = await AgentConfigService(scope.session).changes_since(current.agent_id, expected)
    body = DraftConflictOut(
        code="revision_conflict",
        current=current,
        changes=[
            DraftChangeOut(
                revision=c.revision,
                kind=c.kind,
                by=_human_actor(c.actor),
                at=c.at,
                fields=c.fields,
            )
            for c in changes
        ],
    )
    return HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail=body.model_dump(mode="json"),
        headers={"ETag": etag(current.revision)},
    )


@router.get("/draft", response_model=AgentDraftOut)
async def get_draft(
    response: Response, scope: ClientScope = Depends(agent_in_path("agents:read"))
) -> AgentDraftOut:
    """The draft (``exists``) or, without one, the version it would start from."""
    out = await draft_out(scope)
    response.headers["ETag"] = etag(out.revision)
    return out


# ── writing ────────────────────────────────────────────────────────────


def _apply_policies(
    policies: dict[str, Any], body: AgentDraftPatchIn, *, actor: str, seed_template_ref: str | None
) -> dict[str, Any]:
    """The settings, «A quién responde» and the payment reviewers onto the
    draft's policies, through the same translations the settings editor uses
    (spec 024 and 025), with its same error codes."""
    if body.settings is not None:
        policies = merge_console_policy(policies, body.settings, actor=actor)
    if body.audience is not None:
        try:
            policies = apply_audience(
                policies,
                mode=body.audience.mode,
                numbers=[AudienceNumber(n.phone, n.name) for n in body.audience.numbers],
                locked=is_locked_template(seed_template_ref),
            )
        except AudienceLocked as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code}
            ) from exc
        except AudienceError as exc:
            raise _coded_422(exc.code, getattr(exc, "phone", None)) from exc
    if body.payment_review is not None:
        try:
            policies = apply_reviewers(
                policies, [Reviewer(n.phone, n.name) for n in body.payment_review.reviewers]
            )
        except ReviewerError as exc:
            raise _coded_422(exc.code, getattr(exc, "phone", None)) from exc
    return policies


def _coded_422(code: str, phone: str | None) -> HTTPException:
    detail: dict[str, Any] = {"code": code}
    if phone is not None:
        detail["phone"] = phone
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


@router.patch(
    "/draft",
    response_model=AgentDraftOut,
    responses={
        400: {"description": "revision_invalid"},
        412: {"model": DraftConflictOut, "description": "revision_conflict"},
        422: {"description": "Invalid tools, audience or payment reviewers."},
        428: {"description": "revision_required"},
    },
)
async def patch_draft(
    body: AgentDraftPatchIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> AgentDraftOut:
    """Write into the draft, creating it from the active version if needed."""
    expected = _required_revision(if_match)
    if body.spec is not None:
        return await _patch_spec(body, response, scope, expected)
    service = AgentConfigService(scope.session)
    if body.tools is not None:
        try:
            await service._validate_tools(body.tools)
        except AgentConfigConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
    try:
        draft, _created = await ensure_draft(scope, expected_revision=expected)
    except DraftRevisionConflict as exc:
        raise await _conflict(scope, exc.expected) from None
    if body.system_prompt is not None:
        draft.system_prompt_rendered = body.system_prompt
    if body.tools is not None:
        draft.tools = list(dict.fromkeys(body.tools))
    draft.policies = _apply_policies(
        dict(draft.policies or {}),
        body,
        actor=scope.principal.actor,
        seed_template_ref=draft.seed_template_ref,
    )
    if body.note is not None:
        draft.note = body.note.strip() or None
    await draft_written(scope, draft)
    out = await draft_out(scope)
    response.headers["ETag"] = etag(out.revision)
    return out


async def _patch_spec(
    body: AgentDraftPatchIn, response: Response, scope: ClientScope, expected: int
) -> AgentDraftOut:
    """The AgentSpec as a whole: validated without a model (15.4, 16.1) and
    compiled into the draft's prompt (16.2). Its tests stop counting (17.7)."""
    from nexus_api.services.agent_spec.validator import (
        load_context,
        problems_out,
        validate_spec,
    )

    from .agent_spec_drafts import current_spec, write_spec

    assert body.spec is not None
    before, _cfg = await current_spec(scope)
    legacy_chars = (
        len(before.instructions.legacy_text or "")
        if before is not None and before.mode == "instructions" and before.instructions
        else None
    )
    ctx = await load_context(
        scope.session, partner_id=scope.principal.partner.id, legacy_chars=legacy_chars
    )
    spec, problems = validate_spec(body.spec, ctx, author="person")
    if spec is None or problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "spec_invalid", "problems": problems_out(problems)},
        )
    try:
        draft = await write_spec(scope, spec, expected_revision=expected)
    except DraftRevisionConflict as exc:
        raise await _conflict(scope, exc.expected) from None
    if body.note is not None:
        draft.note = body.note.strip() or None
    out = await draft_out(scope)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.delete(
    "/draft",
    response_model=AgentDraftOut,
    responses={
        404: {"description": "no_draft"},
        412: {"model": DraftConflictOut, "description": "revision_conflict"},
        428: {"description": "revision_required"},
    },
)
async def discard_draft(
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> AgentDraftOut:
    """Discard the draft; the answer is the agent as it is now, without one."""
    expected = _required_revision(if_match)
    assert scope.agent_id is not None
    try:
        await AgentConfigService(scope.session).discard_draft(
            actor=scope.principal.actor, agent_id=scope.agent_id, expected_revision=expected
        )
    except DraftRevisionConflict as exc:
        raise await _conflict(scope, exc.expected) from None
    except NoDraft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "no_draft"}
        ) from None
    out = await draft_out(scope)
    response.headers["ETag"] = etag(out.revision)
    return out


# ── history ────────────────────────────────────────────────────────────


@router.get("/versions", response_model=list[AgentVersionEntryOut])
async def list_versions(
    scope: ClientScope = Depends(agent_in_path("agents:read")),
) -> list[AgentVersionEntryOut]:
    """Every version of the agent, newest first: «v{n}», who wrote it and
    when, who published it, its note and the version it started from."""
    versions = await AgentConfigService(scope.session).list_versions(agent_id=scope.agent_id)
    numbers = {v.id: v.agent_version_number for v in versions}
    return [
        AgentVersionEntryOut(
            number=v.agent_version_number,
            version=v.version,
            status=cast(Any, v.status.value),
            author=_who(v.created_by),
            created_at=v.created_at,
            published_at=v.promoted_at,
            published_by=_who(v.promoted_by),
            change_note=v.note,
            base_number=numbers.get(v.base_version_id) if v.base_version_id else None,
        )
        for v in versions
    ]


__all__ = ["agent_in_path", "etag", "parse_revision", "router"]
