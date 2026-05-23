"""Admin endpoints for the Anthropic Skills bundle (Fase D).

The admin UI lists the skills available on this deploy (i.e. the
``apps/worker/skills/`` directory shipped with the wheel) and which of
them have been uploaded to the Anthropic workspace (manifest at
``apps/worker/skills/uploaded.json``). The operator picks from that
list when configuring a STAGED ``agent_config``.

Skills uploaded but missing from the local source are NOT returned —
the source tree is the canonical list.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends

from nexus_api.core.security import require_admin_token
from nexus_api.schemas.agent_config import AvailableSkillOut

router = APIRouter()


# Resolve the worker's skills dir relative to the api package. The wheel
# layout puts ``apps/worker/skills/`` at the repo root, sister of
# ``apps/api/``. In dev with editable installs this resolves correctly.
# In a production wheel build the deployment should COPY the skills dir
# into the api image too — out of scope for this endpoint.
# skills.py lives at apps/api/src/nexus_api/api/admin/skills.py — 6
# levels up is the repo root. Computed once at import.
_REPO_ROOT = Path(__file__).resolve().parents[6]
_SKILLS_DIR = _REPO_ROOT / "apps" / "worker" / "skills"
_MANIFEST_PATH = _SKILLS_DIR / "uploaded.json"


def _parse_skill_md(skill_dir: Path) -> dict[str, str] | None:
    """Read minimal frontmatter from ``SKILL.md``. Returns ``None`` if the
    file is missing or malformed — the admin lists only well-formed
    skills."""
    md_path = skill_dir / "SKILL.md"
    if not md_path.is_file():
        return None
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    out: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def _load_manifest() -> dict[str, dict[str, str]]:
    """Return ``{skill_name: {skill_id, version}}`` from ``uploaded.json``.

    Empty / missing manifest → ``{}``: the UI then shows every local
    skill with ``skill_id=None`` so the operator knows uploading is the
    next step.
    """
    if not _MANIFEST_PATH.is_file():
        return {}
    try:
        raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    skills = raw.get("skills") or {}
    return skills if isinstance(skills, dict) else {}


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
    out: list[AvailableSkillOut] = []
    if not _SKILLS_DIR.is_dir():
        return out
    manifest = _load_manifest()
    for entry in sorted(_SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        meta = _parse_skill_md(entry)
        if meta is None or "name" not in meta:
            continue
        name = meta["name"]
        uploaded = manifest.get(name) or {}
        out.append(
            AvailableSkillOut(
                name=name,
                description=meta.get("description", ""),
                local_version=meta.get("version", ""),
                skill_id=uploaded.get("skill_id") or None,
                uploaded_version=uploaded.get("version") or None,
            )
        )
    return out
