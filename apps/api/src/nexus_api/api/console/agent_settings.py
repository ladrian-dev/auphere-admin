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
from nexus_api.services.agent_console_policy import (
    ConsolePolicy,
    merge_console_policy,
    read_console_policy,
)

from .agent_drafts import DraftView, ensure_draft, load_view
from .deps import ClientScope, client_scope
from .schemas_agent_tools import AgentSettingsIn, AgentSettingsOut, AgentSettingsSaved

router = APIRouter(prefix="/clients/{ref}/agent/settings")


def _settings_of(cfg: AgentConfig | None) -> ConsolePolicy:
    if cfg is None:
        return ConsolePolicy()
    return read_console_policy(cfg.policies) or ConsolePolicy()


def _out(view: DraftView) -> AgentSettingsOut:
    target = view.target
    return AgentSettingsOut(
        version=target.version if target else None,
        version_status=cast(Any, target.status.value) if target else None,
        active_version=view.active.version if view.active else None,
        has_draft=view.has_draft,
        settings=_settings_of(target),
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
    draft.policies = merge_console_policy(
        dict(draft.policies or {}), body.settings, actor=scope.principal.actor
    )
    await scope.session.flush()
    view = await load_view(scope)
    base = _out(view)
    return AgentSettingsSaved(**base.model_dump(), draft_created=created)


__all__ = ["router"]
