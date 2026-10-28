"""El catálogo de pruebas del sector — spec 047, T090 (requisitos 21.1 y 54.10; research D18).

Doce pruebas por sector, versionadas, que edita Auphere desde el panel de
operador (``api/admin/sector_tests.py``). Un agente recibe las de la versión
vigente del sector de su cliente (deducido del nicho, ``builder.sectors``), cada
una con su ``sector@versión#clave``; un cliente de «Otro» no tiene batería común
y su suite son las del caso y las añadidas.

Publicar una versión nueva no cambia las suites que ya existen: cada prueba
recuerda de qué versión salió.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite, SectorTestCatalog
from nexus_api.services.builder.sectors import OTHER, SECTORS, sector_of_niche
from nexus_api.services.testing.suites import add_test

TESTS_PER_SECTOR: Final = 12


class SectorCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    text: str = Field(min_length=1, max_length=300)


class SectorTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    name: str = Field(min_length=1, max_length=120)
    persona: str = Field(default="", max_length=500)
    first_message: str = Field(min_length=1, max_length=2000)
    plan: str = Field(default="", max_length=1000)
    expected_state: dict[str, Any] = Field(default_factory=dict)
    criteria: list[SectorCriterion] = Field(min_length=1, max_length=6)
    critical: bool = False


class SectorCatalogError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def validate_tests(raw: Sequence[Mapping[str, Any]]) -> list[SectorTest]:
    try:
        tests = [SectorTest.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise SectorCatalogError("invalid_test", str(exc)) from exc
    if len(tests) != TESTS_PER_SECTOR:
        raise SectorCatalogError("twelve_tests_required")
    if len({t.key for t in tests}) != len(tests):
        raise SectorCatalogError("duplicate_key")
    return tests


async def latest(session: AsyncSession, sector: str) -> SectorTestCatalog | None:
    return (
        await session.scalars(
            sa.select(SectorTestCatalog)
            .where(SectorTestCatalog.sector_key == sector)
            .order_by(SectorTestCatalog.version.desc())
            .limit(1)
        )
    ).first()


async def publish(
    session: AsyncSession, sector: str, raw: Sequence[Mapping[str, Any]], *, by: str
) -> SectorTestCatalog:
    """Una versión nueva del sector. Las suites existentes no cambian."""
    if sector not in SECTORS:
        raise SectorCatalogError("unknown_sector")
    tests = validate_tests(raw)
    current = await latest(session, sector)
    row = SectorTestCatalog(
        sector_key=sector,
        version=(current.version + 1) if current else 1,
        tests=[t.model_dump() for t in tests],
        published_by=by,
    )
    session.add(row)
    await session.flush()
    return row


async def client_sector(session: AsyncSession) -> str:
    from nexus_api.db.models.business import BusinessProfile

    profile = await session.get(BusinessProfile, require_current_tenant())
    return sector_of_niche(profile.niche if profile else None)


async def add_sector_tests(session: AsyncSession, suite: AgentTestSuite) -> int:
    """Las 12 del sector del cliente, en la versión vigente; las que la suite ya
    tiene (por su referencia) no se repiten."""
    sector = await client_sector(session)
    if sector == OTHER:
        return 0
    catalog = await latest(session, sector)
    if catalog is None:
        return 0
    have = set(
        (
            await session.scalars(
                sa.select(AgentTest.sector_test_ref).where(
                    AgentTest.tenant_id == suite.tenant_id,
                    AgentTest.suite_id == suite.id,
                    AgentTest.sector_test_ref.is_not(None),
                )
            )
        ).all()
    )
    added = 0
    for item in catalog.tests:
        ref = f"{sector}@{catalog.version}#{item['key']}"
        if ref in have:
            continue
        await add_test(session, suite, {**item, "sector_test_ref": ref}, kind="sector", by="system")
        added += 1
    return added


__all__ = [
    "TESTS_PER_SECTOR",
    "SectorCatalogError",
    "SectorTest",
    "add_sector_tests",
    "client_sector",
    "latest",
    "publish",
    "validate_tests",
]
