"""El catálogo de pruebas del sector — spec 047, T090 (requisitos 21.1 y 54.10; research D18).

Doce pruebas por sector, versionadas, que edita Auphere desde el panel de
operador (``api/admin/sector_tests.py``). Un agente recibe las de la versión
vigente del sector **guardado** en la ficha de su cliente (requisito 57.6,
``services/business/sector.py``; nunca se vuelve a clasificar el nicho), cada una
con su ``sector@versión#clave``. Un cliente de «Otro» recibe las de la guía que
Auphere convirtió para su etiqueta (``clave@versión#prueba``) o, si no la hay, las
de la guía generada para él (``generated:<id>#prueba``, enmienda del 2026-10-29,
T201).

Publicar una versión nueva no cambia las suites que ya existen: cada prueba
recuerda de qué versión salió.

Spec 047, enmienda del 2026-10-30 (requisito 65.8): cada prueba declara lo que
necesita hacer el agente (``needs``, las acciones de ``capability_names``). Al
añadirlas a un agente, la que necesita una acción que sus herramientas no hacen
queda «No aplica», con su razón, sin que nadie la marque: no bloquea la puerta.
Una prueba sin ``needs`` declarado (una guía generada por un modelo) lo deduce de
su estado esperado: una cita (``booking``) necesita reservar.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, Literal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite, SectorTestCatalog
from nexus_api.services.builder.sectors import OTHER, SECTORS
from nexus_api.services.testing.suites import add_test

if TYPE_CHECKING:
    from nexus_api.services.builder.guides.resolve import ResolvedGuide

TESTS_PER_SECTOR: Final = 12

#: The actions a sector test may need (``capability_names.Action``).
Need = Literal[
    "book",
    "modify_booking",
    "charge",
    "collect",
    "invoice",
    "order",
    "modify_order",
    "send_media",
    "remind",
    "catalog",
]
#: What an expected state needs when the test does not say it.
_STATE_NEEDS: Final[dict[str, str]] = {"booking": "book", "payment": "charge", "order": "order"}


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
    #: Spec 047, enmienda del 2026-10-30 (65.8): lo que tiene que poder hacer el
    #: agente para que la prueba aplique. ``None``: se deduce de ``expected_state``.
    needs: list[Need] | None = Field(default=None, max_length=5)


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


def needs_of(test: Mapping[str, Any]) -> set[str]:
    """Lo que necesita una prueba del sector: lo que declara o, si no lo declara,
    lo que pide su estado esperado (una cita necesita reservar)."""
    declared = test.get("needs")
    if declared is not None:
        return {str(n) for n in declared}
    state = test.get("expected_state") or {}
    return {need for key, need in _STATE_NEEDS.items() if key in state}


def not_applicable_reason(test: Mapping[str, Any], tools: Iterable[str]) -> str | None:
    """La razón por la que la prueba no aplica a un agente con ``tools``, o
    ``None`` si aplica (65.8). Cuenta lo que hace cada herramienta según
    ``capability_names``, no su prefijo."""
    from nexus_api.api.console.capability_names import ACTION_LABELS, actions_of

    lacking = sorted(needs_of(test) - set(actions_of(tools)))
    if not lacking:
        return None
    labels = {str(key): label for key, label in ACTION_LABELS.items()}
    what = ", ".join(labels.get(n, n) for n in lacking)
    # Sin «No aplica:» delante: la consola lo pone (contracts/console-api.md §11).
    return f"Este agente no tiene herramienta para {what}."


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
    """La clave del sector guardado del cliente del contexto. Si aún no se ha
    identificado, queda guardado con la regla de respaldo (``ensure_stored``)."""
    from nexus_api.services.business import sector as sector_service

    value = await sector_service.ensure_stored(session)
    return value["key"] if value is not None else OTHER


async def add_sector_tests(
    session: AsyncSession,
    suite: AgentTestSuite,
    *,
    guide: ResolvedGuide | None = None,
    tools: Sequence[str] | None = None,
) -> int:
    """Las 12 del sector del cliente; las que la suite ya tiene (por su referencia)
    no se repiten. Salen de su guía (``guides.resolve``, desde el sector guardado):
    las de Auphere, de la versión vigente del catálogo bajo su clave (la de un
    sector o la de una guía convertida, 58.5); la generada para el cliente, de esa
    guía, con ``generated_guide_id`` («Generada», 58.4). Sin guía aún, ninguna.

    Con ``tools`` (las del agente), la que necesita una acción que no hacen entra
    «No aplica» con su razón (65.8). Sin ``tools``, todas entran como aplicables."""
    from nexus_api.services.builder.guides import resolve

    if guide is None:
        guide = await resolve.for_client(session)
    if guide is None:
        return 0
    if guide.source == "generated" and guide.generated_id is not None:
        items = [
            {
                **item,
                "sector_test_ref": f"generated:{guide.generated_id}#{item.get('key')}",
                "generated_guide_id": guide.generated_id,
            }
            for item in guide.tests
        ]
    elif guide.catalog_key is not None:
        catalog = await latest(session, guide.catalog_key)
        if catalog is None:
            return 0
        items = [
            {**item, "sector_test_ref": f"{guide.catalog_key}@{catalog.version}#{item['key']}"}
            for item in catalog.tests
        ]
    else:
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
    for item in items:
        if item["sector_test_ref"] in have:
            continue
        if tools is not None:
            item = {**item, "not_applicable_reason": not_applicable_reason(item, tools)}
        await add_test(session, suite, item, kind="sector", by="system")
        added += 1
    return added


__all__ = [
    "TESTS_PER_SECTOR",
    "SectorCatalogError",
    "SectorTest",
    "add_sector_tests",
    "client_sector",
    "latest",
    "needs_of",
    "not_applicable_reason",
    "publish",
    "validate_tests",
]
