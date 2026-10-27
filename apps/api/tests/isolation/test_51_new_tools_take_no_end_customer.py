"""Garantía 8 — ninguna herramienta deja que el modelo elija cliente final
(spec 047, T020 · requisitos 56.8, 15.4 y 52.5).

``test_37`` barre las herramientas que **las semillas** ponen en la lista de un
vertical de cara al cliente final. La 047 trae herramientas nuevas
(``reception.handoff``, las de servicios por agente) y el constructor, que
propone listas de herramientas. Aquí se barre **el registro entero**: toda
herramienta, todo argumento. Un argumento que nombra a una persona
(``END_CUSTOMER_AXIS``) solo se acepta si está en el inventario cerrado de
abajo, entrada a entrada y con su razón, y cada razón que se puede comprobar
tiene su caso:

- ``conversation_id``: lo pone el servidor. El runtime sobrescribe el que
  escriba el modelo con la conversación del turno, y ``reservas.*`` además
  descarta una conversación que no es del cliente final del turno.
- las herramientas de operador (``billing.*``, ``woocommerce.get_customer`` y
  compañía) solo están en semillas ``admin_only``.

Una herramienta nueva con un argumento así es roja, y el inventario no crece
(techo). La corrección con datos de un cliente final (52.5) llega con el bloque
de Mejora; hoy no hay correcciones que barrer.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import yaml
from nexus_mcp import build_default_registry
from nexus_worker.runtime.llm import ToolCall
from nexus_worker.runtime.pipeline import _dispatch_tool

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Conversation, ConversationStatus, Customer

from .conftest import seed_active_agent_config, seed_channel
from .test_37_customer_axis_contract import CUSTOMER_AXIS, SEEDS

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

#: Un argumento que nombra o localiza a una persona. Parte del de ``test_37`` y
#: añade lo que identifica a alguien sin llamarse «customer».
END_CUSTOMER_AXIS = CUSTOMER_AXIS | {
    "customer_name",
    "client_phone",
    "client_name",
    "client_document",
    "client_email",
    "phone",
    "email",
    "document",
    "wa_id",
    "contact_id",
    "conversation_id",
}

_INJECTED = (
    "Lo pone el servidor: ``_dispatch_tool`` sobrescribe el valor que escriba el "
    "modelo con la conversación del turno (test_the_runtime_overwrites_…), y sin "
    "él la validación de la entrada falla, porque es obligatorio."
)
_RESERVAS = (
    "Opcional; ``_turn`` descarta una conversación que no es del cliente final del "
    "turno y usa la suya (test_reservas_ignores_a_conversation_of_another_customer)."
)
_OPERATOR = (
    "Herramienta de operador: solo la ponen en su lista semillas ``admin_only``, que "
    "solo contestan al personal del negocio "
    "(test_operator_tools_are_only_seeded_on_admin_only_agents). OJO: la consola "
    "(``PUT /console/clients/{ref}/tools``) y el admin dejan ponerla en la lista de "
    "cualquier agente, también de uno que contesta a todos; ese camino no lo cubre "
    "esta razón (informe A3, defecto abierto)."
)

OPERATOR_TOOLS = frozenset(
    {
        "billing.create_account",
        "billing.find_client",
        "billing.get_debtor_by_phone",
        "billing.update_account",
        "woocommerce.create_order",
        "woocommerce.get_customer",
        "woocommerce.list_customers",
    }
)

LEGIT_CUSTOMER_ARGS: dict[tuple[str, str], str] = {
    **{
        (tool, "conversation_id"): _INJECTED
        for tool in (
            "escalate.escalate_to_human",
            "notification.schedule_reminder",
            "notification.send_audio",
            "notification.send_document",
            "notification.send_image",
            "notification.send_location",
            "notification.send_reaction",
            "notification.send_template",
            "notification.send_text",
            "notification.send_video",
            "operator.consult_owner",
            "payments.request_review",
            "response.send_interactive",
        )
    },
    ("reservas.create", "conversation_id"): _RESERVAS,
    ("reservas.answer_offer", "conversation_id"): _RESERVAS,
    ("payments.request_review", "customer_name"): (
        "El nombre que el cliente final da para el resumen del pedido que ven los "
        "revisores del negocio: se escribe, no busca a nadie."
    ),
    **{
        pair: _OPERATOR
        for pair in (
            ("billing.create_account", "client_document"),
            ("billing.create_account", "client_name"),
            ("billing.create_account", "client_phone"),
            ("billing.find_client", "document"),
            ("billing.find_client", "phone"),
            ("billing.get_debtor_by_phone", "phone"),
            ("billing.update_account", "client_document"),
            ("billing.update_account", "client_name"),
            ("billing.update_account", "client_phone"),
            ("woocommerce.create_order", "customer_id"),
            ("woocommerce.get_customer", "email"),
            ("woocommerce.list_customers", "email"),
        )
    },
}

#: Entradas al escribirse (2026-10-26). No sube: una herramienta nueva —las de
#: la 047 incluidas— resuelve al cliente final en el servidor.
INVENTORY_CEILING = 28


def customer_args(definitions: list[Any]) -> set[tuple[str, str]]:
    return {
        (d.name, arg)
        for d in definitions
        for arg in ((d.parameters or {}).get("properties") or {})
        if arg in END_CUSTOMER_AXIS
    }


def test_no_tool_takes_an_end_customer_but_the_inventoried() -> None:
    registry = build_default_registry()
    found = customer_args(registry.get_tool_definitions(registry.names()))
    assert ("woocommerce.get_customer", "email") in found, "el barrido no ve argumentos"
    new = sorted(found - LEGIT_CUSTOMER_ARGS.keys())
    assert not new, (
        f"herramientas que dejan al modelo nombrar a un cliente final: {new}. "
        "El cliente del turno lo resuelve el servidor (garantía 8)."
    )
    stale = sorted(LEGIT_CUSTOMER_ARGS.keys() - found)
    assert not stale, f"entradas que ya no hacen falta: {stale}. Quítalas y baja el techo."
    assert len(LEGIT_CUSTOMER_ARGS) <= INVENTORY_CEILING


def test_operator_tools_are_only_seeded_on_admin_only_agents() -> None:
    offenders = []
    for seed in sorted(SEEDS.glob("*.yaml")):
        data = yaml.safe_load(seed.read_text()) or {}
        tools = data.get("tools") or {}
        listed = {*(tools.get("required") or []), *(tools.get("optional") or [])}
        access = (data.get("policies") or {}).get("admin_access") or {}
        if listed & OPERATOR_TOOLS and not access.get("admin_only"):
            offenders.append((seed.stem, sorted(listed & OPERATOR_TOOLS)))
    assert not offenders, (
        f"semillas que contestan a todos con herramientas de operador: {offenders}"
    )
    # Control: la que sí las lleva es admin_only.
    cobranza = yaml.safe_load((SEEDS / "cobranza_v1.yaml").read_text())
    assert set(cobranza["tools"]["required"]) & OPERATOR_TOOLS
    assert cobranza["policies"]["admin_access"]["admin_only"] is True


class _Recorder:
    """Un registro que solo apunta qué argumentos le llegan."""

    def __init__(self) -> None:
        self.args: list[dict[str, Any]] = []

    async def dispatch(self, name: str, args: dict[str, Any], *, whitelist: Any) -> dict:
        self.args.append(args)
        return {"status": "ok", "tool": name, "result": {}}


@pytest.mark.parametrize(
    "tool", sorted({t for t, a in LEGIT_CUSTOMER_ARGS if a == "conversation_id"})
)
async def test_the_runtime_overwrites_the_conversation_the_model_names(tool: str) -> None:
    turn, foreign = str(uuid.uuid4()), str(uuid.uuid4())
    recorder = _Recorder()
    await _dispatch_tool(
        recorder,  # type: ignore[arg-type]
        ToolCall(id="c1", name=tool, arguments={"conversation_id": foreign}),
        (tool,),
        "info",
        conversation_id=turn,
    )
    assert recorder.args == [{"conversation_id": turn}], "el modelo eligió la conversación"


async def test_reservas_ignores_a_conversation_of_another_customer(db_session, tenants_ab) -> None:
    from nexus_mcp.servers.reservas.tools import _turn

    a = tenants_ab["a"]
    await seed_active_agent_config(db_session, tenant_id=a, system_prompt="a", tools=[])
    channel = await seed_channel(db_session, tenant_id=a, provider_identifier="iso51")
    convs: dict[str, uuid.UUID] = {}
    customers: dict[str, uuid.UUID] = {}
    for key, phone in (("me", "+34600000101"), ("other", "+34600000102")):
        customer = Customer(tenant_id=a, identifier=phone, preferences={})
        db_session.add(customer)
        await db_session.commit()
        conv = Conversation(
            tenant_id=a,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        db_session.add(conv)
        await db_session.commit()
        convs[key], customers[key] = conv.id, customer.id

    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        conversation, _agent = await _turn(session, customers["me"], convs["other"])
    assert conversation == convs["me"], "reservas usó la conversación de otro cliente final"
