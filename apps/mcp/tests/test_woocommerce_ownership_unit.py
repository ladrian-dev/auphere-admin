"""La tienda también tiene dos clientes — garantía 8 en `woocommerce.*`.

El arreglo de septiembre cerró el eje de cliente en reservas, que es donde se
vio el defecto. El barrido de `test_37_customer_axis_contract.py` encontró que
la tienda tenía la misma forma y nadie había mirado: `list_orders` aceptaba un
identificador de cliente como argumento, y `get_order` devolvía la dirección de
envío de cualquier pedido por su número.

Aquí se prueban las dos mitades:

1. La regla de pertenencia, que es pura y se lee sola.
2. Las dos herramientas, que la aplican cuando hay alguien al otro lado y no la
   aplican cuando no lo hay — un turno de operador mirando los pedidos de su
   propia tienda no es una fuga.

El caso que más importa es el tercer bloque: el pedido que existe y no es suyo
se responde **igual** que el que no existe.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_api.core.tenant_context import tenant_context
from test_woocommerce_tools_unit import FakeWooClient

from nexus_mcp.http import PaginationMeta
from nexus_mcp.servers.woocommerce import tools as woo_tools
from nexus_mcp.servers.woocommerce._ownership import (
    email_key,
    order_belongs_to,
    own_orders,
    phone_key,
)
from nexus_mcp.servers.woocommerce.errors import WooCommerceNotFound
from nexus_mcp.servers.woocommerce.tools import GetOrder, ListOrders, set_test_client

pytestmark = [pytest.mark.unit]

_TENANT = uuid.uuid4()

MINE = "56912345678"
THEIRS = "56987654321"


def _order(oid: int, *, phone: str | None = None, email: str | None = None) -> dict[str, Any]:
    billing: dict[str, Any] = {}
    if phone is not None:
        billing["phone"] = phone
    if email is not None:
        billing["email"] = email
    return {
        "id": oid,
        "number": str(oid),
        "status": "processing",
        "currency": "CLP",
        "total": "19990",
        "billing": billing,
        "shipping": {"address_1": "Avenida Siempre Viva 742"},
    }


@pytest.fixture
def fake_client():
    c = FakeWooClient()
    set_test_client(c)
    yield c
    set_test_client(None)


@pytest.fixture
def tenant_ctx():
    with tenant_context(_TENANT):
        yield _TENANT


@pytest.fixture
def as_person(monkeypatch):
    """Quien escribe, sin pasar por la base de datos.

    La consulta que traduce «el cliente del turno» a un teléfono está probada
    donde vive; lo que se prueba aquí es qué hace la herramienta con el
    resultado. Separarlo deja estos tests sin base de datos, como los demás del
    servidor.
    """

    def _set(phone: str | None, email: str | None = None):
        async def _person() -> tuple[str | None, str | None] | None:
            return (phone, email)

        monkeypatch.setattr(woo_tools, "_person_of_the_turn", _person)

    return _set


# ── la regla, a solas ────────────────────────────────────────────────────


def test_a_phone_is_recognised_however_it_was_typed():
    # El mismo abonado, escrito por dos personas distintas.
    assert phone_key("+56 9 1234 5678") == phone_key("56912345678")


def test_something_too_short_is_not_a_phone():
    # Cuatro dígitos coinciden por casualidad, y una casualidad aquí entrega
    # la dirección de alguien.
    assert phone_key("1234") is None
    assert phone_key("") is None
    assert phone_key(None) is None


def test_an_email_is_compared_without_case_or_spaces():
    assert email_key("  Ana@Tienda.CL ") == "ana@tienda.cl"
    assert email_key("no-es-un-correo") is None


def test_an_order_with_no_contact_details_belongs_to_nobody():
    """Un pedido de invitado sin teléfono ni correo no se atribuye.

    Es la decisión que más se nota: la persona que sí hizo ese pedido no lo va a
    ver. La alternativa —atribuirlo a quien pregunte— es enseñar una dirección
    de envío a un desconocido.
    """
    assert order_belongs_to(_order(1), phone=MINE, email=None) is False


def test_we_do_not_guess_when_we_do_not_know_who_is_writing():
    assert order_belongs_to(_order(1, phone=MINE), phone=None, email=None) is False


def test_the_owner_is_recognised_by_phone_or_by_email():
    assert order_belongs_to(_order(1, phone=MINE), phone=MINE, email=None) is True
    assert order_belongs_to(_order(1, email="ana@x.cl"), phone=None, email="ANA@x.cl") is True


def test_own_orders_keeps_only_mine():
    lote = [_order(1, phone=MINE), _order(2, phone=THEIRS), _order(3)]
    assert [o["id"] for o in own_orders(lote, phone=MINE, email=None)] == [1]


# ── las herramientas, con alguien al otro lado ───────────────────────────


async def test_listing_orders_shows_only_the_ones_of_whoever_is_writing(
    fake_client, tenant_ctx, as_person
):
    as_person(MINE)
    fake_client.next_list = (
        [_order(1, phone=MINE), _order(2, phone=THEIRS)],
        PaginationMeta(page=1, per_page=20, total_count=2, total_pages=1, has_more=False),
    )

    out = await ListOrders().invoke({})

    assert [o["id"] for o in out["result"]["items"]] == [1]


async def test_the_shop_wide_totals_are_not_reported_to_a_customer(
    fake_client, tenant_ctx, as_person
):
    """Cuántos pedidos tiene la tienda también es del negocio.

    Devolver `total_count=2` a quien solo puede ver uno es la misma fuga un
    nivel más arriba —la cardinalidad del negocio— y además le hace pedir
    páginas que no son suyas. Un total propio no lo sabemos: solo vemos esta
    página. Así que se dice que no se sabe, que es lo único cierto.
    """
    as_person(MINE)
    fake_client.next_list = (
        [_order(1, phone=MINE), _order(2, phone=THEIRS)],
        PaginationMeta(page=1, per_page=20, total_count=2, total_pages=1, has_more=False),
    )

    out = await ListOrders().invoke({})

    assert out["result"]["total_count"] is None
    assert out["result"]["total_pages"] is None


async def test_fetching_someone_elses_order_answers_as_if_it_did_not_exist(
    fake_client, tenant_ctx, as_person
):
    """El corazón del asunto.

    Distinguir «ese pedido no existe» de «ese pedido no es tuyo» convierte
    contar hasta mil en un censo de la tienda, con dirección de envío incluida.
    Por eso las dos respuestas tienen que ser la misma, incluido el texto.
    """
    as_person(MINE)
    fake_client.next_get = _order(555, phone=THEIRS)

    with pytest.raises(WooCommerceNotFound) as ajeno:
        await GetOrder().invoke({"id": 555})

    fake_client.next_get = None
    fake_client.raise_on_call = WooCommerceNotFound("no order with id=555", status_code=404)
    with pytest.raises(WooCommerceNotFound) as inexistente:
        await GetOrder().invoke({"id": 555})

    assert str(ajeno.value) == str(inexistente.value)


async def test_fetching_my_own_order_still_works(fake_client, tenant_ctx, as_person):
    # El arreglo no vale nada si la postventa deja de funcionar para su dueño.
    as_person(MINE)
    fake_client.next_get = _order(555, phone=MINE)

    out = await GetOrder().invoke({"id": 555})

    assert out["result"]["order"]["id"] == 555


# ── las herramientas, sin nadie al otro lado ─────────────────────────────


async def test_without_a_resolved_customer_the_store_is_not_filtered(fake_client, tenant_ctx):
    """Un turno de operador mirando los pedidos de su propia tienda.

    Aquí la regla del eje de reservas —leer sin cliente devuelve vacío— sería
    la equivocada: `woocommerce.*` sí tiene uso de personal, y vaciarle la
    lista al dueño de la tienda no protege a nadie. Lo que aplica es el
    invariante, que solo habla de turnos **con** cliente resuelto.
    """
    fake_client.next_list = (
        [_order(1, phone=MINE), _order(2, phone=THEIRS)],
        PaginationMeta(page=1, per_page=20, total_count=2, total_pages=1, has_more=False),
    )

    out = await ListOrders().invoke({})

    assert [o["id"] for o in out["result"]["items"]] == [1, 2]
