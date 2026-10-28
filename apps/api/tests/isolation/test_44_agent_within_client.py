"""Garantía 9 — el agente dentro del cliente, barrida y adversarial (spec 047, T014).

Requisitos 56.3, 37.2, 37.4, 37.5, 11.4 y 32.6. Dos agentes de un mismo
cliente son filas legítimas del mismo tenant: la RLS no los separa. Lo que es
**de un agente** —su versión y su prompt, sus herramientas, su configuración de
canal, y desde la 047 su conocimiento propio, su memoria propia, sus servicios y
sus activaciones— no lo alcanza su hermano por ninguna vía.

**Barre, no enumera** (constitución §I). Dos barridos, cada uno con su caso o su
razón escrita por elemento, y rojo si aparece uno sin ella:

1. **Toda tabla con una columna ``agent_id`` o una FK a ``agents``**, leída de
   ``pg_class``/``pg_constraint`` en todos los esquemas (``AGENT_TABLES``).
2. **Toda herramienta del registro MCP** (``build_default_registry``): las que
   leen datos de un agente tienen su caso; las demás, la razón por la que no
   tienen dimensión de agente (``TOOL_FAMILIES``). Un módulo de servidor que
   empiece a leer agentes sin estar declarado aquí también lo pone en rojo.

Hoy las vías son la recuperación (el cargador de la versión), la compilación (el
prompt que llega al modelo), las herramientas y el número. El constructor, el
copiloto, las sugerencias y la derivación de Recepción llegan con sus tablas y
sus herramientas, y el barrido las pide el día que existan.
"""

from __future__ import annotations

import ast
import importlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from nexus_mcp import build_default_registry
from nexus_worker.runtime.pipeline import _build_handler_messages
from sqlalchemy import select

from nexus_api.core.errors import IsolationViolation
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
)
from nexus_api.services.agents import agent_for_channel

from ._tenant_catalog import all_tables
from .conftest import seed_active_agent_config

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

MCP_SERVERS = Path(__file__).resolve().parents[3] / "mcp" / "src" / "nexus_mcp" / "servers"
WORKER_RUNTIME = Path(__file__).resolve().parents[3] / "worker" / "src" / "nexus_worker" / "runtime"


@dataclass(frozen=True)
class Case:
    """Lo cubre un test, por su nombre (``modulo::funcion`` o una función de este
    archivo). ``test_every_case_points_at_a_real_test`` comprueba que existe."""

    test: str


@dataclass(frozen=True)
class Reason:
    """Por qué ningún agente alcanza lo de su hermano por aquí. Cuando deje de
    ser cierto, la entrada pasa a ``Case``."""

    why: str


# ── barrido 1: las tablas con agente ───────────────────────────────────────

