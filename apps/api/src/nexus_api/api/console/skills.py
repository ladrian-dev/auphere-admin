"""``/console/clients/{ref}/skills`` — vertical skills on/off (CP-14).

The catalogue is the ``apps/worker/skills/`` tree (``services/
skills_catalog.py``, shared with the backoffice); activation is
``agent_configs.runtime_skills`` (``[{skill_id, version}]``) written on
the DRAFT — same STAGED → publish flow as everything else the partner
edits. A skill without an uploaded ``skill_id`` is listed but not
activatable (the runtime needs the id).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, status

from nexus_api.db.models import AgentConfig
from nexus_api.services.skills_catalog import list_skills

from .agent_drafts import DraftView, ensure_draft, load_view
from .deps import ClientScope, client_scope
from .schemas_agent_tools import SkillOut, SkillsIn, SkillsOut, SkillsSaved

router = APIRouter(prefix="/clients/{ref}/skills")


def _enabled_ids(cfg: AgentConfig | None) -> set[str]:
    if cfg is None or not cfg.runtime_skills:
        return set()
    return {str(s.get("skill_id")) for s in cfg.runtime_skills if s.get("skill_id")}


def _out(view: DraftView) -> SkillsOut:
    target = view.target
    on = _enabled_ids(target)
    on_active = _enabled_ids(view.active)
    return SkillsOut(
        version=target.version if target else None,
        version_status=cast(Any, target.status.value) if target else None,
        active_version=view.active.version if view.active else None,
        has_draft=view.has_draft,
        skills=[
            SkillOut(
                name=s.name,
                description=s.description,
                version=s.uploaded_version or s.local_version,
                activatable=s.activatable,
                enabled=s.skill_id in on if s.skill_id else False,
                enabled_in_active=s.skill_id in on_active if s.skill_id else False,
            )
            for s in list_skills()
        ],
    )


@router.get("", response_model=SkillsOut)
async def get_skills(scope: ClientScope = Depends(client_scope("agents:read"))) -> SkillsOut:
    return _out(await load_view(scope))


@router.put(
    "",
    response_model=SkillsSaved,
    responses={422: {"description": "Unknown or non-activatable skill."}},
)
async def put_skills(
    body: SkillsIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> SkillsSaved:
    """Replace the enabled skills on the draft (created on demand)."""
    catalogue = {s.name: s for s in list_skills()}
    wanted = list(dict.fromkeys(body.skills))
    unknown = [n for n in wanted if n not in catalogue]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown skills: " + ", ".join(unknown),
        )
    not_uploaded = [n for n in wanted if catalogue[n].skill_id is None]
    if not_uploaded:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Skills not yet available on this deploy: " + ", ".join(not_uploaded),
        )
    draft, created = await ensure_draft(scope)
    # Keep entries the backoffice may have added with extra keys (e.g.
    # ``channels`` gating) when the skill stays enabled; rebuild the rest.
    previous = {str(s.get("skill_id")): s for s in (draft.runtime_skills or [])}
    entries: list[dict[str, Any]] = []
    for name in wanted:
        entry = catalogue[name]
        assert entry.skill_id is not None  # guarded above
        kept = previous.get(entry.skill_id)
        entries.append(
            dict(kept)
            if kept
            else {"skill_id": entry.skill_id, "version": entry.uploaded_version or "latest"}
        )
    draft.runtime_skills = entries or None
    await scope.session.flush()
    out = _out(await load_view(scope))
    return SkillsSaved(**out.model_dump(), draft_created=created)


__all__ = ["router"]
