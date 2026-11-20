"""Lectura/escritura de ``partner_model_allowlist`` bajo GUC ya fijado.

Spec 016 (R5.3): la allowlist es la única verdad de lo que un partner puede
elegir. Cuando se reescribe sin un modelo que algún cliente tenía enlazado,
``reconcile_bindings`` borra ese binding —el cliente pasa al modelo por
defecto en el siguiente turno— y avisa al partner con ``client.model_reset``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.partner_model_allowlist import PartnerModelAllowlist

log = structlog.get_logger(__name__)


async def read_allowlist(session: AsyncSession, partner_id: uuid.UUID) -> frozenset[str]:
    rows = await session.scalars(
        sa.select(PartnerModelAllowlist.model_id).where(
            PartnerModelAllowlist.partner_id == partner_id
        )
    )
    return frozenset(str(mid) for mid in rows.all())


async def replace_allowlist(
    session: AsyncSession, partner_id: uuid.UUID, model_ids: list[str]
) -> frozenset[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for mid in model_ids:
        if mid in seen:
            continue
        seen.add(mid)
        unique.append(mid)
    await session.execute(
        sa.delete(PartnerModelAllowlist).where(PartnerModelAllowlist.partner_id == partner_id)
    )
    for mid in unique:
        session.add(PartnerModelAllowlist(partner_id=partner_id, model_id=mid))
    await session.flush()
    return frozenset(unique)


@dataclass(frozen=True)
class ModelReset:
    tenant_id: uuid.UUID
    external_client_ref: str
    from_model: str
    to_model: str


async def reconcile_bindings(partner_id: uuid.UUID, allowed: frozenset[str]) -> list[ModelReset]:
    """Borra los bindings ``respond`` que la allowlist ya no permite y avisa.

    Sesiones propias: los bindings son de tenant (RLS) y el aviso es de
    partner, así que cada uno va en la suya. Se llama DESPUÉS de que la
    allowlist nueva esté confirmada; un aviso por cliente y modelo retirado
    (``dedupe_key``), para que reescribir la misma lista dos veces no
    avise dos veces. Nunca lanza: un cliente que no se pueda leer se salta
    y se registra.
    """
    # Spec 065 (requisito 12.4): la asignación de respuesta del cliente ya no decide nada y
    # sus filas se quedan hasta la migración siguiente; lo que una lista más corta cambia
    # es la elección de cada agente (T083).
    return []
