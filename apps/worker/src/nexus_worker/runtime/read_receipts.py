"""Acuse de lectura — lado runner (plataforma v2, cierre del SLI de ack).

Los dos ticks azules se enviaban DENTRO del handler del webhook: una
llamada HTTPS a graph.facebook.com esperada antes de contestarle 200 a
Meta, reteniendo mientras tanto la conexión de base de datos de la
petición y abriendo un cliente httpx nuevo (handshake TLS nuevo) por cada
mensaje entrante. Medido el 2026-08-09 sobre staging: ~40 % del ack, y eso
con la llamada FALLANDO rápido — en producción tiene éxito y cuesta más.
Con eso dentro, ``webhook_ack_ms`` p95 < 50 ms es inalcanzable, y una
degradación de la API de Meta se realimentaba: ack lento → Meta reintenta
el webhook → más carga sobre el mismo cuello.

Ahora el webhook solo DECIDE (es donde están el canal y las políticas del
agente) y marca ``mark_read`` en la entrada del stream; el envío ocurre
aquí, al recoger el turno, reutilizando el adaptador de larga vida que el
worker ya construye una sola vez al arrancar.

El emisor se inyecta por proceso (``set_read_receipt_sender`` desde
bootstrap) igual que el fetcher de media: el dispatcher sigue sin
constructor y los tests sustituyen un doble.

Contrato: **nunca lanza y nunca bloquea el turno**. Un acuse perdido es
cosmético; un turno perdido no.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog

log = structlog.get_logger(__name__)

# adapter.mark_as_read-compatible (keyword-only).
ReadReceiptSender = Callable[..., Awaitable[None]]

_senders: dict[str, ReadReceiptSender] = {}


def set_read_receipt_sender(provider: str, sender: ReadReceiptSender | None) -> None:
    """Registrar (o quitar, con ``None``) el emisor de un proveedor."""
    if sender is None:
        _senders.pop(provider, None)
        return
    _senders[provider] = sender


def reset_read_receipt_senders() -> None:
    _senders.clear()


async def send_read_receipt(
    *,
    provider: str,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    wamid: str | None,
) -> bool:
    """Enviar el acuse. Devuelve si llegó a intentarse (para tests/logs).

    Sin ``wamid`` no hay nada que marcar, y sin emisor registrado para el
    proveedor tampoco: ambos casos son no-op silenciosos, no errores.
    """
    if not wamid:
        return False
    sender = _senders.get(provider)
    if sender is None:
        return False
    try:
        await sender(
            from_phone="",  # el phone_number_id lo resuelve el loader de credenciales
            wamid=wamid,
            tenant_id=tenant_id,
            channel_id=channel_id,
        )
    except Exception as exc:
        log.info(
            "read_receipt.failed",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            provider=provider,
            error=str(exc),
        )
        return False
    return True
