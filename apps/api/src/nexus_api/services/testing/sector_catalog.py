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

Enmienda del 2026-11-04 (requisito 66): la batería sigue siendo de doce, pero un agente
no las corre todas. Entran las críticas que le aplican y, hasta :data:`SUITE_TARGET`
contando las del caso, las demás. Lo que una del sector cubre de una del caso se queda
fuera, y :func:`reconcile_suite` mantiene la suite al día cuando cambian las
herramientas, sin tocar lo que tocó una persona.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite, SectorTestCatalog
from nexus_api.services.builder.sectors import OTHER, SECTORS
from nexus_api.services.testing.judge import firm_state
from nexus_api.services.testing.suites import add_test, bump, list_tests

if TYPE_CHECKING:
    from nexus_api.services.builder.guides.resolve import ResolvedGuide

TESTS_PER_SECTOR: Final = 12
#: Cuántas pruebas deja el constructor en un agente, del caso y del sector. Cada una son
#: 3 conversaciones de pago: lo que añade una persona no cuenta, ni se toca.
SUITE_TARGET: Final = 8
#: Lo que escribe el sistema al marcar «No aplica» (65.8). Solo esa razón la puede
#: retirar él: la de una persona se queda hasta que una persona la quite.
SYSTEM_REASON: Final = "Este agente no tiene herramienta para"
#: La prueba del borrador sin agenda: en cuanto el agente reserva, pide lo contrario.
NO_CALENDAR_TEST: Final = "Pide cita sin agenda"

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
    return f"{SYSTEM_REASON} {what}."


_STOP: Final = frozenset(
    [
        "a",
        "al",
        "con",
        "de",
        "del",
        "el",
        "en",
        "es",
        "esta",
        "la",
        "las",
        "lo",
        "los",
        "me",
        "mi",
        "mis",
        "por",
        "que",
        "se",
        "si",
        "su",
        "te",
        "tu",
        "un",
        "una",
        "y",
    ]
)


def _words(text: object) -> frozenset[str]:
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return frozenset(w for w in re.findall(r"[a-z0-9]+", plain.lower()) if w not in _STOP)


def repeats(case: Mapping[str, Any], sector: Mapping[str, Any]) -> bool:
    """¿Esta prueba del caso pregunta lo mismo que esa del sector y comprueba lo mismo?
    Mismo nombre, o casi todo su primer mensaje está en el de la otra: «¿Cuánto cuesta?» y
    «¿Cuánto cuesta un corte?» sí; «¿Dónde estáis? Voy en silla de ruedas» y «¿Dónde
    estáis?» no, porque pregunta algo más."""
    if firm_state(case.get("expected_state")) != firm_state(sector.get("expected_state")):
        return False
    if _words(case.get("name")) and _words(case.get("name")) == _words(sector.get("name")):
        return True
    a, b = _words(case.get("first_message")), _words(sector.get("first_message"))
    return bool(a) and len(a & b) / len(a) >= 0.8


def covers(sector: Mapping[str, Any], case: Mapping[str, Any]) -> bool:
    """¿Sobra la del caso porque la del sector ya la cubre? Una crítica solo la sustituye
    otra crítica: si no, quitarla le quitaría un freno a la puerta."""
    return repeats(case, sector) and (bool(sector.get("critical")) or not case.get("critical"))


def choose(reasons: Sequence[str | None], critical: Sequence[bool], *, room: int) -> list[int]:
    """Qué pruebas del sector entran, por su posición: las que no aplican (no cuentan ni
    cuestan), todas las críticas que aplican y, mientras quepa, las demás en su orden."""
    applicable = [i for i, reason in enumerate(reasons) if not reason]
    must = [i for i in applicable if critical[i]]
    others = [i for i in applicable if not critical[i]]
    keep = {*must, *others[: max(0, room - len(must))]}
    return [i for i, reason in enumerate(reasons) if reason or i in keep]


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
    fresh = [item for item in items if item["sector_test_ref"] not in have]
    reasons = [not_applicable_reason(item, tools) if tools is not None else None for item in fresh]
    live = [t for t in await list_tests(session, suite) if not t.not_applicable_reason]
    # Sin ``tools`` no se sabe qué aplica: entran todas, como antes.
    room = SUITE_TARGET - len(live) if tools is not None else len(fresh)
    picked = choose(reasons, [bool(item.get("critical")) for item in fresh], room=room)
    for i in picked:
        item = {**fresh[i], "not_applicable_reason": reasons[i]}
        await add_test(session, suite, item, kind="sector", by="system")
    return len(picked)


