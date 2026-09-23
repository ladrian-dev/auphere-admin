"""Lectura/escritura de ``partner_model_allowlist`` bajo GUC ya fijado.

Spec 016 (R5.3): la allowlist es la única verdad de lo que un partner puede
elegir. Cuando se reescribe sin un modelo que algún cliente tenía enlazado,
``reconcile_bindings`` borra ese binding —el cliente pasa al modelo por
defecto en el siguiente turno— y avisa al partner con ``client.model_reset``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

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
    from nexus_api.core.respond_catalog import RESPOND_MODELS, RESPOND_ROLE, SOL_MODEL_ID
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import NotificationKind, NotificationSeverity, PartnerTenant
    from nexus_api.services.console_notifications import emit_detached

    to_model = dict(RESPOND_MODELS).get(SOL_MODEL_ID, SOL_MODEL_ID)
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        mappings = (
            await session.execute(
                sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref).where(
                    PartnerTenant.partner_id == partner_id
                )
            )
        ).all()
    resets: list[ModelReset] = []
    for tenant_id, ref in mappings:
        try:
            async with sm() as scoped, tenant_scoped_session(scoped, tenant_id):
                row = (
                    (
                        await scoped.execute(
                            sa.text(
                                """
                                SELECT b.id, p.model_id, p.display_name
                                  FROM tenant_model_bindings b
                                  JOIN model_profiles p ON p.id = b.model_profile_id
                                 WHERE b.role = :role
                                """
                            ),
                            {"role": RESPOND_ROLE},
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None or str(row["model_id"]) in allowed:
                    continue
                await scoped.execute(
                    sa.text("DELETE FROM tenant_model_bindings WHERE id = :id"), {"id": row["id"]}
                )
                from_id, from_model = str(row["model_id"]), str(row["display_name"])
            await emit_detached(
                partner_id=partner_id,
                kind=NotificationKind.CLIENT_MODEL_RESET,
                data={"external_client_ref": ref, "from_model": from_model, "to_model": to_model},
                severity=NotificationSeverity.INFO,
                external_client_ref=ref,
                dedupe_key=(
                    f"partner:{partner_id}:client.model_reset:{ref}:{from_id}:"
                    f"{datetime.now(UTC):%Y-%m-%d}"
                ),
            )
            resets.append(ModelReset(tenant_id, ref, from_model, to_model))
        except Exception as exc:
            log.warning(
                "partner_allowlist.reconcile_failed",
                partner_id=str(partner_id),
                tenant_id=str(tenant_id),
                error=str(exc),
            )
    return resets
