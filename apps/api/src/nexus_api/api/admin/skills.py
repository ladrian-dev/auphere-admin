"""Admin endpoints for the Anthropic Skills bundle (Fase D).

The admin UI lists the skills available on this deploy (i.e. the
``apps/worker/skills/`` directory shipped with the wheel) and which of
them have been uploaded to the Anthropic workspace (manifest at
``apps/worker/skills/uploaded.json``). The operator picks from that
list when configuring a STAGED ``agent_config``.

Skills uploaded but missing from the local source are NOT returned —
the source tree is the canonical list. The catalogue itself lives in
``services/skills_catalog.py`` (shared with the partner console, CP-14).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from nexus_api.core.security import require_admin_token
from nexus_api.schemas.agent_config import AvailableSkillOut
from nexus_api.services.skills_catalog import list_skills

router = APIRouter()


@router.get(
    "/skills/available",
    response_model=list[AvailableSkillOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_available_skills() -> list[AvailableSkillOut]:
    """List every skill bundled with this deploy + its upload status.

    Used by the admin agent editor to render the skill picker. The
    response is small (a handful of skills) so we recompute it on every
    call — no cache. Operations rebuilds the manifest after every
    ``upload_skill.py`` run.
    """
    return [
        AvailableSkillOut(
            name=s.name,
            description=s.description,
            local_version=s.local_version,
            skill_id=s.skill_id,
            uploaded_version=s.uploaded_version,
        )
        for s in list_skills()
    ]
