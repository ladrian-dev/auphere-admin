"""Which guide a client gets — spec 047, amendment of 2026-10-29 (requirements 58.2,
58.4 and 58.5; research D66).

From the **stored** sector (requirement 57.6; never re-classifying the niche):

1. a sector of the closed list → Auphere's guide from its templates, with the 12
   tests of ``sector_test_catalog`` under that key;
2. «otro» whose normalised label has an Auphere guide converted from a generated
   one (``sector_guides``) → that guide, with its catalog tests under its key;
3. «otro» with the client's own live generated guide for that label → that one,
   with its 12 tests («Generada»);
4. otherwise → nothing yet: the builder generates one (``generated.py``).

The stored key stays «otro» in cases 2 to 4: the closed list of keys the sector is
validated against (57.7) does not grow at run time (D66).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.agent_spec import SectorGuide
from nexus_api.services.builder.guides import generated as generated_guides
from nexus_api.services.builder.guides.catalog import auphere_guide
from nexus_api.services.builder.guides.schema import Guide, label_key, validate_guide
from nexus_api.services.builder.sectors import OTHER, SECTORS


@dataclass(frozen=True)
class ResolvedGuide:
    #: ``template`` | ``promoted`` | ``generated`` | ``missing``.
    source: str
    label: str
    label_key: str
    guide: Guide | None = None
    #: The key of its tests in ``sector_test_catalog`` (template and promoted).
    catalog_key: str | None = None
    #: The client's generated guide (``generated``).
    generated_id: uuid.UUID | None = None
    tests: tuple[dict[str, Any], ...] = field(default=())

    @property
    def has_auphere_guide(self) -> bool:
        return self.source in {"template", "promoted"}


async def promoted(session: AsyncSession, key: str) -> SectorGuide | None:
    """The converted Auphere guide for a normalised label, if any."""
    if not key:
        return None
    found: SectorGuide | None = (
        await session.scalars(sa.select(SectorGuide).where(SectorGuide.label_key == key))
    ).first()
    return found


async def for_sector(session: AsyncSession, sector: dict[str, Any] | None) -> ResolvedGuide | None:
    """The guide for a stored sector (``sector.stored``), inside the client's scope.
    ``None`` without a sector."""
    if sector is None:
        return None
    key, label = str(sector["key"]), str(sector["label"])
    lkey = label_key(label)
    if key in SECTORS:
        found = auphere_guide(key)
        assert found is not None
        return ResolvedGuide(
            source="template",
            label=found.label,
            label_key=label_key(found.label),
            guide=found.guide,
            catalog_key=key,
        )
    if key != OTHER:
        return None
    row = await promoted(session, lkey)
    if row is not None:
        return ResolvedGuide(
            source="promoted",
            label=row.label,
            label_key=row.label_key,
            guide=validate_guide(row.guide),
            catalog_key=row.key,
        )
    mine = await generated_guides.live(session, lkey)
    if mine is not None:
        return ResolvedGuide(
            source="generated",
            label=mine.sector_label,
            label_key=mine.label_key,
            guide=validate_guide(mine.guide),
            generated_id=mine.id,
            tests=tuple(dict(t) for t in mine.tests or ()),
        )
    return ResolvedGuide(source="missing", label=label, label_key=lkey)


async def for_client(session: AsyncSession) -> ResolvedGuide | None:
    """The guide of the client in context, from its stored sector (saved once with
    the fallback rule if it was not identified yet, ``sector.ensure_stored``)."""
    from nexus_api.services.business import sector as sector_service

    return await for_sector(session, await sector_service.ensure_stored(session))


async def has_auphere_guide(session: AsyncSession, sector: dict[str, Any] | None) -> bool:
    """For the console's «Con guía» / «Generada» (``has_guide``): a sector of the
    list, or «otro» whose label Auphere converted."""
    if sector is None:
        return False
    if sector.get("key") in SECTORS:
        return True
    return await promoted(session, label_key(sector.get("label"))) is not None


__all__ = ["ResolvedGuide", "for_client", "for_sector", "has_auphere_guide", "promoted"]
