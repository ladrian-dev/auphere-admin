"""AgentLoader — resolves a tenant's active ``agent_config`` to a runtime bundle.

The bundle holds:
- ``system_prompt``: the pre-rendered prompt verbatim (no Jinja in runtime —
  garantía 5).
- ``tools``: the whitelist as a frozenset for O(1) ``in`` checks. This is the
  ONLY tool surface the pipeline ever sees — handlers ``call_with_whitelist``
  through this set, never against the global catalog (garantía 2).
- ``policies``: opaque JSONB for the handlers.
- ``version``, ``version_id``: useful for traces and the no-redeploy promote
  test.

Caching:
- Per-process ``OrderedDict`` LRU keyed by ``tenant_id``.
- Invalidation arrives via ``invalidate(tenant_id)``. The promote subscriber
  drives that on every ``nexus:agent_config:promote`` message.
- A staged version that is NOT promoted does not change the active row, so we
  never need to invalidate on stage.

The loader opens its own SQLAlchemy session inside ``tenant_scoped_session``
so it can be called from worker code that already has a transaction open
(e.g. the persistence layer); the gotcha from block B (RLS only takes effect
inside an active transaction) is satisfied here.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import structlog
from nexus_api.core.errors import IsolationViolation
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.repositories import AgentConfigRepository

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AgentBundle:
    tenant_id: uuid.UUID
    version: int
    version_id: uuid.UUID
    system_prompt: str
    tools: frozenset[str]
    policies: dict[str, Any] = field(default_factory=dict)
    # Fase D — Anthropic Skills attached to this agent_config. Each
    # element: ``{"skill_id": str, "version": str | "latest"}``. Empty
    # tuple = no skills, the handler skips Skills injection entirely.
    # Tuple (not list) for immutability of the frozen dataclass.
    runtime_skills: tuple[dict[str, str], ...] = ()
    # Fase E — Anthropic MCP connector servers. Each element:
    # ``{name, url, allowed_tools, credential_key}``. Empty tuple =
    # MCP connector OFF for this config; the handler skips ``mcp_servers``
    # + the mcp-client beta header entirely. The auth token is resolved
    # per-turn from tenant_credentials by ``credential_key``.
    runtime_mcp_servers: tuple[dict[str, Any], ...] = ()


class AgentLoader:
    """Per-process loader. Threadsafe via an asyncio lock.

    The cache is keyed by ``tenant_id`` — the active version is whatever the
    DB says it is at fetch time. That keeps cache reads O(1) without an
    extra DB round-trip to discover the active version_id first.
    """

    def __init__(self, max_size: int = 64) -> None:
        self._cache: OrderedDict[uuid.UUID, AgentBundle] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def load(self, tenant_id: uuid.UUID) -> AgentBundle:
        async with self._lock:
            cached = self._cache.get(tenant_id)
            if cached is not None:
                self._cache.move_to_end(tenant_id)
                return cached

        bundle = await self._fetch(tenant_id)

        async with self._lock:
            self._cache[tenant_id] = bundle
            self._cache.move_to_end(tenant_id)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
        return bundle

    def prime(self, bundle: AgentBundle) -> None:
        """Seed the cache with a pre-built bundle, bypassing the DB fetch.

        The eval runner uses this to pin the loader to a SPECIFIC
        ``agent_config`` version — including a STAGED candidate that is
        not the active row — so the real pipeline evaluates the exact
        config under test rather than whatever ``get_active()`` returns.
        ``load`` then returns this bundle for ``bundle.tenant_id`` until
        it is invalidated.

        Sync on purpose: callers prime the loader at setup time, before
        any concurrent ``load`` is awaited, so the lock is unnecessary.
        """
        self._cache[bundle.tenant_id] = bundle
        self._cache.move_to_end(bundle.tenant_id)

    async def invalidate(self, tenant_id: uuid.UUID) -> None:
        async with self._lock:
            self._cache.pop(tenant_id, None)
        log.info("agent_loader.invalidated", tenant_id=str(tenant_id))

    async def invalidate_many(self, tenant_ids: Iterable[uuid.UUID]) -> None:
        async with self._lock:
            for tid in tenant_ids:
                self._cache.pop(tid, None)

    def cache_size(self) -> int:
        return len(self._cache)

    # ── internals ─────────────────────────────────────────────────────────

    async def _fetch(self, tenant_id: uuid.UUID) -> AgentBundle:
        """Open a tenant-scoped session and read the active config row.

        ``tenant_scoped_session`` performs ``set_config('app.tenant_id', …)``
        + ``SET LOCAL ROLE nexus_app`` inside an open transaction so RLS
        actually applies (block B gotcha #1).
        """
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            repo = AgentConfigRepository(session)
            cfg = await repo.get_active()
            if cfg is None:
                raise IsolationViolation(
                    f"no active agent_config for tenant {tenant_id} — refusing to run"
                )
            return AgentBundle(
                tenant_id=tenant_id,
                version=cfg.version,
                version_id=cfg.id,
                system_prompt=cfg.system_prompt_rendered,
                tools=frozenset(cfg.tools or ()),
                policies=dict(cfg.policies or {}),
                runtime_skills=tuple(
                    {
                        "skill_id": str(s.get("skill_id", "")),
                        "version": str(s.get("version", "latest")),
                    }
                    for s in (cfg.runtime_skills or ())
                    if isinstance(s, dict) and s.get("skill_id")
                ),
                runtime_mcp_servers=tuple(
                    {
                        "name": str(s.get("name", "")),
                        "url": str(s.get("url", "")),
                        "allowed_tools": tuple(
                            str(t) for t in (s.get("allowed_tools") or ())
                        ),
                        "credential_key": str(s.get("credential_key", "")),
                    }
                    for s in (cfg.runtime_mcp_servers or ())
                    if isinstance(s, dict) and s.get("name") and s.get("url")
                ),
            )


_default_loader: AgentLoader | None = None


def get_default_loader() -> AgentLoader:
    """Process-singleton used by the streaming consumer. Tests typically
    construct their own ``AgentLoader`` and pass it explicitly."""
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentLoader()
    return _default_loader


def reset_default_loader() -> None:
    global _default_loader
    _default_loader = None
