"""Catalogue of the Anthropic Skills bundled with this deploy (Fase D).

Single source of truth for BOTH the backoffice (``api/admin/skills.py``)
and the partner console (``api/console/skills.py``, CP-14): the
``apps/worker/skills/<name>/SKILL.md`` frontmatter is the list, the
manifest ``apps/worker/skills/uploaded.json`` maps a name to the
``skill_id``/``version`` uploaded to the Anthropic workspace.

A skill without a manifest entry exists but is not activatable — the
runtime needs the ``skill_id``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# ``services/skills_catalog.py`` lives at
# apps/api/src/nexus_api/services/skills_catalog.py — 5 levels up is the
# repo root. Computed once at import; tests may monkeypatch ``SKILLS_DIR``.
_REPO_ROOT = Path(__file__).resolve().parents[5]
SKILLS_DIR = _REPO_ROOT / "apps" / "worker" / "skills"
MANIFEST_NAME = "uploaded.json"


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    local_version: str
    skill_id: str | None
    uploaded_version: str | None

    @property
    def activatable(self) -> bool:
        return self.skill_id is not None


def parse_skill_md(skill_dir: Path) -> dict[str, str] | None:
    """Read minimal frontmatter from ``SKILL.md``. Returns ``None`` if the
    file is missing or malformed — callers list only well-formed skills."""
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


def load_manifest(skills_dir: Path | None = None) -> dict[str, dict[str, str]]:
    """``{skill_name: {skill_id, version}}`` from ``uploaded.json``; ``{}``
    when the manifest is missing or malformed."""
    path = (skills_dir or SKILLS_DIR) / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    skills = raw.get("skills") or {}
    return skills if isinstance(skills, dict) else {}


def list_skills(skills_dir: Path | None = None) -> list[SkillEntry]:
    """Every well-formed skill in the source tree, sorted by directory
    name, joined with its upload status."""
    base = skills_dir or SKILLS_DIR
    if not base.is_dir():
        return []
    manifest = load_manifest(base)
    out: list[SkillEntry] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        meta = parse_skill_md(entry)
        if meta is None or "name" not in meta:
            continue
        name = meta["name"]
        uploaded = manifest.get(name) or {}
        out.append(
            SkillEntry(
                name=name,
                description=meta.get("description", ""),
                local_version=meta.get("version", ""),
                skill_id=uploaded.get("skill_id") or None,
                uploaded_version=uploaded.get("version") or None,
            )
        )
    return out


__all__ = [
    "MANIFEST_NAME",
    "SKILLS_DIR",
    "SkillEntry",
    "list_skills",
    "load_manifest",
    "parse_skill_md",
]
