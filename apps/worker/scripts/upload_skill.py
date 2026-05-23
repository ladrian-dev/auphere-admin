"""Upload an Anthropic Skill from this repo to the workspace.

Fase D §D.3 of [[claude-platform-integration]]. Builds a zip archive
from ``apps/worker/skills/<name>/`` and POSTs it to the Anthropic
Skills API (``client.beta.skills.versions.create``). On success the
script appends an entry to ``apps/worker/skills/uploaded.json`` with
the skill_id Anthropic returned — that file is the source of truth the
runtime reads at startup.

Usage:

    # First-ever upload of a skill: create the skill_id.
    ANTHROPIC_API_KEY=sk-ant-... \\
      uv run python apps/worker/scripts/upload_skill.py \\
        --skill anti-hallucination-booking \\
        --create

    # Subsequent uploads bump the version.
    ANTHROPIC_API_KEY=sk-ant-... \\
      uv run python apps/worker/scripts/upload_skill.py \\
        --skill anti-hallucination-booking

Pre-flight checks (lint) before uploading:

- ``SKILL.md`` has a valid YAML frontmatter with ``name``,
  ``description``, ``version`` keys.
- The frontmatter ``name`` matches the directory name.
- No script in the skill dir imports ``requests`` / ``urllib`` /
  ``aiohttp`` / ``httpx`` — code_execution containers have NO network
  access (Fase D §D.6). Imports that look like network calls are
  rejected with a clear error pointing to the offending file.

The lint is conservative (substring match in source files). False
positives can be silenced with ``# upload-skill: noqa`` on the import
line, but the default is "reject and ask the operator to remove".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ── paths ────────────────────────────────────────────────────────────

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_MANIFEST = _SKILLS_DIR / "uploaded.json"

# Suspicious imports that would silently fail inside a code_execution
# container (no network). Anchored to ``import`` / ``from`` so we don't
# hit them inside comments or strings… most of the time. Tests are not
# uploaded so a test file using requests is fine.
_NETWORK_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+(requests|urllib|urllib3|aiohttp|httpx|http\.client)\b"
    r"|import\s+(requests|urllib|urllib3|aiohttp|httpx|http\.client)\b)",
    flags=re.MULTILINE,
)

# Escape hatch comment that silences the lint on a single import line.
_NOQA_MARKER = "# upload-skill: noqa"


# ── frontmatter parsing ─────────────────────────────────────────────


def _parse_frontmatter(skill_md_path: Path) -> dict[str, Any]:
    """Read the YAML frontmatter at the top of ``SKILL.md``.

    We don't take a YAML dep — the frontmatter is small and structured
    enough for a key-value line parser. Anthropic accepts JSON-ish
    metadata so missing structure is rejected up front.
    """
    text = skill_md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(
            f"{skill_md_path} must start with YAML frontmatter ('---' line)"
        )
    end = text.find("---", 3)
    if end == -1:
        raise ValueError(f"{skill_md_path} has unterminated frontmatter")
    body = text[3:end].strip()
    out: dict[str, Any] = {}
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(
                f"{skill_md_path} frontmatter line not 'key: value': {line!r}"
            )
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def _validate_frontmatter(meta: dict[str, Any], expected_name: str) -> None:
    for required in ("name", "description", "version"):
        if required not in meta:
            raise ValueError(f"SKILL.md frontmatter missing required key: {required}")
    if meta["name"] != expected_name:
        raise ValueError(
            f"SKILL.md frontmatter name={meta['name']!r} does not match "
            f"directory name {expected_name!r}"
        )


# ── network-import lint ─────────────────────────────────────────────


def _lint_skill_dir(skill_dir: Path) -> list[str]:
    """Return list of ``"<file>:<line>: <message>"`` violations.

    Walks every ``.py`` in the skill dir and checks for network imports.
    Markdown / YAML files are not scanned.
    """
    violations: list[str] = []
    for py in skill_dir.rglob("*.py"):
        rel = py.relative_to(skill_dir)
        src = py.read_text(encoding="utf-8")
        for line_no, line in enumerate(src.splitlines(), start=1):
            if _NOQA_MARKER in line:
                continue
            if _NETWORK_IMPORT_PATTERN.match(line):
                violations.append(
                    f"{rel}:{line_no}: network import detected — "
                    "code_execution containers have no network. "
                    f"Add ``{_NOQA_MARKER}`` only if you understand the "
                    "consequences."
                )
    return violations


# ── files collection for upload ────────────────────────────────────


def _collect_files(skill_dir: Path) -> list[tuple[str, bytes, str]]:
    """Walk the skill dir and return ``(filename, content, content_type)``
    tuples in the shape the Anthropic SDK expects.

    The Anthropic Skills API takes ``files`` as a list of file-like
    objects under a single top-level directory. We rebuild that
    structure here using the skill's name as the directory: each entry
    becomes ``<skill_name>/<relpath>``. The SKILL.md MUST be at the
    root of that directory.
    """
    out: list[tuple[str, bytes, str]] = []
    skill_name = skill_dir.name
    for path in skill_dir.rglob("*"):
        if path.is_dir() or path.name == ".DS_Store":
            continue
        rel = path.relative_to(skill_dir).as_posix()
        arcname = f"{skill_name}/{rel}"
        # The SDK accepts ``(filename, content, content_type)`` for
        # multipart uploads. Use ``text/markdown`` for .md and a
        # generic application/octet-stream for everything else; the
        # Skills API does not rely on Content-Type beyond logging.
        content_type = (
            "text/markdown" if path.suffix == ".md" else "application/octet-stream"
        )
        out.append((arcname, path.read_bytes(), content_type))
    return out


# ── manifest IO ─────────────────────────────────────────────────────


def _read_manifest() -> dict[str, Any]:
    if not _MANIFEST.exists():
        return {"skills": {}}
    raw = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    # Tolerate the seed shape — only the "skills" key matters.
    return {"skills": raw.get("skills") or {}}


def _write_manifest(manifest: dict[str, Any]) -> None:
    # Preserve the human-readable "_doc" key if it was there.
    existing = (
        json.loads(_MANIFEST.read_text(encoding="utf-8"))
        if _MANIFEST.exists()
        else {}
    )
    if "_doc" in existing:
        manifest["_doc"] = existing["_doc"]
    _MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ── upload ──────────────────────────────────────────────────────────


def _upload(skill_name: str, *, create: bool) -> tuple[str, str]:
    """Perform the upload, return ``(skill_id, version)``.

    Imports ``anthropic`` lazily so callers that just want to lint
    don't need the SDK installed at import time.
    """
    from anthropic import Anthropic

    client = Anthropic()
    skill_dir = _SKILLS_DIR / skill_name
    files = _collect_files(skill_dir)

    manifest = _read_manifest()
    skills = manifest["skills"]

    if create:
        if skill_name in skills:
            raise ValueError(
                f"skill {skill_name!r} already in manifest with "
                f"skill_id={skills[skill_name].get('skill_id')!r}; drop "
                "the --create flag to bump the version"
            )
        skill_obj = client.beta.skills.create(
            display_title=skill_name,
            files=files,
        )
        skill_id = skill_obj.id
    else:
        existing = skills.get(skill_name)
        if not existing or not existing.get("skill_id"):
            raise ValueError(
                f"skill {skill_name!r} not in manifest; first upload must use --create"
            )
        skill_id = existing["skill_id"]

    version_obj = client.beta.skills.versions.create(
        skill_id=skill_id,
        files=files,
    )
    version = str(getattr(version_obj, "version", "latest"))

    skills[skill_name] = {"skill_id": skill_id, "version": version}
    _write_manifest({"skills": skills})
    return skill_id, version


# ── CLI ─────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill",
        required=True,
        help="Name of the directory under apps/worker/skills/ to upload",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create the skill_id first (only for first-ever upload of a skill)",
    )
    parser.add_argument(
        "--lint-only",
        action="store_true",
        help="Run frontmatter + network-import checks only; don't upload",
    )
    args = parser.parse_args()

    skill_dir = _SKILLS_DIR / args.skill
    if not skill_dir.is_dir():
        print(f"error: skill directory not found: {skill_dir}", file=sys.stderr)
        return 2
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        print(f"error: {skill_md} not found", file=sys.stderr)
        return 2

    # Frontmatter check (always).
    meta = _parse_frontmatter(skill_md)
    _validate_frontmatter(meta, args.skill)

    # Network-import lint (always).
    violations = _lint_skill_dir(skill_dir)
    if violations:
        print(
            "error: skill failed network-import lint — code_execution containers "
            "do not have network access:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 3

    if args.lint_only:
        print(f"OK — {args.skill} v{meta['version']} (description: {meta['description']!r})")
        return 0

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2

    try:
        skill_id, version = _upload(args.skill, create=args.create)
    except Exception as exc:
        print(f"error: upload failed: {exc}", file=sys.stderr)
        return 4

    print(f"uploaded {args.skill}: skill_id={skill_id} version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
