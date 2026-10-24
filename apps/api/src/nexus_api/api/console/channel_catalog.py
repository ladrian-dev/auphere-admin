"""``GET /console/channel-catalog`` — the channels a partner can connect (spec 046).

The same catalog as the operator panel (``services/channel_catalog.py``),
in the partner's words: no ADRs, no provider plumbing. Constitution §V,
amendment 1.2.0: the console may show what is coming, marked with its state
and **never startable**. Here that means one more rule than the panel's — a
channel the console has no connect step for is not startable here even when
the panel can start it (TikTok in beta is connected by the Auphere team).

The catalog is the same for every partner, so it takes no ``{ref}``: the
client the channel is for comes in the wizard's own path.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.services.channel_catalog import ChannelEntry, channel_catalog

router = APIRouter()

#: Channels the console can connect by itself today.
CONSOLE_STARTABLE = frozenset({"whatsapp"})

#: What each channel does, said to a partner.
_DESCRIPTION: dict[str, str] = {
    "whatsapp": "Tu cliente atiende en su número de WhatsApp Business. Es el canal principal.",
    "tiktok": "Responde los mensajes directos de la cuenta de empresa de TikTok.",
    "instagram": "Mensajes directos de la cuenta de Instagram del negocio.",
    "telegram": "Un bot de Telegram que contesta con el agente de tu cliente.",
    "x": "Mensajes directos de la cuenta de X del negocio.",
    "threads": "Conversaciones de la cuenta de Threads del negocio.",
}

#: Why a channel cannot be started from the console. Never a date.
_NOTE: dict[str, str] = {
    "pending": "Esperando la aprobación del proveedor.",
    "coming_soon": "Todavía no se puede conectar.",
}


class ConsoleChannelCatalogOut(BaseModel):
    key: str
    name: str
    description: str
    availability: Literal["available", "pending", "coming_soon"]
    note: str | None


def console_entry(entry: ChannelEntry) -> ConsoleChannelCatalogOut:
    """Pure: one catalog row as the partner sees it."""
    if entry.key in CONSOLE_STARTABLE and entry.availability in ("available", "beta"):
        availability: Literal["available", "pending", "coming_soon"] = "available"
    elif entry.availability == "pending":
        availability = "pending"
    else:
        # Built for the panel but not for the console, or not built yet.
        availability = "coming_soon"
    return ConsoleChannelCatalogOut(
        key=entry.key,
        name=entry.name,
        description=_DESCRIPTION.get(entry.key, entry.description),
        availability=availability,
        note=_NOTE.get(availability),
    )


@router.get("/channel-catalog", response_model=list[ConsoleChannelCatalogOut])
async def get_channel_catalog(
    _: ConsolePrincipal = Depends(require_console_principal("channels:read")),
) -> list[ConsoleChannelCatalogOut]:
    return [console_entry(c) for c in channel_catalog()]


__all__ = ["CONSOLE_STARTABLE", "console_entry", "router"]
