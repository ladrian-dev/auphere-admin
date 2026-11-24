"""Activar la medición de resultados de anuncios de un número — spec 076, requisito 4.

- **Quién la ve** (research D10): un número de WhatsApp por Meta, sin
  desconectar y fuera de coexistencia (hasta que la prueba de staging diga que
  funciona), de un tenant de ``ad_measurement_tenants`` o con la apertura general
  puesta. Si no, el bloque no existe (constitución §V).
- **Activar:** confirmación explícita (4.8), el permiso
  ``whatsapp_business_manage_events`` en el token del número (si falta, 409
  ``reauthorize``), y crear u obtener el conjunto de datos de la cuenta de
  WhatsApp (``POST /{waba_id}/dataset``). Si Meta falla, no se activa nada.
- **Desactivar:** deja de enviar desde ese momento; lo pendiente se descarta.

El conjunto de datos y el token salen de las credenciales del número, bajo el
tenant de la sesión: nunca de la petición (garantía 1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal, Protocol, cast

import sqlalchemy as sa
import structlog
from nexus_channels.whatsapp_meta.credentials import (
    ChannelCredentialsRepository,
    MetaCredentials,
    MetaCredentialsRepository,
)
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import Settings, get_settings
from nexus_api.db.models import (
    AdConversionEvent,
    Channel,
    ChannelAdMeasurement,
    ChannelStatus,
    ChannelType,
)

log = structlog.get_logger(__name__)

#: El permiso que hace falta en el token del número.
EVENTS_SCOPE: Final = "whatsapp_business_manage_events"
REAUTHORIZE: Final = "reauthorize"

State = Literal["on", "off", "reauthorize"]


class MeasurementError(Exception):
    """Lo que la ruta devuelve como ``{"code": …}`` con su estado HTTP."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class _MetaPort(Protocol):
    async def token_scopes(self, *, input_token: str, app_id: str) -> set[str]: ...
    async def ensure_dataset(self, *, waba_id: str, access_token: str) -> str: ...
    async def close(self) -> None: ...


def meta_client() -> _MetaPort:
    """El cliente de Graph. Aislado para que las pruebas lo cambien por un doble."""
    from nexus_api.services.meta_signup_service import build_meta_client

    return cast(_MetaPort, build_meta_client())


# ── disponibilidad ──────────────────────────────────────────────────────────


def is_coexistence(channel: Channel) -> bool:
    return bool(channel.coexistence) or (channel.config or {}).get("mode") == "coexistence"


