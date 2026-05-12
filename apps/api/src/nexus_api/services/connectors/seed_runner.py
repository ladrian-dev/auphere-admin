"""Apply ConnectorSeed rows to the database (idempotent).

Invoked from ``apps/api/scripts/seed_connectors.py`` at deploy time and from
tests that need a populated catalog.

Strategy: per slug, ``ON CONFLICT (slug) DO UPDATE`` every field EXCEPT
``auth_kind``. A change to ``auth_kind`` would mean credentials migrate to a
different shape — that is a "new connector" event, not an in-place rewrite.
We raise :class:`ConnectorAuthKindChanged` instead of silently breaking
existing tenant_connectors rows that point at this slug.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Connector

from .seed_loader import ConnectorSeed


class ConnectorAuthKindChanged(RuntimeError):
    """Refusing to silently rewrite auth_kind for an existing slug."""


@dataclass(frozen=True)
class SeedApplyResult:
    inserted: list[str]
    updated: list[str]
    unchanged: list[str]


async def apply_seeds(session: AsyncSession, seeds: list[ConnectorSeed]) -> SeedApplyResult:
    inserted: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []

    for seed in seeds:
        existing = await session.scalar(select(Connector).where(Connector.slug == seed.slug))
        if existing is not None and existing.auth_kind != seed.auth_kind:
            msg = (
                f"connector {seed.slug}: auth_kind change "
                f"{existing.auth_kind!r} → {seed.auth_kind!r} is not supported "
                "(it would invalidate existing tenant_connectors.credentials_ref). "
                "Create a new slug instead."
            )
            raise ConnectorAuthKindChanged(msg)

        stmt = (
            pg_insert(Connector)
            .values(
                slug=seed.slug,
                display_name=seed.display_name,
                vendor=seed.vendor,
                category=seed.category,
                capabilities=list(seed.capabilities),
                auth_kind=seed.auth_kind,
                mcp_server_ref=seed.mcp_server_ref,
                provider_meta=dict(seed.provider_meta),
                auto_enable_on_connect=seed.auto_enable_on_connect,
                auto_enable_destructive=seed.auto_enable_destructive,
                consent_link_template_name=seed.consent_link_template_name,
                status=seed.status,
            )
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={
                    "display_name": seed.display_name,
                    "vendor": seed.vendor,
                    "category": seed.category,
                    "capabilities": list(seed.capabilities),
                    "mcp_server_ref": seed.mcp_server_ref,
                    "provider_meta": dict(seed.provider_meta),
                    "auto_enable_on_connect": seed.auto_enable_on_connect,
                    "auto_enable_destructive": seed.auto_enable_destructive,
                    "consent_link_template_name": seed.consent_link_template_name,
                    "status": seed.status,
                },
            )
        )
        await session.execute(stmt)

        if existing is None:
            inserted.append(seed.slug)
        else:
            # Detect a no-op vs an update by comparing the fields we update.
            changed = any(
                getattr(existing, field) != getattr_seed(seed, field) for field in _COMPARED_FIELDS
            )
            (updated if changed else unchanged).append(seed.slug)

    await session.commit()
    return SeedApplyResult(inserted=inserted, updated=updated, unchanged=unchanged)


_COMPARED_FIELDS = (
    "display_name",
    "vendor",
    "category",
    "mcp_server_ref",
    "auto_enable_on_connect",
    "auto_enable_destructive",
    "consent_link_template_name",
    "status",
)


def getattr_seed(seed: ConnectorSeed, name: str) -> object:
    return getattr(seed, name)


__all__ = [
    "ConnectorAuthKindChanged",
    "SeedApplyResult",
    "apply_seeds",
]
