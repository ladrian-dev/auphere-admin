"""WP-04 architecture test: every stream publication goes through
``xadd_capped`` (core/streams.py), which enforces MAXLEN.

A raw ``redis.xadd(`` anywhere else reintroduces the unbounded-stream bug
(V2) silently, so this test greps the source tree and fails the build on any
occurrence outside the helper module. Tests are exempt (they exercise redis
directly on purpose).
"""

from __future__ import annotations

import re
from pathlib import Path

# apps/api/tests/unit/test_no_raw_xadd.py → repo root is 4 levels up.
REPO_ROOT = Path(__file__).resolve().parents[4]

SOURCE_TREES = (
    REPO_ROOT / "apps" / "api" / "src",
    REPO_ROOT / "apps" / "worker" / "src",
    REPO_ROOT / "apps" / "channels" / "src",
    REPO_ROOT / "apps" / "mcp",
)

ALLOWED_FILE = REPO_ROOT / "apps" / "api" / "src" / "nexus_api" / "core" / "streams.py"

# ``.xadd(`` on any receiver (redis.xadd, self._redis.xadd, …). The helper
# itself carries the single allowed call.
RAW_XADD = re.compile(r"\.xadd\(")


def test_no_raw_xadd_outside_streams_helper() -> None:
    offenders: list[str] = []
    for tree in SOURCE_TREES:
        if not tree.exists():
            continue
        for path in tree.rglob("*.py"):
            if path == ALLOWED_FILE or "__pycache__" in path.parts:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(content.splitlines(), start=1):
                if RAW_XADD.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Raw .xadd( calls found — use nexus_api.core.streams.xadd_capped so "
        "MAXLEN is always applied:\n" + "\n".join(offenders)
    )


def test_repo_root_looks_right() -> None:
    # Guard against the parents[] arithmetic silently pointing somewhere
    # empty and making the main test pass vacuously.
    assert (REPO_ROOT / "apps" / "api" / "pyproject.toml").exists()
    assert ALLOWED_FILE.exists()