AGENT_TABLES: dict[str, Case | Reason] = {
    "agent_configs": Case("test_a_version_never_carries_its_siblings_prompt_tools_or_policies"),
    "channels": Case("test_a_number_answers_with_its_own_agent_and_its_own_config"),
    "reservations": Case("test_tools_read_the_agent_of_the_turns_number"),
    "jobs": Reason(
        "Trabajos largos de la consola (0175). Ningún agente los lee: el runtime "
        "que conversa con el cliente final no importa el modelo (lo comprueba "
        "test_the_agent_runtime_does_not_read_jobs), y la consola llega a un "
        "trabajo solo por su id, con ``job_tenant`` y la pertenencia al partner. "
        "Cuando el constructor lea el agente de un trabajo para construir otro, "
        "pasa a caso."
    ),
    "messages": Reason(
        "``agent_id`` dice qué agente contestó. El historial se lee por "
        "conversación (``_load_recent_history``), no por agente: la conversación "
        "es del cliente y de su número, y con la derivación de Recepción el "
        "agente de destino sigue el mismo hilo a propósito (requisito 53.2)."
    ),
    "usage_records": Reason(
        "Medición: atribuye el gasto al agente que respondió. Ningún agente la "
        "lee; la leen el medidor, la consola del partner (agregados) y el admin."
    ),
    "usage_ledger": Reason("Libro del partner (RLS por ``partner_id``): ningún agente lo lee."),
    "agent_services": Case("test_an_agent_never_offers_nor_books_its_siblings_services"),
    "agent_model_certifications": Case(
        "test_the_router_never_chooses_with_a_siblings_certification"
    ),
    "proposals": Reason(
        "Propuestas del constructor y del copiloto (0187). El runtime que conversa "
        "no las lee (test_the_agent_runtime_does_not_read_builder_tables). La "
        "consola aplica una propuesta solo sobre el agente de la ruta: la de un "
        "hermano es un 404 opaco (tests/integration/builder/test_proposals.py)."
    ),
    "agent_test_suites": Reason(
        "La suite de pruebas de cada agente (0187). Solo la leen la consola, por "
        "el agente de la ruta, y el trabajo de pruebas de ese agente; el runtime "
        "no (test_the_agent_runtime_does_not_read_builder_tables)."
    ),
    "agent_test_runs": Reason(
        "Las pasadas de la suite de un agente (0187), con su versión. Las escribe y "
        "las lee el trabajo de pruebas de ese agente, en el lote de su cliente "
        "(garantía 7); el runtime no las lee."
    ),
    "channel_signup_links": Reason(
        "El enlace del dueño (0191) guarda el agente al que irá el número. Solo lo "
        "leen la consola, por el agente de la ruta (el de un hermano es un 404), y "
        "el alta, que asigna el número a ese agente; ningún agente lo lee "
        "(tests/integration/channels/test_owner_link.py)."
    ),
    # ``handled_by_agent_id`` (0191) es el agente al que Recepción derivó la
    # conversación, y desde ese turno es el que responde: solo un destino de su
    # lista y de su cliente, nunca en pausa ni archivado, y con el resumen y no
    # el conocimiento de Recepción (T178).
    "conversations": Case(
        "test_44c_reception::test_reception_never_hands_off_outside_its_list_and_its_client"
    ),
    "knowledge_documents": Case(
        "test_44b_agent_knowledge::test_a_siblings_knowledge_never_reaches_the_prompt_nor_the_search"
    ),
    "knowledge_chunks": Case(
        "test_44b_agent_knowledge::test_a_siblings_knowledge_never_reaches_the_prompt_nor_the_search"
    ),
    "knowledge_chunk_vectors": Case(
        "test_44b_agent_knowledge::test_a_siblings_knowledge_never_reaches_the_prompt_nor_the_search"
    ),
    "agent_memories": Case("test_44b_agent_knowledge::test_own_memory_is_never_a_siblings"),
    "agent_memory_versions": Reason(
        "El historial de ``agent_memories`` (0193 copia ``agent_id``). Lo escribe el "
        "disparador y no lo lee ningún agente: la herramienta de memoria lee "
        "``agent_memories`` con su capa (test_44b_agent_knowledge)."
    ),
    "knowledge_revisions": Reason(
        "Un contador por capa (0193). Solo dice que la capa cambió; no lleva "
        "contenido y ningún agente lo lee para responder."
    ),
    "turn_sources": Reason(
        "Las fuentes de cada respuesta (0193), escritas por el turno del agente que "
        "respondió. Las leen el copiloto y las sugerencias del agente de la ruta; "
        "no entran en el prompt de nadie."
    ),
    "agent_connector_activations": Reason(
        "La activación de una integración en un agente (0194). El turno lee solo las "
        "filas de su agente (``activations.tool_policy``); una conexión activada en un "
        "hermano cuenta como gestionada y sus herramientas quedan bloqueadas para este "
        "(tests/integration/connectors/test_activations.py::"
        "test_the_runtime_applies_each_permission, el agente «none»)."
    ),
    "inbox_corrections": Reason(
        "Las correcciones que manda una persona del cliente desde la Bandeja (0198). "
        "Ningún agente las lee: no entran en un prompt, en la búsqueda, en las "
        "herramientas ni en el constructor. Las leen la persona del cliente (con la "
        "RLS de todo el cliente) y el partner por el agente de la ruta "
        "(``corrections.for_partner`` y las mejoras del agente: la de un hermano no "
        "existe)."
    ),
    "agent_suggestions": Reason(
        "Las sugerencias semanales de un agente (0199): el resultado agregado de leer "
        "sus conversaciones en el worker, sin ids de conversación ni de contacto. Las "
        "escribe la pasada de ese agente y solo las lee la consola por el agente de la "
        "ruta (la de un hermano es un 404: tests/integration/improvement/"
        "test_suggestions.py). El runtime no las lee ni entran en ningún prompt "
        "(test_the_agent_runtime_does_not_read_builder_tables)."
    ),
    "agent_monthly_spend": Reason(
        "El gasto del mes de cada agente para su tope (0195). Lo escribe la medición "
        "con el agente del turno y lo leen la puerta de ese agente y la consola; no "
        "lleva contenido ni entra en ningún prompt."
    ),
    "client_wallet_entries": Reason(
        "Los asientos de la bolsa del cliente (0195): la bolsa es del cliente y la "
        "comparten sus agentes a propósito (D25). ``agent_id`` dice qué turno se "
        "cobró; ningún agente lee el libro."
    ),
    "qa.threads": Reason(
        "QA Playground de los operadores de Auphere (RLS por ``operator_id``): "
        "``agent_id`` es el agente probado y ningún agente lee estos hilos."
    ),
}


