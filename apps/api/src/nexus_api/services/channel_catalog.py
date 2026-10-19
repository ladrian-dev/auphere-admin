"""The channel catalog — spec 035.

Which messaging channels exist for Auphere and whether each one can be
connected today. Availability is decided here, on the server, from what the
code can actually do and how it is configured:

* ``available`` — production-ready: WhatsApp through Meta's Cloud API.
* ``beta`` — built and switched on, still young: TikTok with ``tiktok_enabled``.
* ``pending`` — built, waiting for the provider: TikTok without the flag
  (the TikTok app is under the platform's review).
* ``coming_soon`` — not built: Instagram (ADR, plan), Telegram, X, Threads.

Only the operator panel shows ``pending`` and ``coming_soon`` (constitution
§V, amendment 1.1.0). Neither can be started.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nexus_api.config import get_settings

Availability = Literal["available", "beta", "pending", "coming_soon"]


@dataclass(frozen=True)
class ChannelEntry:
    key: str
    name: str
    description: str
    availability: Availability
    #: One line on why it cannot be started, for pending / coming soon.
    note: str | None = None


def channel_catalog() -> list[ChannelEntry]:
    settings = get_settings()
    tiktok_on = bool(settings.tiktok_enabled)
    return [
        ChannelEntry(
            key="whatsapp",
            name="WhatsApp",
            description="Atiende a los clientes en su número de WhatsApp Business, por la API de Meta.",
            availability="available",
        ),
        ChannelEntry(
            key="tiktok",
            name="TikTok",
            description="Responde los mensajes directos de la cuenta de empresa de TikTok.",
            availability="beta" if tiktok_on else "pending",
            note=None if tiktok_on else "Pendiente de la aprobación de TikTok.",
        ),
        ChannelEntry(
            key="instagram",
            name="Instagram",
            description="Mensajes directos y respuestas a comentarios de Instagram.",
            availability="coming_soon",
            note="Diseñado (ADR-030); se construye en su propia spec.",
        ),
        ChannelEntry(
            key="telegram",
            name="Telegram",
            description="Un bot de Telegram que atiende con el agente del cliente.",
            availability="coming_soon",
        ),
        ChannelEntry(
            key="x",
            name="X",
            description="Mensajes directos de la cuenta de X del negocio.",
            availability="coming_soon",
        ),
        ChannelEntry(
            key="threads",
            name="Threads",
            description="Conversaciones de la cuenta de Threads del negocio.",
            availability="coming_soon",
        ),
    ]
