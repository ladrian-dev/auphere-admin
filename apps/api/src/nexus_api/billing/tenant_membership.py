"""Spec 077 · la membresía de un cliente cobrada por Stripe.

Todo lo que habla con el proveedor para la membresía de un cliente vive aquí,
dentro de la frontera (``tests/unit/test_billing_boundary.py``). Lo usa
``services/service_memberships``; la puerta de envío no lo toca nunca.

Reglas propias:

* **El cliente de Stripe es del cliente, nunca de su partner.** Se crea uno por
  tenant con su ``tenant_id`` en la metadata y una clave de idempotencia por
  ``tenant_id``: repetirlo no crea otro.
* **Sin ``client_reference_id``.** El webhook lo lee como ``partner_id``
  (``billing/events.partner_id_from``): un ``tenant_id`` ahí acabaría guardado
  como partner. La sesión y la suscripción llevan ``kind=tenant_membership`` y
  ``tenant_id`` en su metadata, y los avisos se resuelven desde ahí.
* **Precio en línea**, mensual y en USD: cada cliente tiene su importe y no
  hace falta un catálogo (``membership_tiers`` solo admite cuatro niveles).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import structlog

from nexus_api.billing.provider import field, get_client, idempotency_key

log = structlog.get_logger(__name__)

#: La marca que distingue nuestros objetos de Stripe de los de los partners.
KIND_TENANT_MEMBERSHIP = "tenant_membership"


@dataclass(frozen=True)
class OpenedCheckout:
    url: str
    session_id: str
    expires_at: datetime | None


def _ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def ensure_tenant_customer(*, tenant_id: uuid.UUID, name: str, email: str | None) -> str:
    """El cliente de Stripe del tenant. Idempotente por ``tenant_id``."""
    client = get_client()
    params: dict[str, Any] = {
        "name": name,
        "metadata": {"kind": KIND_TENANT_MEMBERSHIP, "tenant_id": str(tenant_id)},
    }
    if email:
        params["email"] = email
    customer = client.customers.create(
        cast(Any, params),
        options={"idempotency_key": idempotency_key("tenant_customer", tenant_id)},
    )
    return str(field(customer, "id"))


def open_tenant_membership_session(
    *,
    tenant_id: uuid.UUID,
    customer_id: str,
    amount_cents: int,
    product_name: str,
    success_url: str,
    cancel_url: str,
    stamp: str,
) -> OpenedCheckout:
    """Una sesión de Checkout de suscripción mensual por ``amount_cents`` USD.

    ``stamp`` distingue cada enlace: sin él, pedir uno nuevo reutilizaría la
    clave y Stripe devolvería la sesión anterior (quizá ya caducada).
    """
    client = get_client()
    metadata = {"kind": KIND_TENANT_MEMBERSHIP, "tenant_id": str(tenant_id)}
    params: dict[str, Any] = {
        "mode": "subscription",
        "customer": customer_id,
        "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "recurring": {"interval": "month"},
                    "product_data": {"name": product_name},
                },
                "quantity": 1,
            }
        ],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        # Renewal notices are not born from the session: the subscription
        # carries the same mark so they find their way home.
        "subscription_data": {"metadata": metadata},
    }
    session = client.checkout.sessions.create(
        cast(Any, params),
        options={
            "idempotency_key": idempotency_key(
                "tenant_membership", tenant_id, str(amount_cents), stamp
            )
        },
    )
    log.info("billing.tenant_membership_checkout_opened", tenant_id=str(tenant_id))
    return OpenedCheckout(
        url=str(field(session, "url")),
        session_id=str(field(session, "id")),
        expires_at=_ts(field(session, "expires_at")),
    )


def expire_checkout_session(session_id: str) -> str | None:
    """Caduca un enlace que sigue abierto, para que no se paguen dos.

    Devuelve la suscripción que el enlace ya pagó, si se pagó (el aviso puede
    no haber llegado): quien llama decide qué hacer con ella."""
    client = get_client()
    session = client.checkout.sessions.retrieve(session_id)
    state = str(field(session, "status") or "")
    if state == "open":
        client.checkout.sessions.expire(session_id)
        return None
    if state == "complete":
        found = field(session, "subscription")
        return str(field(found, "id") or found or "") or None
    return None


def retrieve_checkout_session(session_id: str) -> Any:
    return get_client().checkout.sessions.retrieve(session_id)


def retrieve_subscription(subscription_id: str) -> Any:
    return get_client().subscriptions.retrieve(subscription_id)


def cancel_subscription(subscription_id: str) -> Any:
    return get_client().subscriptions.cancel(subscription_id)


def list_subscription_invoices(subscription_id: str, *, limit: int = 24) -> list[Any]:
    listing = get_client().invoices.list(
        cast(Any, {"subscription": subscription_id, "limit": limit})
    )
    return list(field(listing, "data") or [])


def open_invoice_url(subscription_id: str) -> str | None:
    """The page where the client pays the subscription's unpaid invoice."""
    listing = get_client().invoices.list(
        cast(Any, {"subscription": subscription_id, "status": "open", "limit": 1})
    )
    data = list(field(listing, "data") or [])
    return str(field(data[0], "hosted_invoice_url") or "") or None if data else None


def is_ours(obj: Any) -> bool:
    """¿Es un objeto de la membresía de un cliente (y no de un partner)?"""
    return str(field(field(obj, "metadata"), "kind") or "") == KIND_TENANT_MEMBERSHIP


def tenant_of(obj: Any) -> uuid.UUID | None:
    raw = str(field(field(obj, "metadata"), "tenant_id") or "")
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


def subscription_period(sub: Any) -> tuple[datetime | None, datetime | None]:
    """El periodo en curso. Las versiones nuevas de la API lo dejan en el
    elemento de la suscripción; las viejas, en la suscripción."""
    items = field(field(sub, "items"), "data") or []
    first = items[0] if items else None
    start = field(first, "current_period_start") or field(sub, "current_period_start")
    end = field(first, "current_period_end") or field(sub, "current_period_end")
    return _ts(start), _ts(end)


def subscription_of_invoice(invoice: Any) -> str | None:
    """La suscripción de una factura: el campo de siempre o, en versiones
    nuevas, ``parent.subscription_details.subscription``."""
    direct = field(invoice, "subscription")
    if direct:
        return str(field(direct, "id") or direct)
    nested = field(field(field(invoice, "parent"), "subscription_details"), "subscription")
    if nested:
        return str(field(nested, "id") or nested)
    return None


def invoice_row(invoice: Any) -> dict[str, Any]:
    """Lo que el panel enseña de una factura: periodo, importe, estado y enlace."""
    status = str(field(invoice, "status") or "")
    lines = field(field(invoice, "lines"), "data") or []
    period = field(lines[0], "period") if lines else None
    paid = status == "paid"
    failed = status == "open" and int(field(invoice, "attempt_count") or 0) > 0
    return {
        "period_start": _ts(field(period, "start") or field(invoice, "period_start")),
        "period_end": _ts(field(period, "end") or field(invoice, "period_end")),
        "amount_cents": int(
            field(invoice, "amount_paid") if paid else field(invoice, "amount_due") or 0
        ),
        "status": "paid" if paid else "failed" if failed else status or "open",
        "url": field(invoice, "hosted_invoice_url"),
    }
