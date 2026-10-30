"""Sectors without a guide and «Convertir en guía de Auphere» — spec 047, amendment
of 2026-10-29 (requirement 58.5; ``contracts/admin-sector-guides.md``; D66).

What the operator panel does, without HTTP:

- :func:`auphere_list`: Auphere's guides, the six of the templates and the
  converted ones;
- :func:`missing`: the labels of «otro» without guide, most repeated first, read
  **client by client with its scope declared** (the tables are RLS FORCE: a query
  across clients without it would see nothing in production, and everything
  locally, which is how such a bug hides);
- :func:`read`, :func:`review` and :func:`promote`: one generated guide, under its
  own client.

Converting writes, in one transaction: the platform guide (``sector_guides``, with
nothing of the client), its 12 tests as version 1 of its key in
``sector_test_catalog``, the client's guide as ``promoted`` and two audit rows (the
client's, and a platform one with nothing of the client).
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import declare_tenant
from nexus_api.db.models import AuditLog, Tenant
from nexus_api.db.models.agent_spec import GeneratedGuide, SectorGuide, SectorTestCatalog
from nexus_api.db.models.business import BusinessProfile
from nexus_api.services.builder.guides import client_data
from nexus_api.services.builder.guides.catalog import template_guides
from nexus_api.services.builder.guides.schema import (
    Guide,
    GuideInvalid,
    label_key,
    validate_guide,
    validate_tests,
)
from nexus_api.services.builder.sectors import OTHER, SECTORS

CANDIDATES: Final = 5
LIVE: Final = ("generated", "reviewed")


@dataclass
class GuideAdminError(Exception):
    code: str
    status: int
    findings: list[dict[str, str]] | None = None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _clear_tenant(session: AsyncSession) -> None:
    """Back to the platform scope inside the same transaction."""
    await session.execute(sa.text("SELECT set_config('app.tenant_id', '', true)"))


async def _catalog_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            sa.select(
                SectorTestCatalog.sector_key, SectorTestCatalog.version, SectorTestCatalog.tests
            )
        )
    ).all()
    latest: dict[str, tuple[int, int]] = {}
    for key, version, tests in rows:
        if key not in latest or version > latest[key][0]:
            latest[key] = (version, len(tests or []))
    return {key: count for key, (_v, count) in latest.items()}


def _guide_out(
    *,
    key: str,
    label: str,
    source: str,
    guide: Guide | dict[str, Any],
    tests: int,
    templates: tuple[str, ...] = (),
    version: int = 1,
    published_by: str | None = None,
    published_at: datetime | None = None,
) -> dict[str, Any]:
    body = guide.model_dump() if isinstance(guide, Guide) else dict(guide)
    return {
        "key": key,
        "label": label,
        "label_key": label_key(label),
        "source": source,
        "templates": list(templates),
        "version": version,
        "tests": tests,
        "published_by": published_by,
        "published_at": _iso(published_at),
        "guide": body,
    }


async def auphere_list(session: AsyncSession) -> list[dict[str, Any]]:
    """The six template guides in the order of the sectors, then the converted ones
    by date. Platform scope."""
    counts = await _catalog_counts(session)
    out = [
        _guide_out(
            key=item.key,
            label=item.label,
            source="template",
            guide=item.guide,
            tests=counts.get(item.key, 0),
            templates=item.templates,
        )
        for item in template_guides().values()
    ]
    rows = (
        await session.scalars(
            sa.select(SectorGuide).order_by(SectorGuide.published_at, SectorGuide.key)
        )
    ).all()
    out += [
        _guide_out(
            key=row.key,
            label=row.label,
            source="promoted",
            guide=row.guide,
            tests=counts.get(row.key, 0),
            version=row.version,
            published_by=row.published_by,
            published_at=row.published_at,
        )
        for row in rows
    ]
    return out


def _summary(row: GeneratedGuide, client_name: str) -> dict[str, Any]:
    return {
        "tenant_id": str(row.tenant_id),
        "client_name": client_name,
        "guide_id": str(row.id),
        "status": row.status,
        "tests": len(row.tests or []),
        "created_at": _iso(row.created_at),
        "reviewed_at": _iso(row.reviewed_at),
        "reviewed_by": row.reviewed_by,
    }


async def missing(session: AsyncSession, *, limit: int) -> dict[str, Any]:
    """The labels of «otro» without an Auphere guide, most repeated first."""
    tenants = (
        await session.execute(
            sa.select(Tenant.id, Tenant.name)
            .where(Tenant.status != "archived")
            .order_by(Tenant.name, Tenant.id)
        )
    ).all()
    guided = set((await session.scalars(sa.select(SectorGuide.label_key))).all())
    clients: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = {}
    guides: dict[str, list[tuple[GeneratedGuide, str]]] = {}
    for tenant_id, name in tenants:
        await declare_tenant(session, tenant_id)
        sector = await session.scalar(
            sa.select(BusinessProfile.sector).where(BusinessProfile.tenant_id == tenant_id)
        )
        if isinstance(sector, dict) and sector.get("key") == OTHER and sector.get("label"):
            key = label_key(sector["label"])
            if key and key not in guided:
                clients[key] += 1
                spellings.setdefault(key, Counter())[str(sector["label"])] += 1
        rows = (
            await session.scalars(
                sa.select(GeneratedGuide).where(
                    GeneratedGuide.tenant_id == tenant_id, GeneratedGuide.status.in_(LIVE)
                )
            )
        ).all()
        for row in rows:
            if row.label_key not in guided:
                guides.setdefault(row.label_key, []).append((row, str(name)))
    await _clear_tenant(session)
    keys = set(clients) | set(guides)
    ordered = sorted(keys, key=lambda k: (-clients.get(k, 0), k))
    items = []
    for key in ordered[:limit]:
        found = guides.get(key, [])
        found.sort(key=lambda pair: (pair[0].status != "reviewed", -pair[0].created_at.timestamp()))
        written = spellings.get(key) or Counter()
        if not written and found:
            written = Counter(row.sector_label for row, _n in found)
        label = max(sorted(written), key=lambda s: written[s]) if written else key
        items.append(
            {
                "label_key": key,
                "label": label,
                "clients": clients.get(key, 0),
                "guides": {
                    status: sum(1 for row, _n in found if row.status == status) for status in LIVE
                },
                "candidates": [_summary(row, name) for row, name in found[:CANDIDATES]],
            }
        )
    return {
        "items": items,
        "clients_scanned": len(tenants),
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def _owned(
    session: AsyncSession, tenant_id: uuid.UUID, guide_id: uuid.UUID, *, lock: bool = False
) -> tuple[GeneratedGuide, str]:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise GuideAdminError("unknown_guide", 404)
    await declare_tenant(session, tenant_id)
    query = sa.select(GeneratedGuide).where(
        GeneratedGuide.tenant_id == tenant_id, GeneratedGuide.id == guide_id
    )
    if lock:
        query = query.with_for_update()
    row = (await session.scalars(query.execution_options(populate_existing=True))).first()
    if row is None:
        raise GuideAdminError("unknown_guide", 404)
    return row, tenant.name


async def _findings(session: AsyncSession, row: GeneratedGuide) -> list[dict[str, str]]:
    data = await client_data.load(session, row.tenant_id, label=row.sector_label)
    doc = {"guide": row.guide or {}, "tests": list(row.tests or [])}
    return [f.out() for f in client_data.scan(doc, data)]


def _well_formed(row: GeneratedGuide) -> bool:
    try:
        validate_guide(row.guide)
        validate_tests(list(row.tests or []))
    except GuideInvalid:
        return False
    return True


def _detail(
    row: GeneratedGuide, client_name: str, findings: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "guide_id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "client_name": client_name,
        "sector_label": row.sector_label,
        "label_key": row.label_key,
        "status": row.status,
        "guide": dict(row.guide or {}),
        "tests": list(row.tests or []),
        "client_data": findings,
        "promotable": row.status == "reviewed" and not findings and _well_formed(row),
        "reviewed_by": row.reviewed_by,
        "reviewed_at": _iso(row.reviewed_at),
        "promoted_to": row.promoted_to,
        "promoted_at": _iso(row.promoted_at),
        "created_at": _iso(row.created_at),
    }


async def read(session: AsyncSession, tenant_id: uuid.UUID, guide_id: uuid.UUID) -> dict[str, Any]:
    row, name = await _owned(session, tenant_id, guide_id)
    findings = await _findings(session, row)
    await _clear_tenant(session)
    return _detail(row, name, findings)


async def review(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    guide_id: uuid.UUID,
    *,
    guide: dict[str, Any] | None,
    tests: list[dict[str, Any]] | None,
    note: str | None,
    actor: str,
) -> dict[str, Any]:
    """Marks the guide reviewed, with the operator's corrections if any. Nothing is
    written if client data remains (``client_data_found``)."""
    row, name = await _owned(session, tenant_id, guide_id, lock=True)
    if row.status in {"promoted", "archived"}:
        raise GuideAdminError("guide_not_reviewable", 409)
    try:
        new_guide = validate_guide(guide if guide is not None else row.guide).model_dump()
        new_tests = validate_tests(tests if tests is not None else list(row.tests or []))
    except GuideInvalid as exc:
        raise GuideAdminError(exc.code, 422) from exc
    before = row.status
    edited = guide is not None or tests is not None
    data = await client_data.load(session, tenant_id, label=row.sector_label)
    findings = [f.out() for f in client_data.scan({"guide": new_guide, "tests": new_tests}, data)]
    if findings:
        raise GuideAdminError("client_data_found", 422, findings=findings)
    row.guide = new_guide
    row.tests = new_tests
    row.status = "reviewed"
    row.reviewed_by = actor
    row.reviewed_at = datetime.now(UTC)
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="generated_guide.reviewed",
            target=f"generated_guide:{row.id}",
            before_json={"status": before},
            after_json={"status": "reviewed", "edited": edited, "note": (note or "")[:300]},
        )
    )
    await session.flush()
    out = _detail(row, name, [])
    await _clear_tenant(session)
    return out


async def promote(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    guide_id: uuid.UUID,
    *,
    key: str,
    label: str,
    reason: str,
    actor: str,
) -> dict[str, Any]:
    """«Convertir en guía de Auphere» (see the module)."""
    from nexus_api.services.business.sector import clean_label

    row, _name = await _owned(session, tenant_id, guide_id, lock=True)
    if row.status == "promoted":
        raise GuideAdminError("guide_already_promoted", 409)
    if row.status != "reviewed":
        raise GuideAdminError("guide_not_reviewed", 409)
    try:
        guide = validate_guide(row.guide)
        tests = validate_tests(list(row.tests or []))
    except GuideInvalid as exc:
        raise GuideAdminError(exc.code, 422) from exc
    findings = await _findings(session, row)
    if findings:
        raise GuideAdminError("client_data_found", 422, findings=findings)
    clean = clean_label(label)
    lkey = label_key(clean)
    if not clean or not lkey:
        raise GuideAdminError("invalid_label", 422)
    now = datetime.now(UTC)
    row.status = "promoted"
    row.promoted_to = key
    row.promoted_at = now
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="generated_guide.promoted",
            target=f"generated_guide:{row.id}",
            before_json={"status": "reviewed"},
            after_json={"promoted_to": key, "reason": reason},
        )
    )
    await session.flush()

    # The platform part: nothing of the client from here on.
    await _clear_tenant(session)
    if key in SECTORS or key == OTHER or await session.get(SectorGuide, key) is not None:
        raise GuideAdminError("guide_key_taken", 409)
    if (
        await session.scalar(
            sa.select(SectorTestCatalog.sector_key)
            .where(SectorTestCatalog.sector_key == key)
            .limit(1)
        )
        is not None
    ):
        raise GuideAdminError("guide_key_taken", 409)
    if await session.scalar(
        sa.select(SectorGuide.key).where(SectorGuide.label_key == lkey)
    ) is not None or lkey in {label_key(item.label) for item in template_guides().values()}:
        raise GuideAdminError("guide_label_taken", 409)
    platform = SectorGuide(
        key=key,
        label=clean,
        label_key=lkey,
        guide=guide.model_dump(),
        version=1,
        published_by=actor,
        published_at=now,
    )
    session.add(platform)
    session.add(SectorTestCatalog(sector_key=key, version=1, tests=tests, published_by=actor))
    session.add(
        AuditLog(
            tenant_id=None,
            actor=actor,
            action="sector_guide.promoted",
            target=f"sector_guide:{key}",
            before_json=None,
            after_json={"key": key, "label": clean, "tests": len(tests), "reason": reason},
        )
    )
    await session.flush()
    return _guide_out(
        key=key,
        label=clean,
        source="promoted",
        guide=guide,
        tests=len(tests),
        version=1,
        published_by=actor,
        published_at=now,
    )


__all__ = ["GuideAdminError", "auphere_list", "missing", "promote", "read", "review"]
