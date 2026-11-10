"""Garantía 3 — la ficha no entra en el grafo y ``kg.*`` sigue por cliente
(spec 047, T015 · requisito 8.2).

La ficha del negocio (bloque B) es la fuente única de sus datos: si también se
escribiera en ``kg_nodes``/``kg_edges`` habría dos copias que pueden divergir, y
el grafo —que el turno vuelca entero en el prompt— se convertiría en un segundo
camino por el que llegan datos del negocio sin pasar por la compilación
determinista (garantía 5).

**Barre, no enumera.** Se recorre con ``ast`` todo el código de producto (API,
scripts, worker, servidores MCP, canales) y se clasifica cada módulo que toca
el grafo:

- **escritores** (``KGNode(...)``, ``insert/update/delete`` sobre los modelos o
  SQL que escribe en las tablas): tienen que estar en ``KG_WRITERS`` con su
  razón, y ninguno puede ser un módulo de la ficha. Hoy no hay ninguno.
- **lectores**: cada uno con su caso adversarial (``KG_READERS``) que prueba
  que solo ve el grafo de su cliente.

Un módulo nuevo que toque el grafo pone el test en rojo hasta declararse.
"""

from __future__ import annotations

import ast
import re
import uuid
from datetime import date
from pathlib import Path

import pytest
from nexus_mcp import build_default_registry
from nexus_worker.runtime.pipeline import _load_kg_snapshot_text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import KGNode
from tests.integration.clients._reader_world import fake_dns  # noqa: F401 - fixture

from .conftest import set_tenant

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

APPS = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = (
    APPS / "api" / "src",
    APPS / "api" / "scripts",
    APPS / "worker" / "src",
    APPS / "mcp" / "src",
    APPS / "channels" / "src",
)
#: Los modelos declaran las tablas y sus FK; no leen ni escriben.
_DECLARATIONS = APPS / "api" / "src" / "nexus_api" / "db" / "models"

_KG_MODELS = frozenset({"KGNode", "KGEdge"})
_KG_SQL_WRITE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|COPY|TRUNCATE)\s+(?:public\.)?kg_(nodes|edges)\b",
    re.IGNORECASE,
)
_KG_SQL_ANY = re.compile(r"\bkg_(nodes|edges)\b")
#: Un módulo de la ficha del negocio, por su ruta (bloque B).
_BUSINESS_PROFILE = re.compile(r"business|ficha|client_spec|clientspec|profile", re.IGNORECASE)

#: Quién escribe en el grafo fuera de los tests, y por qué no es la ficha.
#: Vacío: hoy nada de producto escribe en el grafo.
KG_WRITERS: dict[str, str] = {}

#: Quién lee el grafo, y el caso que prueba que solo ve el de su cliente.
KG_READERS: dict[str, str] = {
    "worker/src/nexus_worker/runtime/pipeline.py": "test_the_turns_graph_snapshot_is_the_clients",
    "mcp/src/nexus_mcp/servers/commission/tools.py": (
        "test_commission_tools_do_not_reach_another_clients_barber"
    ),
    "api/src/nexus_api/core/isolation_enforcer.py": (
        "Razón: es la lista de tablas cuyas consultas vigila el enforcer; nombra el "
        "grafo, no lo lee."
    ),
    # Spec 048: el barbero de una cita casa con una persona de Reservas por nombre.
    "api/src/nexus_api/services/reservations/passing.py": (
        "test_passing_to_reservas_never_reads_another_clients_barber"
    ),
    "mcp/src/nexus_mcp/_agenda.py": "test_the_daily_report_never_takes_another_clients_barber",
}


