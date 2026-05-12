"""Connector catalog — merge of custom seeds and Composio auth_configs.

Composio is the single source of truth for OAuth connectors. Every
auth_config the operator registers in the Composio dashboard becomes a
connectable toolkit in the Nexus panel without a redeploy. Custom
non-Composio integrations (``whatsapp_ycloud``, ``agendapro``) keep
living in seed YAMLs because they have no equivalent in Composio.

Catalog shape:

    seeds (auth_kind != oauth_composio)  ←  ``connectors`` table
        +
    dynamic OAuth toolkits               ←  ``composio.auth_configs.list()``
        =
    catalog returned by GET /admin/connectors

If Composio is unreachable the endpoint degrades to "custom seeds only"
and logs a warning — the operator still sees the things that don't
require Composio.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Connector

from .composio_client import (
    AuthConfigSummary,
    ComposioClientProtocol,
    ComposioUnavailable,
    ToolkitMetadata,
)

log = logging.getLogger(__name__)

# In-process cache for ``toolkits.get(slug)`` results. Lives as long as the
# worker process — for Phase 1 (1 worker, low traffic) that's enough to
# avoid hitting Composio on every catalog load. Redis-backed TTL cache is
# the obvious next step but tracked as follow-up. ``None`` values are
# cached too so we don't re-query slugs that returned 404.
_TOOLKIT_METADATA_CACHE: dict[str, ToolkitMetadata | None] = {}
_TOOLKIT_METADATA_LOCK = asyncio.Lock()


async def _get_toolkit_metadata_cached(
    composio: ComposioClientProtocol, slug: str
) -> ToolkitMetadata | None:
    slug = slug.lower()
    if slug in _TOOLKIT_METADATA_CACHE:
        return _TOOLKIT_METADATA_CACHE[slug]
    async with _TOOLKIT_METADATA_LOCK:
        # Re-check after acquiring the lock — another coroutine may have
        # populated the cache while we waited.
        if slug in _TOOLKIT_METADATA_CACHE:
            return _TOOLKIT_METADATA_CACHE[slug]
        try:
            md = await composio.get_toolkit_metadata(slug)
        except Exception as exc:
            log.warning("toolkits.get(%s) failed: %s", slug, exc)
            md = None
        _TOOLKIT_METADATA_CACHE[slug] = md
        return md


@dataclass(frozen=True)
class CatalogConnector:
    """A connector as seen by the catalog endpoint.

    ``id`` is ``None`` for dynamic Composio entries that haven't been
    persisted yet (they get a row in ``connectors`` lazily, only when
    a tenant initiates consent — until then they live just in this view).
    """

    id: uuid.UUID | None
    slug: str
    display_name: str
    vendor: str
    category: str
    capabilities: list[str]
    auth_kind: str
    mcp_server_ref: str
    provider_meta: dict[str, Any]
    auto_enable_on_connect: bool
    auto_enable_destructive: bool
    consent_link_template_name: str | None
    status: str


# Composio's category strings → Nexus category buckets used by the panel
# to group cards. Match case-insensitive on the Composio side. Unknown
# categories fall back to ``"otros"`` so the catalog never breaks on a
# new toolkit type Composio introduces.
_CATEGORY_MAP: dict[str, str] = {
    "calendar": "calendar",
    "scheduling": "booking",
    "booking": "booking",
    "productivity": "docs",
    "productivity-and-project-management": "docs",
    "project-management": "docs",
    "knowledge-management": "docs",
    "knowledge": "docs",
    "documents": "docs",
    "crm": "crm",
    "communication": "messaging",
    "messaging": "messaging",
    "team-collaboration": "messaging",
    "email": "messaging",
}


# Convention for the consent magic-link WhatsApp template. All
# oauth_composio connectors reuse the same Meta-approved template name —
# there is one template per audience, not per connector.
_DEFAULT_CONSENT_TEMPLATE = "connector_consent_request_v1"


def _project_dynamic(ac: AuthConfigSummary, md: ToolkitMetadata | None = None) -> CatalogConnector:
    """Project a Composio AuthConfigSummary into the catalog shape.

    Optional ``md`` (from ``toolkits.get(slug)``) supplies the canonical
    name + category that Composio publishes for the toolkit, overriding
    the auth_config alias (which defaults to ``<slug>-<random>``).
    """
    slug = ac.toolkit_slug.lower()
    # Display name: prefer toolkit canonical name → auth_config alias →
    # title-cased slug. Drop the auth_config alias when it looks like the
    # SDK default ``<slug>-<6chars>`` because that's not user-facing copy.
    canonical_name = md.name if md and md.name else None
    alias_looks_default = (
        ac.display_name
        and ac.display_name.lower().startswith(slug + "-")
        and len(ac.display_name) - len(slug) - 1 <= 8
    )
    display_name = canonical_name or (
        slug.title() if alias_looks_default else (ac.display_name or slug.title())
    )

    # Category: prefer toolkit metadata → AuthConfigSummary fallback → otros.
    raw_category = (md.category_slug if md and md.category_slug else ac.category) or ""
    composio_category = raw_category.lower().replace(" ", "-").replace("_", "-")
    category = _CATEGORY_MAP.get(composio_category, "otros")

    provider_meta: dict[str, Any] = {
        "composio_toolkit_slug": slug.upper(),
        "composio_auth_config_id": ac.auth_config_id,
    }
    icon = (md.logo if md and md.logo else None) or ac.icon_url
    if icon:
        provider_meta["icon_url"] = icon
    if ac.docs_url:
        provider_meta["docs_url"] = ac.docs_url
    vendor = canonical_name or display_name
    return CatalogConnector(
        id=None,
        slug=slug,
        display_name=display_name,
        vendor=vendor,
        category=category,
        # Conservative defaults — the real capabilities materialize once the
        # operator connects and we sync tools.list. Phase 1 treats every
        # OAuth toolkit as "could read, could write".
        capabilities=["read", "write"],
        auth_kind="oauth_composio",
        mcp_server_ref=f"composio:{slug}",
        provider_meta=provider_meta,
        auto_enable_on_connect=True,
        auto_enable_destructive=False,
        consent_link_template_name=_DEFAULT_CONSENT_TEMPLATE,
        status="available",
    )


def _project_persisted(row: Connector) -> CatalogConnector:
    return CatalogConnector(
        id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        vendor=row.vendor,
        category=row.category,
        capabilities=list(row.capabilities or []),
        auth_kind=row.auth_kind,
        mcp_server_ref=row.mcp_server_ref,
        provider_meta=dict(row.provider_meta or {}),
        auto_enable_on_connect=row.auto_enable_on_connect,
        auto_enable_destructive=row.auto_enable_destructive,
        consent_link_template_name=row.consent_link_template_name,
        status=row.status,
    )


async def list_catalog(
    session: AsyncSession,
    composio: ComposioClientProtocol,
    *,
    category: str | None = None,
    status_filter: str | None = None,
) -> list[CatalogConnector]:
    """Return the merged catalog.

    Filters apply post-merge so they work uniformly across persisted and
    dynamic entries.
    """
    stmt = select(Connector).where(Connector.auth_kind != "oauth_composio")
    rows = (await session.scalars(stmt)).all()
    persisted = [_project_persisted(r) for r in rows]

    dynamic: list[CatalogConnector] = []
    try:
        configs = await composio.list_auth_configs()
        # Enrich each auth_config with its toolkit metadata in parallel.
        # ``asyncio.gather`` with the cache means we hit Composio at most
        # once per slug per worker process. Errors degrade silently — the
        # auth_config alias is still good enough for the panel.
        metadata_list = await asyncio.gather(
            *[_get_toolkit_metadata_cached(composio, ac.toolkit_slug) for ac in configs],
            return_exceptions=False,
        )
        for ac, md in zip(configs, metadata_list, strict=True):
            dynamic.append(_project_dynamic(ac, md))
    except ComposioUnavailable as exc:
        log.warning("composio unavailable in catalog: %s", exc)
    except Exception as exc:
        # Defensive: any other failure (SDK shape change, auth error,
        # malformed item) must not 500 the catalog endpoint. The seed
        # rows alone keep the panel usable while we triage the upstream
        # error from the logs.
        log.exception("composio list_auth_configs failed unexpectedly: %s", exc)

    # Merge by slug. Dynamic entries win over any stale persisted row with
    # the same slug — Composio is authoritative for OAuth.
    by_slug: dict[str, CatalogConnector] = {p.slug: p for p in persisted}
    for d in dynamic:
        by_slug[d.slug] = d
    merged = list(by_slug.values())

    if category:
        merged = [c for c in merged if c.category == category]
    if status_filter:
        merged = [c for c in merged if c.status == status_filter]
    merged.sort(key=lambda c: (c.category, c.display_name))
    return merged


async def get_catalog_entry(
    session: AsyncSession,
    composio: ComposioClientProtocol,
    slug: str,
) -> CatalogConnector | None:
    """Lookup a single catalog entry by slug. Returns ``None`` if the slug
    is unknown to both the seed catalog and Composio.

    For OAuth slugs, Composio is queried first — the persisted row (if
    any) is only used as a fallback when Composio is unreachable.
    """
    slug = slug.lower()
    row = await session.scalar(select(Connector).where(Connector.slug == slug))
    if row is not None and row.auth_kind != "oauth_composio":
        return _project_persisted(row)
    try:
        configs = await composio.list_auth_configs()
    except ComposioUnavailable:
        return _project_persisted(row) if row else None
    except Exception as exc:
        log.exception("composio list_auth_configs failed in get_entry: %s", exc)
        return _project_persisted(row) if row else None
    for ac in configs:
        if ac.toolkit_slug.lower() == slug:
            md = await _get_toolkit_metadata_cached(composio, slug)
            return _project_dynamic(ac, md)
    return _project_persisted(row) if row else None


async def ensure_composio_connector_persisted(
    session: AsyncSession,
    composio: ComposioClientProtocol,
    slug: str,
) -> Connector:
    """Upsert a ``connectors`` row from Composio metadata.

    Called by ``initiate-consent`` before creating the ``tenant_connector``
    row, so the FK has a target. Idempotent.

    Raises ``LookupError`` if the slug is not registered in Composio (the
    panel should never present this slug as connectable in that case, but
    the endpoint protects itself anyway).
    """
    slug = slug.lower()
    row = await session.scalar(select(Connector).where(Connector.slug == slug))
    if row is not None:
        return row
    configs = await composio.list_auth_configs()
    for ac in configs:
        if ac.toolkit_slug.lower() == slug:
            md = await _get_toolkit_metadata_cached(composio, slug)
            view = _project_dynamic(ac, md)
            row = Connector(
                slug=view.slug,
                display_name=view.display_name,
                vendor=view.vendor,
                category=view.category,
                capabilities=view.capabilities,
                auth_kind=view.auth_kind,
                mcp_server_ref=view.mcp_server_ref,
                provider_meta=view.provider_meta,
                auto_enable_on_connect=view.auto_enable_on_connect,
                auto_enable_destructive=view.auto_enable_destructive,
                consent_link_template_name=view.consent_link_template_name,
                status=view.status,
            )
            session.add(row)
            await session.flush()
            return row
    msg = (
        f"connector {slug!r} not registered as seed or in Composio dashboard — "
        "the catalog is out of sync; refresh the panel"
    )
    raise LookupError(msg)
