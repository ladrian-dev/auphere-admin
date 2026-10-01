"""``/console/clients/{ref}/agent/settings`` — the structured agent editor
(CP-11) and the AI-disclosure decision (CP-31).

Reads/writes ``policies.console`` (schema in
``services/agent_console_policy.py``) on the client's DRAFT: a PUT
creates the draft as a copy of the active version if none exists, then
replaces the ``console`` object. Publishing stays CP-12's
``POST .../versions/{v}/publish``. The worker renders the object into an
"Operating policy" system-prompt block on every turn, so what the
partner saves here is what the agent follows once published.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, status

from nexus_api.core.errors import AgentConfigConflict
from nexus_api.db.models import AgentConfig
from nexus_api.services.agent_audience import (
    AudienceError,
    AudienceLocked,
    AudienceNumber,
    apply_audience,
    audience_of,
    is_locked_template,
)
from nexus_api.services.agent_console_policy import (
    ConsolePolicy,
    merge_console_policy,
    read_console_policy,
)
from nexus_api.services.agent_payment_review import (
    Reviewer,
    ReviewerError,
    apply_reviewers,
    reviewers_of,
)

from .agent_drafts import DraftView, ensure_draft, load_view
from .deps import ClientScope, client_scope
from .schemas_agent_tools import (
    AgentSettingsIn,
    AgentSettingsOut,
    AgentSettingsSaved,
    AudienceNumberOut,
    AudienceOut,
    PaymentReviewOut,
)

router = APIRouter(prefix="/clients/{ref}/agent/settings")


def _settings_of(cfg: AgentConfig | None) -> ConsolePolicy:
    if cfg is None:
        return ConsolePolicy()
    return read_console_policy(cfg.policies) or ConsolePolicy()


def _audience_out(cfg: AgentConfig | None) -> AudienceOut:
    """Spec 024: ``admin_access`` of the version being edited, as the
    console shows it. ``locked`` comes from the template the agent was
    seeded from."""
    locked = is_locked_template(cfg.seed_template_ref) if cfg else False
    audience = audience_of(cfg.policies if cfg else None, locked=locked)
    return AudienceOut(
        mode=audience.mode,
        numbers=[AudienceNumberOut(phone=n.phone, name=n.name) for n in audience.numbers],
        locked=audience.locked,
    )


def _payment_review_out(cfg: AgentConfig | None) -> PaymentReviewOut:
    """Spec 025: ``policies.payment_review`` of the version being edited."""
    return PaymentReviewOut(
        reviewers=[
            AudienceNumberOut(phone=r.phone, name=r.name)
            for r in reviewers_of(cfg.policies if cfg else None)
        ]
    )


def _out(view: DraftView) -> AgentSettingsOut:
    target = view.target
    return AgentSettingsOut(
        version=target.version if target else None,
        version_status=cast(Any, target.status.value) if target else None,
        active_version=view.active.version if view.active else None,
        has_draft=view.has_draft,
        settings=_settings_of(target),
        audience=_audience_out(target),
        payment_review=_payment_review_out(target),
    )


@router.get("", response_model=AgentSettingsOut)
async def get_settings(
    scope: ClientScope = Depends(client_scope("agents:read")),
) -> AgentSettingsOut:
    """The settings of the version being edited (draft if any, else active)."""
    return _out(await load_view(scope))


@router.put(
    "",
    response_model=AgentSettingsSaved,
    responses={409: {"description": "The draft could not be created."}},
)
async def put_settings(
    body: AgentSettingsIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> AgentSettingsSaved:
    """Replace ``policies.console`` on the draft (created on demand)."""
    try:
        draft, created = await ensure_draft(scope)
    except AgentConfigConflict as exc:  # pragma: no cover - copy of a valid version
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    policies = merge_console_policy(
        dict(draft.policies or {}), body.settings, actor=scope.principal.actor
    )
    if body.audience is not None:
        # Spec 024: the list lives in ``admin_access`` (the key the runtime
        # reads); the console rewrites it through the one translation.
        try:
            policies = apply_audience(
                policies,
                mode=body.audience.mode,
                numbers=[AudienceNumber(n.phone, n.name) for n in body.audience.numbers],
                locked=is_locked_template(draft.seed_template_ref),
            )
        except AudienceLocked as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code}
            ) from exc
        except AudienceError as exc:
            detail: dict[str, Any] = {"code": exc.code}
            phone = getattr(exc, "phone", None)
            if phone is not None:
                detail["phone"] = phone
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
            ) from exc
    if body.payment_review is not None:
        try:
            policies = apply_reviewers(
                policies,
                [Reviewer(n.phone, n.name) for n in body.payment_review.reviewers],
            )
        except ReviewerError as exc:
            detail = {"code": exc.code}
            phone = getattr(exc, "phone", None)
            if phone is not None:
                detail["phone"] = phone
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
            ) from exc
    draft.policies = policies
    await scope.session.flush()
    view = await load_view(scope)
    base = _out(view)
    return AgentSettingsSaved(**base.model_dump(), draft_created=created)


__all__ = ["router"]