def classify(source: str) -> set[str]:
    """``{"write"}``, ``{"read"}``, los dos o ninguno, para un módulo."""
    tree = ast.parse(source)
    kinds: set[str] = set()
    written_names: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _KG_MODELS:
                kinds.add("write")
                written_names.add(id(func))
            fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if fname in {"insert", "update", "delete"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Name) and first.id in _KG_MODELS:
                    kinds.add("write")
                    written_names.add(id(first))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _KG_SQL_WRITE.search(node.value):
                kinds.add("write")
            elif _KG_SQL_ANY.search(node.value):
                kinds.add("read")
    for node in ast.walk(tree):
        # Un uso del modelo que no es su escritura (``select(KGNode)``,
        # ``session.get(KGNode, …)``, ``KGNode.label``). El import no cuenta.
        if isinstance(node, ast.Name) and node.id in _KG_MODELS and id(node) not in written_names:
            kinds.add("read")
    return kinds


def sweep() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for root in SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            if path.is_relative_to(_DECLARATIONS):
                continue
            kinds = classify(path.read_text(encoding="utf-8"))
            if kinds:
                found[str(path.relative_to(APPS))] = kinds
    return found


# ── el barrido ──────────────────────────────────────────────────────────────


def test_nobody_writes_the_graph_but_the_declared_writers() -> None:
    writers = {path for path, kinds in sweep().items() if "write" in kinds}
    undeclared = sorted(writers - KG_WRITERS.keys())
    assert not undeclared, (
        f"código de producto que escribe en el grafo sin declararlo: {undeclared}. "
        "La ficha no se escribe en el grafo (requisito 8.2)."
    )
    assert not KG_WRITERS.keys() - writers, "escritores declarados que ya no escriben"


def test_no_business_profile_module_writes_the_graph() -> None:
    """Ni declarado: un módulo de la ficha que escribe en el grafo es el defecto."""
    writers = {path for path, kinds in sweep().items() if "write" in kinds}
    offenders = sorted(p for p in writers | KG_WRITERS.keys() if _BUSINESS_PROFILE.search(p))
    assert not offenders, f"la ficha escribe en el grafo: {offenders}"


def test_every_graph_reader_has_its_case() -> None:
    readers = {path for path, kinds in sweep().items() if "read" in kinds}
    assert {
        "worker/src/nexus_worker/runtime/pipeline.py",
        "mcp/src/nexus_mcp/servers/commission/tools.py",
    } <= readers, f"el barrido no ve a los lectores conocidos: {sorted(readers)}"
    undeclared = sorted(readers - KG_READERS.keys())
    assert not undeclared, f"lectores del grafo sin caso: {undeclared}"
    assert not KG_READERS.keys() - readers, "lectores declarados que ya no leen"
    for case in KG_READERS.values():
        if not case.startswith("Razón:"):
            assert callable(globals().get(case)), f"caso que no existe: {case}"


def test_the_scanner_tells_a_write_from_a_read() -> None:
    """Control del control, sobre el mismo ``classify`` que usa el barrido."""
    write = (
        "from nexus_api.db.models import KGNode\n"
        "session.add(KGNode(tenant_id=t, label='Service', properties=profile))\n"
    )
    raw = "await s.execute(text('INSERT INTO kg_edges (tenant_id) VALUES (:t)'))\n"
    orm = "await s.execute(sa.update(KGEdge).values(weight=1))\n"
    read = "rows = await s.execute(select(KGNode).where(KGNode.label == 'Barber'))\n"
    assert "write" in classify(write)
    assert classify(raw) == {"write"}
    assert "write" in classify(orm)
    assert classify(read) == {"read"}
    assert classify("x = 1\n") == set()


# ── los casos: solo el grafo del cliente ───────────────────────────────────


async def _graph(db_session, tenants_ab) -> dict[str, uuid.UUID]:
    a, b = tenants_ab["a"], tenants_ab["b"]
    ids: dict[str, uuid.UUID] = {}
    for tenant, key, pct in ((a, "a", 40), (b, "b", 60)):
        node = KGNode(
            id=uuid.uuid4(),
            tenant_id=tenant,
            label="Barber",
            properties={
                "name": f"BARBERO-{key.upper()}",
                "commission_model": "commission",
                "commission_pct": pct,
            },
        )
        async with db_session.begin():
            await set_tenant(db_session, tenant)
            db_session.add(node)
        ids[key] = node.id
    return ids