async def agent_tables() -> set[str]:
    """Tablas con una columna ``agent_id`` o una FK hacia ``agents``."""
    async with get_sessionmaker()() as session:
        tables = await all_tables(session)
    return {
        t.name
        for t in tables.values()
        if "agent_id" in t.columns or any(fk.target == "agents" for fk in t.foreign_keys)
    }


async def test_every_agent_table_has_its_case_or_its_reason() -> None:
    found = await agent_tables()
    assert "jobs" in found and "agent_configs" in found, f"barrido roto: {sorted(found)}"
    missing = sorted(found - AGENT_TABLES.keys())
    assert not missing, (
        f"tablas con agente sin caso ni razón (garantía 9): {missing}. "
        "Escribe el test adversarial o la razón por la que ningún agente lee lo "
        "de su hermano por ahí."
    )
    stale = sorted(AGENT_TABLES.keys() - found)
    assert not stale, f"entradas para tablas que ya no tienen agente: {stale}"


# ── barrido 2: las herramientas del registro ───────────────────────────────

_CLIENT_DATA = (
    "Lee o escribe datos del cliente o de la conversación del turno, que no "
    "tienen dimensión de agente: los comparten todos los agentes del cliente. "
)

#: Familia → (caso o razón, nombres exactos). Los nombres son exhaustivos: una
#: herramienta nueva en una familia conocida también tiene que añadirse aquí, y
#: eso obliga a mirar si lee algo del agente.
TOOL_FAMILIES: dict[str, tuple[Case | Reason, frozenset[str]]] = {
    # Spec 047, T178: la única herramienta que nombra un agente, limitada a la
    # lista de Recepción y a su cliente.
    "reception": (
        Case("test_44c_reception::test_reception_never_hands_off_outside_its_list_and_its_client"),
        frozenset({"reception.handoff"}),
    ),
    "agent_reads": (
        Case("test_tools_read_the_agent_of_the_turns_number"),
        frozenset(
            {
                # Los revisores de pago del agente del número.
                "payments.request_review",
                # La política de recordatorios del agente del número.
                "notification.schedule_reminder",
                # Atribuyen la reserva al agente del número.
                "reservas.create",
                "reservas.answer_offer",
            }
        ),
    ),
    "agent_services": (
        # Spec 047, T058 (requisito 11.4): los servicios del agente del número.
        Case("test_an_agent_never_offers_nor_books_its_siblings_services"),
        frozenset(
            {
                "reservas.services",
                "reservas.find_slots",
                "reservas.join_waitlist",
                "booking.check_availability",
                "booking.create_appointment",
            }
        ),
    ),
    "booking": (
        Reason(_CLIENT_DATA + "Citas del cliente final del turno (garantía 8, test_35)."),
        frozenset(
            {
                "booking.cancel_appointment",
                "booking.get_appointments",
                "booking.modify_appointment",
            }
        ),
    ),
    "reservas": (
        Reason(
            _CLIENT_DATA + "Reservas ya hechas de la persona del turno: cambiarlas, "
            "cancelarlas o confirmarlas no elige servicio (lo trae la reserva)."
        ),
        frozenset(
            {
                "reservas.cancel",
                "reservas.confirm_attendance",
                "reservas.list_mine",
                "reservas.reschedule",
            }
        ),
    ),
    "client": (
        Reason(_CLIENT_DATA + "Historial y preferencias del cliente final del turno."),
        frozenset({"client.get_history", "client.get_preferences", "client.update_preferences"}),
    ),
    "queue": (
        Reason(_CLIENT_DATA + "La cola del local."),
        frozenset(
            {
                "queue.check_in",
                "queue.get_estimated_wait",
                "queue.get_position",
                "queue.join_queue",
                "queue.remove_from_queue",
            }
        ),
    ),
    "commission": (
        Reason(_CLIENT_DATA + "Comisiones del personal del negocio."),
        frozenset(
            {
                "commission.calculate_commission",
                "commission.get_barber_earnings",
                "commission.get_daily_report",
            }
        ),
    ),
    "notification": (
        Reason(_CLIENT_DATA + "Envían a la conversación del turno."),
        frozenset(
            {
                "notification.cancel_scheduled",
                "notification.send_audio",
                "notification.send_document",
                "notification.send_image",
                "notification.send_location",
                "notification.send_reaction",
                "notification.send_template",
                "notification.send_text",
                "notification.send_video",
                "response.send_interactive",
            }
        ),
    ),
    "escalate_operator": (
        Reason(_CLIENT_DATA + "Pasan la conversación del turno a una persona o al dueño."),
        frozenset({"escalate.escalate_to_human", "operator.consult_owner"}),
    ),
    "catalog_inventory": (
        Reason(_CLIENT_DATA + "Catálogo de Meta e inventario del negocio."),
        frozenset(
            {
                "catalog.get_product",
                "catalog.search_products",
                "inventory.check_stock",
                "inventory.get_product",
                "inventory.low_stock",
                "inventory.search_products",
            }
        ),
    ),
    "billing": (
        Reason(_CLIENT_DATA + "Cuentas de Amigable Cobro del negocio."),
        frozenset(
            {
                "billing.add_charge",
                "billing.apply_discount",
                "billing.create_account",
                "billing.find_client",
                "billing.get_account",
                "billing.get_debtor_by_phone",
                "billing.get_my_debt",
                "billing.list_overdue",
                "billing.register_payment",
                "billing.send_reminders",
                "billing.update_account",
                "billing.update_status",
            }
        ),
    ),
    "woocommerce": (
        Reason(_CLIENT_DATA + "La tienda WooCommerce del negocio."),
        frozenset(
            {
                "woocommerce.add_order_note",
                "woocommerce.build_checkout_link",
                "woocommerce.create_order",
                "woocommerce.get_customer",
                "woocommerce.get_order",
                "woocommerce.get_product",
                "woocommerce.list_categories",
                "woocommerce.list_customers",
                "woocommerce.list_orders",
                "woocommerce.list_product_variations",
                "woocommerce.list_products",
                "woocommerce.update_order",
                "woocommerce.update_order_status",
            }
        ),
    ),
}