def available(channel: Channel, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if channel.type is not ChannelType.WHATSAPP or channel.provider != "meta":
        return False
    if channel.status is ChannelStatus.DISCONNECTED:
        return False
    if is_coexistence(channel):
        return False
    return s.ad_measurement_general_availability or channel.tenant_id in s.ad_measurement_tenant_ids


def reconnect_config_id(channel: Channel, settings: Settings | None = None) -> str:
    """La configuración del registro insertado para volver a autorizar el número:
    la de pruebas de su modo si está puesta (solo staging), si no la normal."""
    s = settings or get_settings()
    if is_coexistence(channel):
        return s.meta_config_id_wa_events_test_coexistence or s.meta_config_id_wa_coexistence
    return s.meta_config_id_wa_events_test_cloud_api or s.meta_config_id_wa_cloud_api


# ── estado ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Status:
    state: State
    #: Si está encendida, aunque ``state`` diga ``reauthorize``: así la página
    #: sabe si ofrecer «Apagar».
    enabled: bool
    dataset_linked: bool
    sent_7d: int
    last_error_code: str | None
    last_error_at: datetime | None
    reconnect_config_id: str


async def _row(session: AsyncSession, channel_id: uuid.UUID) -> ChannelAdMeasurement | None:
    return (
        await session.execute(
            sa.select(ChannelAdMeasurement).where(ChannelAdMeasurement.channel_id == channel_id)
        )
    ).scalar_one_or_none()


async def status_of(session: AsyncSession, channel: Channel) -> Status | None:
    """El bloque de la página del número, o ``None`` si no admite la medición."""
    if not available(channel):
        return None
    row = await _row(session, channel.id)
    since = datetime.now(UTC) - timedelta(days=7)
    sent = await session.scalar(
        sa.select(sa.func.count())
        .select_from(AdConversionEvent)
        .where(
            AdConversionEvent.channel_id == channel.id,
            AdConversionEvent.status == "sent",
            AdConversionEvent.sent_at >= since,
        )
    )
    state: State = "off"
    if row is not None and row.last_error_code == REAUTHORIZE:
        state = REAUTHORIZE
    elif row is not None and row.enabled:
        state = "on"
    return Status(
        state=state,
        enabled=bool(row and row.enabled),
        dataset_linked=bool(row and row.meta_dataset_id),
        sent_7d=int(sent or 0),
        last_error_code=row.last_error_code if row else None,
        last_error_at=row.last_error_at if row else None,
        reconnect_config_id=reconnect_config_id(channel),
    )


# ── activar y desactivar ────────────────────────────────────────────────────


async def channel_credentials(session: AsyncSession, channel: Channel) -> MetaCredentials | None:
    """Las del número; las del tenant solo si son de ese mismo número."""
    own = await ChannelCredentialsRepository(session).get(channel.id)
    if own is not None:
        return own
    tenant = await MetaCredentialsRepository(session).get()
    pnid = (channel.config or {}).get("phone_number_id")
    if tenant is not None and (pnid is None or tenant.phone_number_id == pnid):
        return tenant
    return None


async def _upsert_row(session: AsyncSession, channel: Channel) -> ChannelAdMeasurement:
    row = await _row(session, channel.id)
    if row is None:
        row = ChannelAdMeasurement(
            tenant_id=channel.tenant_id, channel_id=channel.id, enabled=False
        )
        session.add(row)
    return row


async def enable(session: AsyncSession, channel: Channel, *, actor: str) -> ChannelAdMeasurement:
    """Requisitos 4.2 y 4.3. Lanza ``MeasurementError``; no deja nada a medias."""
    settings = get_settings()
    creds = await channel_credentials(session, channel)
    waba_id = (creds.waba_id if creds else None) or (channel.config or {}).get("waba_id")
    if creds is None or not waba_id:
        raise MeasurementError(409, REAUTHORIZE)
    client = meta_client()
    try:
        try:
            scopes = await client.token_scopes(
                input_token=creds.bisuat, app_id=settings.meta_app_id
            )
        except MetaAPIError as exc:
            log.warning(
                "ad_measurement.scope_check_failed", tenant_id=str(channel.tenant_id), code=exc.code
            )
            raise MeasurementError(502, "meta_unavailable") from None
        if EVENTS_SCOPE not in scopes:
            row = await _upsert_row(session, channel)
            row.enabled = False
            row.last_error_code = REAUTHORIZE
            row.last_error_at = datetime.now(UTC)
            await session.flush()
            raise MeasurementError(409, REAUTHORIZE)
        try:
            dataset_id = await client.ensure_dataset(
                waba_id=str(waba_id), access_token=creds.bisuat
            )
        except MetaAPIError as exc:
            log.warning(
                "ad_measurement.dataset_failed", tenant_id=str(channel.tenant_id), code=exc.code
            )
            raise MeasurementError(502, "meta_unavailable") from None
    finally:
        await client.close()
    row = await _upsert_row(session, channel)
    row.enabled = True
    row.meta_dataset_id = dataset_id[:64]
    row.enabled_by = actor
    row.enabled_at = datetime.now(UTC)
    row.last_error_code = None
    row.last_error_at = None
    await session.flush()
    log.info(
        "ad_measurement.changed",
        tenant_id=str(channel.tenant_id),
        channel_id=str(channel.id),
        enabled=True,
    )
    return row


async def disable(session: AsyncSession, channel: Channel, *, actor: str) -> ChannelAdMeasurement:
    """Requisito 4.4: deja de enviar desde ahora y descarta lo que espera."""
    row = await _upsert_row(session, channel)
    row.enabled = False
    row.disabled_by = actor
    row.disabled_at = datetime.now(UTC)
    await session.execute(
        sa.update(AdConversionEvent)
        .where(AdConversionEvent.channel_id == channel.id, AdConversionEvent.status == "pending")
        .values(status="discarded", lease_until=None, updated_at=sa.func.now())
    )
    await session.flush()
    log.info(
        "ad_measurement.changed",
        tenant_id=str(channel.tenant_id),
        channel_id=str(channel.id),
        enabled=False,
    )
    return row


def audit_after(row: ChannelAdMeasurement, *, confirm_data_sharing: bool) -> dict[str, Any]:
    return {
        "enabled": row.enabled,
        "confirm_data_sharing": confirm_data_sharing,
        "meta_dataset_id": row.meta_dataset_id,
    }