async def test_the_turns_graph_snapshot_is_the_clients(db_session, tenants_ab) -> None:
    """Lo que el turno vuelca del grafo en el system es solo de su cliente."""
    await _graph(db_session, tenants_ab)
    snap_a = await _load_kg_snapshot_text(tenants_ab["a"])
    snap_b = await _load_kg_snapshot_text(tenants_ab["b"])
    assert "BARBERO-A" in snap_a and "BARBERO-B" not in snap_a
    assert "BARBERO-B" in snap_b and "BARBERO-A" not in snap_b
    assert await _load_kg_snapshot_text(uuid.uuid4()) == ""


async def test_commission_tools_do_not_reach_another_clients_barber(db_session, tenants_ab) -> None:
    """Con el id de un barbero del vecino, la herramienta responde como si no
    existiera: el modelo de comisión del vecino (60 %) no se aplica."""
    ids = await _graph(db_session, tenants_ab)
    registry = build_default_registry()
    tools = ["commission.calculate_commission", "commission.get_barber_earnings"]

    async def commission(barber: uuid.UUID) -> dict:
        with tenant_context(tenants_ab["a"]):
            return await registry.dispatch(
                "commission.calculate_commission",
                {"barber_id": str(barber), "service_amount_cents": 10_000},
                whitelist=tools,
            )

    own = (await commission(ids["a"]))["result"]
    foreign = (await commission(ids["b"]))["result"]
    assert own["commission_cents"] == 4_000
    assert foreign["commission_cents"] == 0, "se aplicó el modelo del barbero de otro cliente"
    assert foreign["model"] == "employee"

    with tenant_context(tenants_ab["a"]):
        earnings = await registry.dispatch(
            "commission.get_barber_earnings",
            {
                "barber_id": str(ids["b"]),
                "from_date": date(2026, 1, 1).isoformat(),
                "to_date": date(2026, 12, 31).isoformat(),
            },
            whitelist=tools,
        )
    assert "BARBERO-B" not in repr(earnings)