#: Los módulos de servidor que leen el agente del turno. Se detectan en el
#: código (abajo); declararlos aquí hace que uno nuevo sea una decisión visible.
AGENT_READING_SERVERS = frozenset({"payments", "notification", "reservas", "booking", "reception"})
_AGENT_READ = re.compile(
    r"agent_for_channel|agent_for_conversation|AgentConfigRepository|Channel\.agent_id"
    r"|principal_agent_id"
)

#: Un argumento que nombra a un agente: el modelo elegiría de quién leer.
AGENT_AXIS = frozenset({"agent", "agent_id", "agent_name", "to_agent_id", "from_agent_id"})


def test_every_registry_tool_has_its_case_or_its_reason() -> None:
    registry = build_default_registry()
    names = set(registry.names())
    assert len(names) >= 50, f"el registro tiene {len(names)} herramientas; ¿se rompió?"
    declared: dict[str, str] = {}
    for family, (_entry, tools) in TOOL_FAMILIES.items():
        for tool in tools:
            assert tool not in declared, f"{tool} está en {declared[tool]} y en {family}"
            declared[tool] = family
    missing = sorted(names - declared.keys())
    assert not missing, (
        f"herramientas sin caso ni razón de garantía 9: {missing}. ¿Leen algo "
        "de un agente? Si sí, su caso adversarial; si no, a su familia con la razón."
    )
    stale = sorted(declared.keys() - names)
    assert not stale, f"entradas para herramientas que ya no existen: {stale}"


def test_the_servers_that_read_an_agent_are_declared() -> None:
    """Un servidor que empieza a leer agentes entra en ``agent_reads``."""
    reading = {
        path.parent.name
        for path in MCP_SERVERS.glob("*/*.py")
        if _AGENT_READ.search(path.read_text(encoding="utf-8"))
    }
    assert reading == AGENT_READING_SERVERS, (
        f"servidores que leen el agente: {sorted(reading)}; declarados: "
        f"{sorted(AGENT_READING_SERVERS)}. Sus herramientas que lo lean van a "
        "``agent_reads`` con su caso."
    )


