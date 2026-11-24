"""Eventos de conversión para la API de conversiones de Meta — spec 076, requisitos 5 y 6.

Este módulo decide **qué** sale a Meta y lo deja en la cola
``ad_conversion_events`` dentro de la transacción de quien crea el resultado. El
despachador de ``egress`` (``nexus_worker.conversions``) lo envía después.

Reglas (research D7):

- solo resultados del agente en el chat: una reserva con ``origin = 'agent'``
  (``Purchase`` con su precio, o ``LeadSubmitted`` sin precio), un pedido de
  WooCommerce que crea el agente (``OrderCreated``) y la cancelación de una
  reserva cuyo evento existe (``OrderCanceled``, la cancele quien la cancele);
- el número de la conversación tiene la medición activa;
- el contacto no tiene una baja activa en ese número;
- atribución: el último clic con ``ctwa_clid`` del mismo contacto **y del mismo
  número** anterior al resultado; sin clic, el contacto tiene que tener teléfono;
- ``event_id`` estable (``"{source_kind}:{source_id}:{event_name}"``): un
  reintento del turno no duplica (``ON CONFLICT DO NOTHING``).

El teléfono **no se guarda** en la cola, ni cifrado: el despachador lo lee y lo
cifra al enviar (``phone_hash``). Ningún log lleva el clic ni el teléfono.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Final

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    AdConversionEvent,
    ChannelAdMeasurement,
    Conversation,
    Customer,
    CustomerAdReferral,
    Reservation,
    WhatsAppOptOut,
)
from nexus_api.services.business.services_catalog import exponent

log = structlog.get_logger(__name__)

PURCHASE: Final = "Purchase"
LEAD: Final = "LeadSubmitted"
ORDER_CREATED: Final = "OrderCreated"
ORDER_CANCELED: Final = "OrderCanceled"

#: Un teléfono, tal como puede venir: dígitos con ``+``, espacios, guiones,
#: puntos o paréntesis, y un ``tel:`` delante. Un BSUID (``ES.1000…``) no lo es.
_PHONE_SHAPE: Final = re.compile(r"^\s*(?:tel:)?\+?[\d\s().\-]+$", re.IGNORECASE)
#: E.164: como mucho 15 dígitos; menos de 7 no es un teléfono.
_MIN_DIGITS: Final = 7
_MAX_DIGITS: Final = 15


# ── reglas puras ────────────────────────────────────────────────────────────


def normalize_phone(raw: str | None) -> str | None:
    """Como dice Meta: solo dígitos, con código de país y sin ceros iniciales.

    ``None`` si no tiene forma de teléfono (un BSUID, un nombre de usuario)."""
    if not raw or not _PHONE_SHAPE.match(raw):
        return None
    digits = re.sub(r"\D", "", raw).lstrip("0")
    if not _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
        return None
    return digits


def phone_hash(raw: str | None) -> str | None:
    """El SHA-256 en hexadecimal del teléfono normalizado, o ``None``."""
    normalized = normalize_phone(raw)
    if normalized is None:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()


def booking_event(
    *, price_minor: int | None, currency: str | None
) -> tuple[str, int | None, str | None]:
    """``(event_name, value_minor, currency)`` de una reserva del agente.

    Con precio y moneda, ``Purchase`` (una reserva gratis es una compra de 0).
    Sin una de las dos, ``LeadSubmitted`` sin importe (decisión de Luis)."""
    if price_minor is not None and currency:
        return PURCHASE, price_minor, currency.upper()
    return LEAD, None, None


def event_id(source_kind: str, source_id: str, event_name: str) -> str:
    return f"{source_kind}:{source_id}:{event_name}"


def order_minor(total: str | None, currency: str) -> int | None:
    """El total de un pedido de la tienda (texto decimal) en unidades menores."""
    if total is None:
        return None
    try:
        amount = Decimal(str(total).strip())
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return int((amount * (10 ** exponent(currency))).to_integral_value())


def major_value(minor: int, currency: str) -> Decimal:
    """Lo que Meta espera en ``custom_data.value``: unidades mayores."""
    return Decimal(minor) / (Decimal(10) ** exponent(currency))


def customer_phone(customer: Customer) -> str | None:
    """El teléfono del contacto: ``phone`` (spec 050) o el ``identifier`` cuando
    es un teléfono. Un BSUID no lo es."""
    for raw in (customer.phone, customer.identifier):
        if normalize_phone(raw):
            return raw
    return None


# ── lo que decide si un resultado entra ────────────────────────────────────


async def active_measurement(
    session: AsyncSession, channel_id: uuid.UUID
) -> ChannelAdMeasurement | None:
    """La medición del número si está activa y tiene conjunto de datos de Meta."""
    row = (
        await session.execute(
            sa.select(ChannelAdMeasurement).where(ChannelAdMeasurement.channel_id == channel_id)
        )
    ).scalar_one_or_none()
    if row is None or not row.enabled or not row.meta_dataset_id:
        return None
    return row


async def opted_out(session: AsyncSession, *, channel_id: uuid.UUID, customer: Customer) -> bool:
    """Requisito 5.9: una baja activa del contacto **en este número**, sea cual sea
    su alcance. La tabla es por número y teléfono, y ``customer_id`` es opcional
    en ella: se mira por las dos cosas."""
    phones: set[str] = {p for p in (customer.phone, customer.identifier) if p}
    digits: set[str] = {d for d in (normalize_phone(p) for p in phones) if d}
    candidates = sorted(phones | digits | {f"+{d}" for d in digits})
    match = WhatsAppOptOut.customer_id == customer.id
    if candidates:
        match = sa.or_(match, WhatsAppOptOut.recipient_phone.in_(candidates))
    found = await session.scalar(
        sa.select(sa.literal(True))
        .where(
            WhatsAppOptOut.channel_id == channel_id,
            WhatsAppOptOut.opted_in_at.is_(None),
            match,
        )
        .limit(1)
    )
    return bool(found)


async def attributing_click(
    session: AsyncSession, *, customer_id: uuid.UUID, channel_id: uuid.UUID, at: datetime
) -> CustomerAdReferral | None:
    """El último clic con ``ctwa_clid`` del contacto **en este número** antes de
    ``at`` (research D7). Un clic en otro número es de otra cuenta de WhatsApp."""
    return (
        await session.execute(
            sa.select(CustomerAdReferral)
            .where(
                CustomerAdReferral.customer_id == customer_id,
                CustomerAdReferral.channel_id == channel_id,
                CustomerAdReferral.ctwa_clid.is_not(None),
                CustomerAdReferral.clicked_at <= at,
            )
            .order_by(CustomerAdReferral.clicked_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _insert(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    customer_id: uuid.UUID,
    referral_id: uuid.UUID | None,
    source_kind: str,
    source_id: str,
    event_name: str,
    event_time: datetime,
    value_minor: int | None,
    currency: str | None,
    cancels_event_id: uuid.UUID | None = None,
) -> bool:
    stmt = (
        insert(AdConversionEvent)
        .values(
            tenant_id=tenant_id,
            channel_id=channel_id,
            customer_id=customer_id,
            referral_id=referral_id,
            cancels_event_id=cancels_event_id,
            source_kind=source_kind,
            source_id=source_id,
            event_name=event_name,
            event_id=event_id(source_kind, source_id, event_name),
            event_time=event_time,
            value_minor=value_minor,
            currency=currency,
        )
        .on_conflict_do_nothing(constraint="uq_ad_conversion_events_event_id")
        .returning(AdConversionEvent.id)
    )
    inserted = (await session.execute(stmt)).scalar_one_or_none() is not None
    if inserted:
        log.info(
            "ad_conversion.enqueued",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            event_name=event_name,
            source_kind=source_kind,
            attributed=referral_id is not None,
        )
    return inserted


async def _eligible(
    session: AsyncSession,
    conversation_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    at: datetime,
) -> tuple[Conversation, Customer, CustomerAdReferral | None] | None:
    """La conversación, su contacto y el clic que atribuye, si el resultado entra.

    El contacto del resultado tiene que ser el de la conversación (garantía 8): un
    resultado nunca se atribuye con el clic o el teléfono de otra persona."""
    if conversation_id is None or customer_id is None:
        return None
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.customer_id != customer_id:
        return None
    if await active_measurement(session, conv.channel_id) is None:
        return None
    customer = await session.get(Customer, customer_id)
    if customer is None:
        return None
    if await opted_out(session, channel_id=conv.channel_id, customer=customer):
        return None
    click = await attributing_click(
        session, customer_id=customer.id, channel_id=conv.channel_id, at=at
    )
    if click is None and customer_phone(customer) is None:
        return None
    return conv, customer, click


# ── las tres entradas ───────────────────────────────────────────────────────


async def enqueue_for_booking(session: AsyncSession, reservation: Reservation) -> None:
    """Una reserva que crea el agente en el chat (requisitos 5.1 y 5.2).

    Una reserva de la consola, de la app, de la lista de espera o de una llegada
    sin reserva no entra (5.5): el discriminador es ``origin == 'agent'``."""
    if reservation.origin != "agent":
        return
    # ``created_at`` is a server default: after the flush it is expired, and
    # reading it would lazy-load under an async session. The booking is now.
    at = reservation.__dict__.get("created_at") or datetime.now(UTC)
    found = await _eligible(session, reservation.conversation_id, reservation.customer_id, at)
    if found is None:
        return
    conv, customer, click = found
    name, value, currency = booking_event(
        price_minor=reservation.price_minor, currency=reservation.currency
    )
    await _insert(
        session,
        tenant_id=reservation.tenant_id,
        channel_id=conv.channel_id,
        customer_id=customer.id,
        referral_id=click.id if click else None,
        source_kind="reservation",
        source_id=str(reservation.id),
        event_name=name,
        event_time=at,
        value_minor=value,
        currency=currency,
    )


async def enqueue_cancellation(session: AsyncSession, reservation: Reservation) -> None:
    """La cancelación de una reserva cuyo evento existe (requisito 5.3), la cancele
    quien la cancele. Lleva el mismo clic, el mismo importe y la misma moneda que
    el original, sin buscar un clic más nuevo, y el despachador la envía solo
    después de que el original haya salido."""
    original = (
        await session.execute(
            sa.select(AdConversionEvent).where(
                AdConversionEvent.source_kind == "reservation",
                AdConversionEvent.source_id == str(reservation.id),
                AdConversionEvent.event_name.in_((PURCHASE, LEAD)),
                AdConversionEvent.status.in_(("pending", "sent")),
            )
        )
    ).scalar_one_or_none()
    if original is None:
        return
    if await active_measurement(session, original.channel_id) is None:
        return
    await _insert(
        session,
        tenant_id=original.tenant_id,
        channel_id=original.channel_id,
        customer_id=original.customer_id,
        referral_id=original.referral_id,
        source_kind="reservation",
        source_id=str(reservation.id),
        event_name=ORDER_CANCELED,
        event_time=reservation.cancelled_at or datetime.now(UTC),
        value_minor=original.value_minor,
        currency=original.currency,
        cancels_event_id=original.id,
    )


async def enqueue_for_order(
    session: AsyncSession, *, order_id: str, total: str | None, currency: str | None
) -> None:
    """Un pedido o un enlace de pago que crea el agente en WooCommerce (5.4).

    La conversación y el contacto salen del turno (``conversation_context`` y
    ``customer_context``), nunca de un argumento: sin turno, no entra."""
    from nexus_api.core.tenant_context import (
        get_current_conversation,
        get_current_customer,
        get_current_tenant,
    )

    tenant_id = get_current_tenant()
    if tenant_id is None or not currency:
        return
    at = datetime.now(UTC)
    found = await _eligible(session, get_current_conversation(), get_current_customer(), at)
    if found is None:
        return
    conv, customer, click = found
    await _insert(
        session,
        tenant_id=tenant_id,
        channel_id=conv.channel_id,
        customer_id=customer.id,
        referral_id=click.id if click else None,
        source_kind="woo_order",
        source_id=str(order_id)[:64],
        event_name=ORDER_CREATED,
        event_time=at,
        value_minor=order_minor(total, currency),
        currency=currency.upper(),
    )


async def measure(session: AsyncSession, step: str, reservation: Reservation) -> None:
    """Llama a ``enqueue_for_booking`` o ``enqueue_cancellation`` dentro de un
    SAVEPOINT: medir nunca puede tumbar una reserva ni su cancelación."""
    fn = enqueue_for_booking if step == "created" else enqueue_cancellation
    try:
        async with session.begin_nested():
            await fn(session, reservation)
    except Exception as exc:
        log.warning(
            "ad_conversion.enqueue_failed",
            tenant_id=str(reservation.tenant_id),
            step=step,
            error=type(exc).__name__,
        )