async def _reservas_of_a(db_session, tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """En A, Reservas en Servicios con una persona que se llama como el barbero
    de B, y un servicio."""
    from nexus_api.db.models import (
        Customer,
        ReservationService,
        ReservationSettings,
        ReservationStaff,
    )
    from nexus_api.services.reservations.settings import apply_defaults

    settings = ReservationSettings(tenant_id=tenant_id, version=1, updated_by="tests")
    apply_defaults(settings, "services", None)
    staff = ReservationStaff(tenant_id=tenant_id, name="BARBERO-B")
    service = ReservationService(tenant_id=tenant_id, name="Corte", duration_minutes=30)
    customer = Customer(tenant_id=tenant_id, identifier="56911112222", preferences={})
    async with db_session.begin():
        await set_tenant(db_session, tenant_id)
        db_session.add_all([settings, staff, service, customer])
    return {"staff": staff.id, "service": service.id, "customer": customer.id}


async def test_passing_to_reservas_never_reads_another_clients_barber(
    db_session, tenants_ab
) -> None:
    """Spec 048: una cita de A que apunta al barbero de B (una FK de una
    columna no pasa por la RLS) no casa con la persona de A que se llama como
    él: el nombre del barbero de B no se lee desde A."""
    from datetime import UTC, datetime, timedelta

    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import Appointment, AppointmentStatus
    from nexus_api.services.reservations.passing import import_appointments

    a = tenants_ab["a"]
    ids = await _graph(db_session, tenants_ab)
    world = await _reservas_of_a(db_session, a)
    starts = datetime.now(UTC) + timedelta(days=3)
    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(
            Appointment(
                tenant_id=a,
                customer_id=world["customer"],
                barber_id=ids["b"],
                service_name="Corte",
                service_duration_min=30,
                starts_at=starts,
                ends_at=starts + timedelta(minutes=30),
                status=AppointmentStatus.BOOKED,
                idempotency_key="iso-46-cross",
            )
        )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        result = await import_appointments(session, a, now=datetime.now(UTC))
    assert result.imported == []
    assert [(n["reason"], n["staff_name"]) for n in result.not_imported] == [
        ("staff_not_found", None)
    ]


async def test_the_daily_report_never_takes_another_clients_barber(db_session, tenants_ab) -> None:
    """Spec 048: una reserva de A con una persona que se llama como el barbero
    de B no cobra con el modelo de B (60 %): desde A, el grafo de B no existe."""
    from datetime import UTC, datetime, timedelta

    from nexus_api.db.models import Reservation

    a = tenants_ab["a"]
    ids = await _graph(db_session, tenants_ab)
    world = await _reservas_of_a(db_session, a)
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    async with db_session.begin():
        await set_tenant(db_session, a)
        db_session.add(
            Reservation(
                tenant_id=a,
                mode="services",
                status="done",
                starts_at=today,
                ends_at=today + timedelta(minutes=30),
                staff_id=world["staff"],
                service_id=world["service"],
                service_name="Corte",
                price_minor=10_000,
                currency="CLP",
                customer_id=world["customer"],
                origin="agent",
                channel="whatsapp",
                created_by_kind="system",
                version=1,
            )
        )
    registry = build_default_registry()
    with tenant_context(a):
        report = await registry.dispatch(
            "commission.get_daily_report",
            {"on_date": today.date().isoformat()},
            whitelist=["commission.get_daily_report"],
        )
    result = report["result"]
    assert result["appointments_count"] == 1
    assert result["total_commission_cents"] == 0, "se aplicó el modelo del barbero de B"
    assert all(b["barber_id"] != str(ids["b"]) for b in result["by_barber"])


# ── la ficha, con datos: el alta y la lectura no tocan el grafo ──────────────
#
# Spec 047, T042 a T045. El barrido de arriba prueba que ningún módulo de la
# ficha **puede** escribir en el grafo; este caso prueba que, de hecho, un alta
# con web y la lectura completa de esa web dejan ``kg_nodes`` y ``kg_edges`` del
# cliente vacíos: lo leído va a la ficha (y a sus sugerencias), nunca al grafo.


@pytest.mark.usefixtures("fake_dns")
async def test_the_alta_and_the_reading_write_nothing_to_the_graph(
    client, db_session, console_world, fake_redis
) -> None:
    import httpx
    import respx
    import sqlalchemy as sa

    from nexus_api.db.models import KGEdge
    from nexus_api.db.models.business import (
        BusinessLocation,
        BusinessProfile,
        BusinessSuggestion,
    )
    from tests.integration.clients._reader_world import (
        CULTOR_READ,
        FakeExtractor,
        create_client,
        page,
        roomy,
        run_reader,
        scoped,
        tenant_of,
    )

    await roomy(db_session, console_world)
    a = console_world["a"]
    created = await create_client(
        client, a["headers"](), name="Barbería Cultor", niche="Barbería", info="cultorbarber.com"
    )
    tenant_id = await tenant_of(db_session, a["partner_id"], created["ref"])
    with respx.mock(assert_all_called=False) as router:
        router.get("https://cultorbarber.com/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
        )
        router.get("https://cultorbarber.com/").mock(
            return_value=httpx.Response(200, html=page("<p>Corte 15 €. Lunes a sábado.</p>"))
        )
        # La lectura y la identificación del sector que el alta dejó en cola (57.2).
        assert await run_reader(fake_redis, FakeExtractor(reply=CULTOR_READ)) == 2

    # La ficha sí recibió lo leído (aplicado en una ficha vacía, o al lado como
    # sugerencia si una persona ya lo había escrito)…
    assert await scoped(db_session, tenant_id, sa.select(BusinessProfile))
    assert await scoped(db_session, tenant_id, sa.select(BusinessLocation)) or await scoped(
        db_session, tenant_id, sa.select(BusinessSuggestion)
    )
    # …y el grafo del cliente sigue vacío.
    assert await scoped(db_session, tenant_id, sa.select(KGNode)) == []
    assert await scoped(db_session, tenant_id, sa.select(KGEdge)) == []
