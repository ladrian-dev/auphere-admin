"""E2E-2026-08-30 F0/A4 — every LLM pipeline entry point opens the
partner virtual-key scope.

``resolve_litellm_proxy`` is fail-closed: a hop outside
``llm_proxy_partner_scope`` dies with "missing partner virtual key"
before leaving the process, and — because asyncio gives each Task a
fresh contextvar context — a scope opened by a request handler does NOT
reach a driver spawned as its own Task. That is exactly how the console
Playground shipped dead (N2 of INFORME-E2E-STAGING-2026-08-30).

This test enumerates, by AST, every file under ``apps/api/src`` and
``apps/worker/src`` that invokes an agent pipeline
(``.astream_events(...)`` / ``.ainvoke(...)``) and requires each one to
reference ``llm_proxy_partner_scope`` — or to be listed below with a
written reason why the scope is guaranteed by its caller. Adding a new
entry point without opening the scope turns this red instead of
shipping another silent 100%-failure surface.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCAN_ROOTS = ("apps/api/src", "apps/worker/src")
_PIPELINE_CALLS = frozenset({"astream_events", "ainvoke"})

# Files that invoke a pipeline WITHOUT referencing the scope themselves.
# Every entry needs a reason proving the scope is opened by the caller
# in the SAME asyncio task (contextvars do not cross Task boundaries).
_ALLOWED_WITHOUT_SCOPE: dict[str, str] = {
    "apps/api/src/nexus_api/api/qa_streaming.py": (
        "default_pipeline_driver is a factory with zero callers today; "
        "qa.py and console/playground.py build their own drivers. Any "
        "future caller must open llm_proxy_partner_scope inside the "
        "driver it passes to start_run."
    ),
    "apps/api/src/nexus_api/services/evals/pipeline_driver.py": (
        "Driven by api/admin/evals.py, which resolves the tenant's "
        "partner and awaits run_eval inside llm_proxy_partner_scope in "
        "the same task (no Task hop between scope and ainvoke)."
    ),
    "apps/api/src/nexus_api/services/evals/companion/driver.py": (
        "Companion eval driver — invoked under the same "
        "llm_proxy_partner_scope block in api/admin/evals.py as "
        "pipeline_driver, same task."
    ),
}


def _pipeline_invokers() -> dict[str, bool]:
    """Map repo-relative path → whether the file references the scope,
    for every file that calls ``.astream_events(`` or ``.ainvoke(``."""
    found: dict[str, bool] = {}
    for root in _SCAN_ROOTS:
        for path in sorted((_REPO_ROOT / root).rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
            except SyntaxError:  # pragma: no cover — broken file fails elsewhere
                continue
            invokes = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _PIPELINE_CALLS
                for node in ast.walk(tree)
            )
            if invokes:
                rel = path.relative_to(_REPO_ROOT).as_posix()
                found[rel] = "llm_proxy_partner_scope" in source
    return found


def test_every_pipeline_entry_point_opens_partner_scope() -> None:
    invokers = _pipeline_invokers()
    assert invokers, "AST scan found no pipeline invokers — scan roots moved?"
    missing = [
        rel
        for rel, has_scope in invokers.items()
        if not has_scope and rel not in _ALLOWED_WITHOUT_SCOPE
    ]
    assert not missing, (
        "LLM pipeline entry points without llm_proxy_partner_scope "
        f"(fail-closed resolver → every hop dies): {missing}. Open the "
        "scope INSIDE the driver task, or allowlist with a reason "
        "proving the caller opens it in the same task."
    )


def test_scope_allowlist_has_no_stale_entries() -> None:
    """An allowlisted file that gained the scope (or disappeared) must be
    dropped from the list so the list stays an honest inventory."""
    invokers = _pipeline_invokers()
    stale = [rel for rel in _ALLOWED_WITHOUT_SCOPE if rel not in invokers or invokers[rel]]
    assert not stale, f"Stale _ALLOWED_WITHOUT_SCOPE entries: {stale}"
