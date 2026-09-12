"""Spec 005 · qué evento va a qué manejador, y cuál NO está suscrito.

El test que más avería previene de esta spec es el último, y no prueba que
algo funcione: prueba que **algo no está**.
"""

from __future__ import annotations

import pytest

from nexus_api.billing.events import (
    HANDLED_EVENTS,
    checkout_session_id_from,
    object_id_from,
    partner_id_from,
)

pytestmark = [pytest.mark.asyncio]


async def test_invoice_created_is_not_subscribed() -> None:
    """La mina de las 72 horas.

    Verificado el 2026-09-12: si el endpoint no responde correctamente a
    ``invoice.created``, Stripe retrasa la finalización de **todas** las
    facturas con cobro automático hasta 72 horas. No las de ese partner:
    todas. Y sin síntoma: el sistema no se cae, simplemente deja de facturar.

    No lo necesitamos — el dinero llega con ``invoice.paid`` — y a un evento
    al que no se está suscrito no se le debe respuesta.
    """
    assert "invoice.created" not in HANDLED_EVENTS


async def test_the_quiet_failure_is_subscribed() -> None:
    """Y su contraria: ``finalization_failed`` **sí** tiene que estar.

    Una factura que no finaliza deja la suscripción activa —el partner
    trabaja— y no cobra nada. Sin manejador, no hay ningún síntoma.
    """
    assert "invoice.finalization_failed" in HANDLED_EVENTS


async def test_the_six_events_we_act_on() -> None:
    for event in (
        "invoice.paid",
        "invoice.payment_failed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ):
        assert event in HANDLED_EVENTS, event


async def test_the_partner_comes_from_client_reference_id() -> None:
    pid = "7f3a1c62-0000-4000-8000-000000000001"
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_1", "client_reference_id": pid}},
    }
    assert str(partner_id_from(event)) == pid


async def test_the_partner_also_comes_from_subscription_metadata() -> None:
    """Un aviso de renovación no nace de una sesión de Checkout."""
    pid = "7f3a1c62-0000-4000-8000-000000000002"
    event = {
        "id": "evt_2",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_1", "metadata": {"partner_id": pid}}},
    }
    assert str(partner_id_from(event)) == pid


async def test_a_broken_reference_does_not_explode() -> None:
    event = {
        "id": "evt_3",
        "type": "invoice.paid",
        "data": {"object": {"id": "in_1", "client_reference_id": "no-soy-un-uuid"}},
    }
    assert partner_id_from(event) is None


async def test_the_object_id_travels_so_the_worker_can_refetch() -> None:
    event = {"id": "evt_4", "type": "invoice.paid", "data": {"object": {"id": "in_9"}}}
    assert object_id_from(event) == "in_9"


async def test_the_checkout_anchor_only_applies_to_checkout_events() -> None:
    invoice = {"id": "e", "type": "invoice.paid", "data": {"object": {"id": "in_1"}}}
    checkout = {"id": "e", "type": "checkout.session.completed", "data": {"object": {"id": "cs_1"}}}
    assert checkout_session_id_from(invoice) is None
    assert checkout_session_id_from(checkout) == "cs_1"