def test_no_tool_lets_the_model_name_an_agent() -> None:
    """El agente del turno lo pone el servidor, como el cliente y el cliente final.

    ``reception.handoff`` (requisito 53.3) acepta un destino, limitado a la lista de
    Recepción y a su cliente: es la única, con su caso en ``test_44c_reception``."""
    registry = build_default_registry()
    allowed = {"reception.handoff": ["to_agent_id"]}
    offenders = {
        d.name: sorted(AGENT_AXIS.intersection((d.parameters or {}).get("properties") or {}))
        for d in registry.get_tool_definitions(registry.names())
    }
    offenders = {k: v for k, v in offenders.items() if v and allowed.get(k) != v}
    assert not offenders, f"herramientas que dejan al modelo elegir agente: {offenders}"


def test_every_case_points_at_a_real_test() -> None:
    entries = [e for e in AGENT_TABLES.values() if isinstance(e, Case)] + [
        e for e, _tools in TOOL_FAMILIES.values() if isinstance(e, Case)
    ]
    for entry in entries:
        module_name, _, func = entry.test.rpartition("::")
        module = (
            importlib.import_module(f"tests.isolation.{module_name}")
            if module_name
            else importlib.import_module(__name__)
        )
        assert callable(getattr(module, func, None)), f"caso que no existe: {entry.test}"


def test_the_agent_runtime_does_not_read_jobs() -> None:
    """La razón de ``jobs``, comprobada: nada del runtime importa el modelo."""
    readers = []
    for path in WORKER_RUNTIME.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = {a.name for a in node.names}
                if node.module.endswith("models.jobs") or (
                    node.module.endswith("db.models") and "Job" in names
                ):
                    readers.append(str(path.relative_to(WORKER_RUNTIME)))
    assert not readers, f"el runtime del agente lee ``jobs``: {readers}"


def test_the_agent_runtime_does_not_read_builder_tables() -> None:
    """Las razones de ``proposals`` y de la suite: el runtime que conversa no
    importa los modelos del constructor ni de las pruebas (0187)."""
    builder_models = {
        "Proposal",
        "AgentTestSuite",
        "AgentTest",
        "AgentTestRun",
        "AgentTestResult",
        "AgentReview",
        "AgentSuggestion",
    }
    readers = []
    for path in WORKER_RUNTIME.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = {a.name for a in node.names}
                if node.module.endswith("models.agent_spec") or (
                    node.module.endswith("db.models") and names & builder_models
                ):
                    readers.append(str(path.relative_to(WORKER_RUNTIME)))
    assert not readers, f"el runtime del agente lee tablas del constructor: {readers}"


# ── el mundo: dos agentes de un cliente y un vecino ────────────────────────


@dataclass
class _Agent:
    agent_id: uuid.UUID
    marker: str
    tools: list[str]
    channel: Channel
    conversation: Conversation