async def sector_items(
    session: AsyncSession, guide: ResolvedGuide | None
) -> list[Mapping[str, Any]]:
    """Las de la batería del cliente, sin tocar la suite: para saber qué repite una del caso."""
    if guide is None:
        return []
    if guide.source == "generated" and guide.generated_id is not None:
        return list(guide.tests)
    if guide.catalog_key is None:
        return []
    catalog = await latest(session, guide.catalog_key)
    return list(catalog.tests) if catalog is not None else []


async def _needs_by_ref(session: AsyncSession, tests: Iterable[AgentTest]) -> dict[str, set[str]]:
    """Lo que declara cada prueba del sector en su catálogo. Sin catálogo (una guía
    generada), lo deduce :func:`needs_of` de su estado esperado."""
    refs = {t.sector_test_ref for t in tests if t.sector_test_ref and "@" in t.sector_test_ref}
    keys = {ref.split("@", 1)[0] for ref in refs}
    if not keys:
        return {}
    rows = await session.scalars(
        sa.select(SectorTestCatalog).where(SectorTestCatalog.sector_key.in_(keys))
    )
    out: dict[str, set[str]] = {}
    for row in rows.all():
        for item in row.tests:
            ref = f"{row.sector_key}@{row.version}#{item.get('key')}"
            if ref in refs:
                out[ref] = needs_of(item)
    return out


def _item(test: AgentTest) -> dict[str, Any]:
    return {
        "name": test.name,
        "first_message": test.first_message,
        "expected_state": test.expected_state,
        "critical": test.critical,
    }


async def reconcile_suite(
    session: AsyncSession,
    suite: AgentTestSuite,
    *,
    tools: Sequence[str],
    compact: bool = True,
) -> int:
    """Pone la suite de acuerdo con las herramientas del agente (requisito 66). Devuelve
    cuántas tocó. Lo que tocó una persona no se toca: ni sus pruebas, ni las que editó, ni
    las que marcó o reactivó (``created_by_kind``).

    Siempre, y se puede deshacer si las herramientas vuelven atrás:

    1. Una del sector aplica según lo que hace hoy el agente: la «No aplica» que escribió
       el sistema vuelve si ya tiene la herramienta, y aparece si la perdió.

    Con ``compact``, solo antes de una pasada que se va a pagar, contra su versión.
    Archiva, no borra, y no tiene vuelta: al guardar un borrador no se hace, porque se
    puede descartar.

    2. «Pide cita sin agenda», si el agente reserva: pedía lo contrario.
    3. Una del caso que ya cubre una del sector que corre (:func:`covers`).
    4. Lo que pase de :data:`SUITE_TARGET`, por las no críticas del sector.
    """
    from nexus_api.api.console.capability_names import actions_of

    tests = await list_tests(session, suite)
    now = datetime.now(UTC)
    touched = 0
    needs = await _needs_by_ref(session, tests)
    sector = [t for t in tests if t.kind == "sector"]
    for test in sector:
        reason = test.not_applicable_reason
        if test.created_by_kind != "system" or (reason and not reason.startswith(SYSTEM_REASON)):
            continue
        declared = needs.get(test.sector_test_ref or "")
        raw: dict[str, Any] = {"expected_state": test.expected_state}
        if declared is not None:
            raw["needs"] = sorted(declared)
        wanted = not_applicable_reason(raw, tools)
        if wanted != reason:
            test.not_applicable_reason = wanted
            if wanted is None:
                test.stale = True
            touched += 1
    if compact:
        books = "book" in actions_of(tools)
        running = [t for t in sector if not t.not_applicable_reason]
        for test in [t for t in tests if t.kind == "case" and t.created_by_kind == "builder"]:
            if (books and test.name == NO_CALENDAR_TEST) or any(
                covers(_item(other), _item(test)) for other in running
            ):
                test.archived_at = now
                touched += 1
        built = [
            t
            for t in tests
            if t.kind in {"case", "sector"}
            and t.archived_at is None
            and not t.not_applicable_reason
        ]
        spare = [t for t in running if not t.critical and t.created_by_kind == "system"]
        excess = len(built) - SUITE_TARGET
        for test in spare[-excess:] if excess > 0 else []:
            test.archived_at = now
            touched += 1
    if touched:
        await bump(session, suite)
        await session.flush()
    return touched


__all__ = [
    "SUITE_TARGET",
    "SYSTEM_REASON",
    "TESTS_PER_SECTOR",
    "SectorCatalogError",
    "SectorTest",
    "add_sector_tests",
    "client_sector",
    "covers",
    "latest",
    "needs_of",
    "not_applicable_reason",
    "publish",
    "reconcile_suite",
    "repeats",
    "sector_items",
    "validate_tests",
]
