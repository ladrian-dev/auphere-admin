"""El origen de anuncio de un mensaje de WhatsApp — spec 076, requisito 1.1.

Meta manda en el primer mensaje que llega desde un anuncio de clic a WhatsApp
(o desde una publicación) un objeto ``referral``. El adaptador lo copia entero en
``InboundMessage.referral``; este módulo decide qué sale del proceso del webhook:

- solo las claves de la lista blanca, cada una cortada a su tope
  (``contracts/api-y-eventos.md`` §1);
- un ``source_type`` que no sea ``ad`` o ``post`` descarta el anuncio entero;
- sin nada más que el tipo, no hay origen.

El worker vuelve a pasar lo que lee del stream por ``parse_referral_field``: no
se fía de lo que viene de otra parte. ``ctwa_clid`` es un identificador personal
(único por clic): nunca va a un log.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import CustomerAdReferral

#: Las claves que pasan y su tope en caracteres. El orden no importa.
REFERRAL_LIMITS: Final[Mapping[str, int]] = {
    "source_type": 8,
    "source_id": 64,
    "source_url": 512,
    "headline": 200,
    "body": 500,
    "media_type": 16,
    "ctwa_clid": 256,
    "ref": 128,
}

SOURCE_TYPES: Final = frozenset({"ad", "post"})

#: La clave del stream de entrantes.
STREAM_FIELD: Final = "referral_json"


def clean_referral(raw: object) -> dict[str, str] | None:
    """Lo que sobrevive de un ``referral``: claves de la lista blanca, recortadas.

    ``None`` si no es un objeto, si el tipo no es ``ad`` ni ``post`` o si no queda
    nada más que el tipo."""
    if not isinstance(raw, Mapping):
        return None
    source_type = raw.get("source_type")
    if not isinstance(source_type, str) or source_type not in SOURCE_TYPES:
        return None
    out: dict[str, str] = {"source_type": source_type}
    for key, limit in REFERRAL_LIMITS.items():
        if key == "source_type":
            continue
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            continue
        text = str(value).strip()
        if text:
            out[key] = text[:limit]
    return out if len(out) > 1 else None


def referral_stream_field(raw: object) -> str | None:
    """El valor de ``referral_json`` para el stream, o ``None`` si no hay origen."""
    cleaned = clean_referral(raw)
    if cleaned is None:
        return None
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def parse_referral_field(value: str | None) -> dict[str, str] | None:
    """Lo que el worker lee de ``referral_json``, filtrado otra vez.

    Un JSON roto o que no es un objeto da ``None``: quien llama lo registra y el
    mensaje sigue su curso."""
    if not value:
        return None
    try:
        raw = json.loads(value)
    except (TypeError, ValueError):
        return None
    return clean_referral(raw)


async def last_click(
    session: AsyncSession, *, customer_id: uuid.UUID, channel_id: uuid.UUID
) -> CustomerAdReferral | None:
    """El último clic de un contacto en un número (requisito 1.3).

    El contacto y el número salen de la conversación que pide quien llama, nunca
    de una petición: garantía 8. La sesión ya lleva el tenant (RLS)."""
    return (
        await session.execute(
            sa.select(CustomerAdReferral)
            .where(
                CustomerAdReferral.customer_id == customer_id,
                CustomerAdReferral.channel_id == channel_id,
            )
            .order_by(CustomerAdReferral.clicked_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