async def _siblings(db_session, tenant_id: uuid.UUID) -> dict[str, _Agent]:
    """El principal («x», nace con la primera versión) y «y», cada uno con su
    número, su conversación en ese número, su prompt, sus herramientas y sus
    políticas, todo marcado."""
    marks = {k: f"MARCA-{k.upper()}-{uuid.uuid4().hex[:8]}" for k in ("x", "y")}
    tools = {"x": ["client.get_history"], "y": ["client.get_preferences"]}

    def policies(k: str) -> dict[str, object]:
        return {
            "marker": marks[k],
            "scheduled_reminders": {"templates": [f"tpl_{marks[k].lower()}"]},
            "payments": {"reviewers": [{"phone": "+3460000000" + ("1" if k == "x" else "2")}]},
        }

    x_cfg = await seed_active_agent_config(
        db_session,
        tenant_id=tenant_id,
        system_prompt=f"Eres X. {marks['x']}",
        tools=tools["x"],
        policies=policies("x"),
    )
    y = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name="Y")
    db_session.add(y)
    await db_session.commit()
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            agent_id=y.id,
            version=x_cfg.version + 1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered=f"Eres Y. {marks['y']}",
            channels=[],
            tools=tools["y"],
            policies=policies("y"),
            seed_template_ref=None,
        )
    )
    await db_session.commit()

    customer = Customer(tenant_id=tenant_id, identifier="+34600999888", preferences={})
    db_session.add(customer)
    await db_session.commit()
    out: dict[str, _Agent] = {}
    for key, agent_id in (("x", x_cfg.agent_id), ("y", y.id)):
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"g9-{key}-{uuid.uuid4().hex[:6]}",
            config={"marker": marks[key]},
            status=ChannelStatus.ACTIVE,
            agent_id=agent_id,
        )
        db_session.add(channel)
        await db_session.commit()
        conv = Conversation(
            tenant_id=tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        db_session.add(conv)
        await db_session.commit()
        out[key] = _Agent(agent_id, marks[key], tools[key], channel, conv)
    return out


def _flat_bundle(bundle) -> str:
    return repr((bundle.system_prompt, sorted(bundle.tools), bundle.policies))


# ── los casos ───────────────────────────────────────────────────────────────


async def test_a_version_never_carries_its_siblings_prompt_tools_or_policies(
    db_session, tenants_ab, agent_loader
) -> None:
    """Recuperación y compilación: lo que el cargador entrega y lo que llega al
    modelo como system son del agente, nunca de su hermano ni de otro cliente."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    world = await _siblings(db_session, a)
    neighbour = await seed_active_agent_config(
        db_session, tenant_id=b, system_prompt="MARCA-VECINO", tools=["queue.check_in"]
    )

    for me, sibling in (("x", "y"), ("y", "x")):
        bundle = await agent_loader.load(a, world[me].agent_id)
        flat = _flat_bundle(bundle)
        assert world[me].marker in flat
        assert world[sibling].marker not in flat, f"{me} recibió lo de {sibling}"
        assert "MARCA-VECINO" not in flat
        assert set(bundle.tools) == set(world[me].tools)

        messages = _build_handler_messages(
            {"user_message": "hola", "history": []},
            bundle,
            intent="info",
            kg_snapshot="",
            knowledge="",
        )
        compiled = repr(messages)
        assert world[me].marker in compiled
        assert world[sibling].marker not in compiled, f"el prompt de {me} lleva a {sibling}"

    # El agente de otro cliente, nombrado bajo este: la RLS no lo ve.
    with pytest.raises(IsolationViolation):
        await agent_loader.load(a, neighbour.agent_id)


async def test_a_number_answers_with_its_own_agent_and_its_own_config(
    db_session, tenants_ab
) -> None:
    """La configuración de un canal no toca otro canal (32.6): cada número
    resuelve su agente, y su configuración es la suya."""
    a = tenants_ab["a"]
    world = await _siblings(db_session, a)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        for me, sibling in (("x", "y"), ("y", "x")):
            channel_id = world[me].channel.id
            assert await agent_for_channel(session, channel_id) == world[me].agent_id
            config = await session.scalar(select(Channel.config).where(Channel.id == channel_id))
            assert config == {"marker": world[me].marker}
            assert world[sibling].marker not in repr(config)


async def test_tools_read_the_agent_of_the_turns_number(db_session, tenants_ab) -> None:
    """Las herramientas que leen un agente leen el del número de la conversación
    del turno, nunca el de un hermano: los revisores de pago y la política de
    recordatorios salen de su versión, y la reserva se atribuye a él.

    Ojo para la derivación de Recepción (requisito 53): estas herramientas
    deducen el agente del NÚMERO, no del turno. Cuando un número tenga a
    Recepción delante y conteste otro agente, este caso tiene que pasar a usar el
    agente del turno."""
    from nexus_mcp.servers.notification.tools import _reminder_policy
    from nexus_mcp.servers.reservas.tools import _turn

    from nexus_api.repositories import AgentConfigRepository

    a = tenants_ab["a"]
    world = await _siblings(db_session, a)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        for me, sibling in (("x", "y"), ("y", "x")):
            conv = world[me].conversation
            # notification.schedule_reminder
            policy = await _reminder_policy(session, conv)
            assert policy.templates == {f"tpl_{world[me].marker.lower()}"}
            # payments.request_review: la versión activa del agente del número.
            agent_id = await agent_for_channel(session, conv.channel_id)
            active = await AgentConfigRepository(session).get_active(agent_id=agent_id)
            assert active is not None and active.policies["marker"] == world[me].marker
            assert world[sibling].marker not in repr(active.policies)
            # reservas.create / reservas.answer_offer
            turn_conv, turn_agent = await _turn(session, conv.customer_id, conv.id)
            assert (turn_conv, turn_agent) == (conv.id, world[me].agent_id)


async def test_the_router_never_chooses_with_a_siblings_certification(
    db_session, tenants_ab
) -> None:
    """``agent_model_certifications`` (T140): la certificación de un despliegue
    es **del agente** que pasó su suite. El router de su hermano, en el mismo
    cliente, no la ve ni elige con ella; el vecino tampoco."""
    import json

    import sqlalchemy as sa
    from nexus_worker.runtime.model_resolver import RouteContext, chain_for

    from nexus_api.core import respond_catalog
    from nexus_api.services.certification import (
        AgentSuiteResult,
        SuiteCase,
        certified_deployments_for_agent,
        record_agent_certification,
    )
    from nexus_api.services.router_catalog import (
        ClassCertification,
        ProfilePolicy,
        load_snapshot,
    )

    a, b = tenants_ab["a"], tenants_ab["b"]
    world = await _siblings(db_session, a)
    key = f"g9-{uuid.uuid4().hex[:8]}/cert"
    caps = {"tools": True, "strict_structured_outputs": True, "cache_mode": "explicit"}
    await db_session.execute(
        sa.text(
            "INSERT INTO model_profiles (provider, model_id, display_name, family, residency, "
            "zero_retention, retention_how, contract_dpa, subprocessor_listed, status, "
            "capabilities, price_input_per_mtok, price_output_per_mtok) VALUES "
            "('prov_g9', :k, :k, 'fam', 'eu', true, 'store=false', true, true, 'active', "
            "CAST(:c AS jsonb), 1, 5)"
        ),
        {"k": key, "c": json.dumps(caps)},
    )
    await db_session.execute(
        sa.text(
            "INSERT INTO model_prices (deployment_id, valid_from, input, output) "
            "SELECT id, DATE '2026-10-01', 1, 5 FROM model_profiles WHERE model_id = :k"
        ),
        {"k": key},
    )
    await db_session.commit()
    try:
        async with get_sessionmaker()() as session:
            snap = await load_snapshot(session)
        deployment = snap.deployments[key]
        x_cfg = await db_session.scalar(
            select(AgentConfig).where(AgentConfig.agent_id == world["x"].agent_id)
        )
        assert x_cfg is not None
        passed = AgentSuiteResult(
            cases=(SuiteCase(test_id="t0", critical=True, passes=3),),
            score=90,
            reference_score=90,
            reference_deployment=key,
        )
        async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
            await record_agent_certification(
                session,
                tenant_id=a,
                agent_id=world["x"].agent_id,
                agent_config_id=x_cfg.id,
                deployment=deployment,
                suite_revision=1,
                result=passed,
                launched_by="partner",
            )

        async def certified(tenant: uuid.UUID, agent_id: uuid.UUID) -> frozenset[str]:
            async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant):
                return await certified_deployments_for_agent(
                    session, agent_id=agent_id, agent_config_id=None, suite_revision=None
                )

        assert await certified(a, world["x"].agent_id) == frozenset({key})
        assert await certified(a, world["y"].agent_id) == frozenset(), "lo de su hermano"
        assert await certified(b, world["x"].agent_id) == frozenset(), "lo de otro cliente"

        class_cert = ClassCertification(
            deployment_key=key,
            task="tool_turn",
            battery_version=1,
            quality=0.99,
            passed=True,
            scores={},
            certified_at=None,
            invalidated_at=None,
        )
        catalog = type(snap)(
            taxonomy=snap.taxonomy,
            deployments={key: deployment},
            class_certs=(class_cert,),
            profiles={},
            battery_version=1,
        )
        policy = ProfilePolicy.from_row("auto", 1, {"tasks": {"tool_turn": {"min_quality": 0.9}}})
        for me, expected in (("x", key), ("y", None)):
            ctx = RouteContext(
                tenant_id=a,
                catalog=catalog,
                agent_id=world[me].agent_id,
                eu_only=True,
                agent_certified=await certified(a, world[me].agent_id),
                now=1.0,
            )
            decision = chain_for("tool_turn", policy, ctx)
            assert decision.chosen == expected, (me, decision.rejected)
        assert {r.reason for r in decision.rejected} == {"agent_not_certified"}
    finally:
        await db_session.execute(
            sa.text("DELETE FROM model_profiles WHERE model_id = :k"), {"k": key}
        )
        await db_session.commit()
        respond_catalog.reset()


async def test_an_agent_never_offers_nor_books_its_siblings_services(
    db_session, tenants_ab
) -> None:
    """``agent_services`` (T058, requisito 11.4): cada agente ofrece solo sus
    servicios. Su hermano no los ve en su prompt compilado (la ficha entra con
    los servicios **del agente**), ni en ``reservas.services``, ni los encuentra
    con ``reservas.find_slots`` o ``booking.check_availability``, ni los reserva
    con ``reservas.create`` aunque el modelo invente su id. El agente es el del
    número de la conversación, nunca un argumento."""
    from datetime import date, timedelta

    from nexus_mcp.base import ToolError
    from nexus_mcp.registry import reset_default_registry

    from nexus_api.core.tenant_context import customer_context, tenant_context
    from nexus_api.db.models import (
        ClientAccess,
        Partner,
        ReservationSettings,
        ReservationStaff,
        Tenant,
    )
    from nexus_api.services.business import services_catalog
    from nexus_api.services.business.sections import Actor
    from nexus_api.services.reservations.settings import apply_defaults

    a = tenants_ab["a"]
    world = await _siblings(db_session, a)
    partner = Partner(id=uuid.uuid4(), name="G9 Partner", slug=f"g9-{uuid.uuid4().hex[:6]}")
    db_session.add(partner)
    await db_session.flush()
    tenant = await db_session.get(Tenant, a)
    assert tenant is not None
    tenant.timezone = "Europe/Madrid"
    tenant.business_hours = {
        d: [{"from": "09:00", "to": "20:00"}]
        for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    }
    db_session.add(
        ClientAccess(
            tenant_id=a, partner_id=partner.id, enabled=True, modules=["reservas"], updated_by="t"
        )
    )
    await db_session.commit()

    ops = Actor(kind="system", id="g9", origin="system")
    names = {"x": "Corte de X", "y": "Pedido de Y"}
    customers: dict[str, uuid.UUID] = {}
    services: dict[str, uuid.UUID] = {}
    async with tenant_scoped_session(db_session, a):
        settings = ReservationSettings(tenant_id=a, version=1, updated_by="t")
        apply_defaults(settings, "services", None)
        db_session.add(settings)
        db_session.add(ReservationStaff(tenant_id=a, name="Lucía", position=1))
        for key in ("x", "y"):
            service_id, _w = await services_catalog.create_service(
                db_session,
                services_catalog.ServiceData(name=names[key], bookable=True, duration_min=30),
                actor=ops,
            )
            services[key] = service_id
        for key in ("x", "y"):
            await services_catalog.set_agent_services(
                db_session,
                world[key].agent_id,
                serves_all=False,
                service_ids=[services[key]],
                actor=ops,
            )
            customer = Customer(
                tenant_id=a, identifier=f"3461{uuid.uuid4().int % 10**7:07d}", preferences={}
            )
            db_session.add(customer)
            await db_session.flush()
            db_session.add(
                Conversation(
                    tenant_id=a,
                    channel_id=world[key].channel.id,
                    customer_id=customer.id,
                    status=ConversationStatus.OPEN,
                )
            )
            customers[key] = customer.id

    reset_default_registry()
    registry = build_default_registry()
    day = (date.today() + timedelta(days=5)).isoformat()

    async def tool(key: str, name: str, args: dict[str, object]) -> dict[str, object]:
        with tenant_context(a), customer_context(customers[key]):
            try:
                env = await registry.dispatch(name, args, whitelist=[name])
            except ToolError as exc:
                return {"status": "error", "error": str(exc)}
        return dict(env)

    for me, sibling in (("x", "y"), ("y", "x")):
        async with tenant_scoped_session(db_session, a):
            mine = await services_catalog.services_for_agent(db_session, world[me].agent_id)
            prompt = await db_session.scalar(
                select(AgentConfig.system_prompt_rendered)
                .where(
                    AgentConfig.agent_id == world[me].agent_id,
                    AgentConfig.status == AgentConfigStatus.ACTIVE,
                )
                .execution_options(populate_existing=True)
            )
        assert [s.name for s in mine] == [names[me]]
        assert prompt is not None and names[me] in prompt
        assert names[sibling] not in prompt, f"el prompt de {me} lleva los servicios de {sibling}"

        listed = await tool(me, "reservas.services", {})
        assert {s["name"] for s in listed["result"]["services"]} == {names[me]}
        found = await tool(
            me, "reservas.find_slots", {"date": day, "service_id": str(services[sibling])}
        )
        assert found["result"]["why_closed"] == "not_offered", found
        booked = await tool(
            me,
            "reservas.create",
            {
                "date": day,
                "time": "10:00",
                "service_id": str(services[sibling]),
                "idempotency_key": f"g9-{me}",
            },
        )
        assert booked["result"]["refused"] == "not_offered", booked
        legacy = await tool(
            me,
            "booking.check_availability",
            {"service_name": names[sibling], "on_date": day, "duration_min": 30},
        )
        assert legacy["status"] == "error" and "not_offered" in str(legacy["error"])
        own = await tool(
            me,
            "booking.check_availability",
            {"service_name": names[me], "on_date": day, "duration_min": 30},
        )
        assert own["status"] == "ok", own
