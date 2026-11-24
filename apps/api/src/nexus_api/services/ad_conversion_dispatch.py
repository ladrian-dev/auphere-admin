"""Reservar, construir y anotar los eventos que van a Meta — spec 076, requisito 6.

El patrón de los avisos push (``push_fanout``): el worker (``egress``) llama a
``claim`` en la transacción del tenant, envía **fuera** de cualquier transacción
y llama a ``settle`` en otra. Toda la decisión vive aquí, donde la barren las
suites de aislamiento.

- **Reserva** las filas ``pending`` que tocan, con ``SKIP LOCKED`` y un plazo
  (``lease_until``), y suma un intento.
- **No sale**:
  - un evento de más de 6 d 23 h (Meta rechaza el lote entero), que pasa a
    ``failed`` con ``too_old``;
  - nada de un número con la medición apagada ni de un contacto con baja, que
    pasan a ``discarded``;
  - una cancelación cuyo original no ha salido, que espera sin gastar intentos;
    si el original quedó ``failed`` o ``discarded``, se descarta.
- **El cuerpo** lleva el clic (``ctwa_clid``) si sigue guardado; si no, el
  teléfono cifrado con SHA-256 y el número.
- **El conjunto de datos y el token** salen de la medición y las credenciales
  **del tenant de la sesión**, nunca de la fila del evento (garantía 1).

Ningún log lleva el clic, el teléfono ni su hash (requisito 6.7).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final, Literal

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import (
    AdConversionEvent,
    Channel,
    ChannelAdMeasurement,
    Customer,
    CustomerAdReferral,
)
from nexus_api.services.ad_conversions import (
    active_measurement,
    customer_phone,
    major_value,
    opted_out,
    phone_hash,
)
from nexus_api.services.ad_measurement import REAUTHORIZE, channel_credentials

log = structlog.get_logger(__name__)

BATCH: Final = 50
LEASE: Final = timedelta(minutes=2)
MAX_ATTEMPTS: Final = 6
BACKOFF_BASE: Final = timedelta(minutes=1)
#: Meta rechaza el lote entero si un evento tiene más de 7 días; un margen.
MAX_AGE: Final = timedelta(days=7) - timedelta(hours=1)
PARTNER_AGENT: Final = "auphere"


@dataclass(frozen=True)
class Outgoing:
    """Un evento reservado, listo para enviar. ``access_token`` nunca se registra."""

    row_id: uuid.UUID
    tenant_id: uuid.UUID
    channel_id: uuid.UUID
    event_name: str
    dataset_id: str
    access_token: str = field(repr=False)
    event: dict[str, Any] = field(repr=False)
    lease_until: datetime
    test_event_code: str | None = None


@dataclass(frozen=True)
class Outcome:
    """Lo que pasó al enviar: ``sent``, ``retry`` (pasajero) o ``failed``."""

    kind: Literal["sent", "retry", "failed"]
    code: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _number(v: Decimal) -> int | float:
    return int(v) if v == v.to_integral_value() else float(v)


def _log(event: str, ev: AdConversionEvent, **extra: Any) -> None:
    log.info(
        event,
        tenant_id=str(ev.tenant_id),
        channel_id=str(ev.channel_id),
        event_name=ev.event_name,
        attempts=ev.attempts,
        **extra,
    )


async def _mark_number(
    session: AsyncSession, channel_id: uuid.UUID, code: str | None, now: datetime
) -> None:
    """El último error del número para su estado (4.6); ``None`` lo limpia."""
    await session.execute(
        sa.update(ChannelAdMeasurement)
        .where(ChannelAdMeasurement.channel_id == channel_id)
        .values(last_error_code=code, last_error_at=now if code else None, updated_at=sa.func.now())
    )


def _fail(ev: AdConversionEvent, code: str) -> None:
    ev.status = "failed"
    ev.last_error_code = code
    ev.lease_until = None
    _log("ad_conversion.failed", ev, code=code)


def _discard(ev: AdConversionEvent, reason: str) -> None:
    ev.status = "discarded"
    ev.lease_until = None
    _log("ad_conversion.discarded", ev, reason=reason)


async def _user_data(
    session: AsyncSession,
    ev: AdConversionEvent,
    customer: Customer,
    channel: Channel,
    waba_id: str,
    pnid: str,
) -> dict[str, Any] | None:
    if ev.referral_id is not None:
        ref = await session.get(CustomerAdReferral, ev.referral_id)
        if ref is not None and ref.ctwa_clid and ref.customer_id == ev.customer_id:
            return {"whatsapp_business_account_id": waba_id, "ctwa_clid": ref.ctwa_clid}
    hashed = phone_hash(customer_phone(customer))
    if hashed is None:
        return None
    return {
        "whatsapp_business_account_id": waba_id,
        "whatsapp_phone_number_id": pnid,
        "ph": [hashed],
    }


async def claim(session: AsyncSession, *, now: datetime | None = None) -> list[Outgoing]:
    """Reserva lo que toca de este tenant y devuelve lo que hay que enviar."""
    ts = now or _now()
    rows = (
        (
            await session.execute(
                sa.select(AdConversionEvent)
                .where(
                    AdConversionEvent.status == "pending",
                    AdConversionEvent.next_attempt_at <= ts,
                    sa.or_(
                        AdConversionEvent.lease_until.is_(None), AdConversionEvent.lease_until < ts
                    ),
                )
                .order_by(AdConversionEvent.event_time, AdConversionEvent.created_at)
                .limit(BATCH)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    test_code = get_settings().meta_capi_test_event_code
    out: list[Outgoing] = []
    for ev in rows:
        if ev.event_time < ts - MAX_AGE:
            _fail(ev, "too_old")
            await _mark_number(session, ev.channel_id, "too_old", ts)
            continue
        measurement = await active_measurement(session, ev.channel_id)
        if measurement is None or not measurement.meta_dataset_id:
            _discard(ev, "measurement_off")
            continue
        customer = await session.get(Customer, ev.customer_id)
        if customer is None or await opted_out(
            session, channel_id=ev.channel_id, customer=customer
        ):
            _discard(ev, "opted_out")
            continue
        if ev.cancels_event_id is not None:
            original = await session.get(AdConversionEvent, ev.cancels_event_id)
            if original is None or original.status in ("failed", "discarded"):
                _discard(ev, "cancelled_before_send")
                continue
            if original.status != "sent":
                continue  # espera, sin gastar intentos
        channel = await session.get(Channel, ev.channel_id)
        creds = await channel_credentials(session, channel) if channel is not None else None
        if channel is None or creds is None:
            _fail(ev, REAUTHORIZE)
            await _mark_number(session, ev.channel_id, REAUTHORIZE, ts)
            continue
        cfg = channel.config or {}
        waba_id = str(creds.waba_id or cfg.get("waba_id") or "")
        pnid = str(cfg.get("phone_number_id") or creds.phone_number_id or "")
        user_data = await _user_data(session, ev, customer, channel, waba_id, pnid)
        if user_data is None or not waba_id:
            # Requisito 6.3: lo que no es pasajero se ve en el estado del número.
            _fail(ev, "no_identity")
            await _mark_number(session, ev.channel_id, "no_identity", ts)
            continue
        event: dict[str, Any] = {
            "event_name": ev.event_name,
            "event_time": int(ev.event_time.timestamp()),
            "event_id": ev.event_id,
            "action_source": "business_messaging",
            "messaging_channel": "whatsapp",
            "user_data": user_data,
        }
        if ev.value_minor is not None and ev.currency:
            event["custom_data"] = {
                "currency": ev.currency,
                "value": _number(major_value(ev.value_minor, ev.currency)),
            }
        ev.lease_until = ts + LEASE
        ev.attempts += 1
        out.append(
            Outgoing(
                row_id=ev.id,
                tenant_id=ev.tenant_id,
                channel_id=ev.channel_id,
                event_name=ev.event_name,
                dataset_id=measurement.meta_dataset_id,
                access_token=creds.bisuat,
                event=event,
                lease_until=ev.lease_until,
                test_event_code=test_code,
            )
        )
    await session.flush()
    return out


async def settle(
    session: AsyncSession, results: list[tuple[Outgoing, Outcome]], *, now: datetime | None = None
) -> None:
    """Anota lo que pasó. Solo toca filas que siguen reservadas por esta pasada."""
    ts = now or _now()
    for out, res in results:
        ev = await session.get(AdConversionEvent, out.row_id, with_for_update=True)
        if ev is None or ev.status != "pending" or ev.lease_until != out.lease_until:
            continue
        if res.kind == "sent":
            ev.status = "sent"
            ev.sent_at = ts
            ev.lease_until = None
            ev.last_error_code = None
            await _mark_number(session, ev.channel_id, None, ts)
            _log("ad_conversion.sent", ev)
        elif res.kind == "retry" and ev.attempts < MAX_ATTEMPTS:
            ev.lease_until = None
            ev.last_error_code = res.code
            ev.next_attempt_at = ts + BACKOFF_BASE * (2 ** max(ev.attempts - 1, 0))
            _log("ad_conversion.retry", ev, code=res.code)
        else:
            code = res.code or "meta_error"
            _fail(ev, code)
            await _mark_number(session, ev.channel_id, code, ts)
    await session.flush()


async def tenants_with_pending(
    identity: AsyncSession, *, now: datetime | None = None
) -> list[uuid.UUID]:
    """El recorrido del despachador: tenants con eventos que ya tocan. Con la
    sesión de identidad, como ``push_fanout.tenants_with_pending``; lo demás se
    hace después tenant a tenant."""
    ts = now or _now()
    rows = await identity.execute(
        sa.select(AdConversionEvent.tenant_id)
        .where(AdConversionEvent.status == "pending", AdConversionEvent.next_attempt_at <= ts)
        .distinct()
    )
    return [row[0] for row in rows]
