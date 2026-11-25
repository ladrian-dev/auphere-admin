"""Claves de envío de un cliente desde el panel — spec 077, requisito 5.

Hasta ahora la clave con la que un cliente de solo envío llama a
``POST /v1/messages/template`` solo la emitía un script. Aquí el operador la
lista, la emite, la rota y la revoca desde la ficha del cliente.

- La clave nace **ligada al cliente** (``api_keys.tenant_id``) y con el único
  permiso ``messages_send``: no puede actuar sobre otro cliente ni sobre la
  superficie de partners (``require_tenant_key``, ``tests/isolation/test_14``).
- Cuelga del partner del cliente o, si no tiene, del partner contenedor de los
  clientes directos de Auphere (el mismo que usó el script para New Air).
- Rotar conserva el cliente: lo contrario rompía la integración al vencer la
  gracia (``admin/partners.rotate_key`` tenía ese fallo y también se arregla).
- Cada escritura nombra al operador en la auditoría del cliente (§IV).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_enabled_operator
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import declare_tenant
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ApiKeyScope,
    AuditLog,
    OperatorAccount,
    Partner,
    PartnerApiKey,
    Tenant,
)
from nexus_api.metering.wallet import partner_id_for_tenant
from nexus_api.schemas.partner import ApiKeyOut
from nexus_api.services.console_v2 import born_on_new_console

router = APIRouter(prefix="/tenants", dependencies=[Depends(require_admin_token)])
log = structlog.get_logger(__name__)

#: El partner contenedor de los clientes directos (sin partner) de Auphere. La
#: FK ``api_keys.partner_id`` es obligatoria; quien decide el cliente es
#: ``api_keys.tenant_id``. Es el mismo slug que usó el alta a mano de New Air.
DIRECT_PARTNER_SLUG = "auphere-direct"


class TenantKeyOut(ApiKeyOut):
    """Una clave del cliente con quién la emitió (R5.1), leído de la auditoría.
    ``None`` para las que se emitieron fuera del panel (el script de New Air)."""

    created_by: str | None = None


class TenantKeyCreatedOut(BaseModel):
    """La única vez que la clave existe en claro fuera del sistema del cliente."""

    key: TenantKeyOut
    plaintext: str


class TenantKeyRotateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grace_hours: int = Field(default=24, ge=0, le=336)


def _who(actor: str | None) -> str | None:
    """``operator:luis@auphere.com`` → ``luis@auphere.com``."""
    return actor.removeprefix("operator:") if actor else None


def _snapshot(key: PartnerApiKey) -> dict[str, Any]:
    return ApiKeyOut.model_validate(key).model_dump(mode="json")


async def _tenant_or_404(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
    return tenant


async def _key_of_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, key_id: uuid.UUID
) -> PartnerApiKey:
    key: PartnerApiKey | None = await session.get(PartnerApiKey, key_id)
    if key is None or key.tenant_id != tenant_id:
        # Una clave de otro cliente es «no existe»: no se distingue (garantía 1).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key_not_found")
    return key


async def _partner_for(session: AsyncSession, tenant: Tenant) -> uuid.UUID:
    """El partner actual del cliente (``partner_tenants`` primero, como el resto
    del libro) o el contenedor de los directos (se crea si falta)."""
    current = await partner_id_for_tenant(session, tenant.id)
    if current is not None:
        return current
    partner = await session.scalar(sa.select(Partner).where(Partner.slug == DIRECT_PARTNER_SLUG))
    if partner is None:
        partner = born_on_new_console(
            Partner(id=uuid.uuid4(), name="Auphere Direct", slug=DIRECT_PARTNER_SLUG)
        )
        session.add(partner)
        await session.flush()
    return partner.id


def _audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    operator: OperatorAccount,
    action: str,
    key: PartnerApiKey,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=operator_actor(operator),
            action=action,
            target=f"key:{key.id}",
            before_json=before,
            after_json=after,
        )
    )


@asynccontextmanager
async def _client_transaction(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Una transacción de plataforma que declara el cliente: las claves y los
    partners son tablas de plataforma, la auditoría es del cliente. Cada
    consulta filtra por ``tenant_id`` ella misma (``declare_tenant``)."""
    async with get_sessionmaker()() as session, session.begin():
        await declare_tenant(session, tenant_id)
        yield session


@router.get("/{tenant_id}/api-keys", response_model=list[TenantKeyOut])
async def list_tenant_keys(tenant_id: uuid.UUID) -> list[TenantKeyOut]:
    """Todas las claves ligadas a este cliente, de cualquier partner, las más
    nuevas primero (también las creadas a mano antes de esta spec)."""
    async with get_sessionmaker()() as session, session.begin():
        await _tenant_or_404(session, tenant_id)
        await declare_tenant(session, tenant_id)
        keys = (
            await session.scalars(
                sa.select(PartnerApiKey)
                .where(PartnerApiKey.tenant_id == tenant_id)
                .order_by(PartnerApiKey.created_at.desc())
            )
        ).all()
        # Who issued each one: the audit row of its creation (or rotation).
        creators = {
            str(target).removeprefix("key:"): str(actor)
            for target, actor in (
                await session.execute(
                    sa.select(AuditLog.target, AuditLog.actor).where(
                        AuditLog.tenant_id == tenant_id,
                        AuditLog.action.in_(("tenant_key.create", "tenant_key.rotate")),
                    )
                )
            ).all()
        }
        return [
            TenantKeyOut(
                **ApiKeyOut.model_validate(k).model_dump(),
                created_by=_who(creators.get(str(k.id))),
            )
            for k in keys
        ]


@router.post(
    "/{tenant_id}/api-keys",
    response_model=TenantKeyCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant_key(
    tenant_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> TenantKeyCreatedOut:
    generated = generate_api_key()
    async with _client_transaction(tenant_id) as session:
        tenant = await _tenant_or_404(session, tenant_id)
        key = PartnerApiKey(
            id=uuid.uuid4(),
            partner_id=await _partner_for(session, tenant),
            tenant_id=tenant_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=[ApiKeyScope.MESSAGES_SEND.value],
        )
        session.add(key)
        await session.flush()
        await session.refresh(key)
        _audit(
            session,
            tenant_id=tenant_id,
            operator=operator,
            action="tenant_key.create",
            key=key,
            before=None,
            after=_snapshot(key),
        )
        out = TenantKeyOut(**ApiKeyOut.model_validate(key).model_dump(), created_by=operator.email)
    log.info("tenant_keys.created", tenant_id=str(tenant_id), prefix=out.prefix_snippet)
    return TenantKeyCreatedOut(key=out, plaintext=generated.plaintext)


@router.post(
    "/{tenant_id}/api-keys/{key_id}/rotate",
    response_model=TenantKeyCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
async def rotate_tenant_key(
    tenant_id: uuid.UUID,
    key_id: uuid.UUID,
    body: TenantKeyRotateIn,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> TenantKeyCreatedOut:
    """Una clave nueva del mismo cliente; la vieja sigue valiendo durante la
    gracia para que el cliente cambie su secreto sin cortar envíos."""
    async with _client_transaction(tenant_id) as session:
        old = await _key_of_tenant(session, tenant_id, key_id)
        if old.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="key_already_revoked")
        before = _snapshot(old)
        now = datetime.now(UTC)
        old.revoked_at = now
        old.grace_expires_at = now + timedelta(hours=body.grace_hours)
        generated = generate_api_key(old.type)
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
        new = PartnerApiKey(
            id=uuid.uuid4(),
            # R5.8: the client's CURRENT partner — one moved to another
            # partner takes its key along (its limit and its suspension).
            partner_id=await _partner_for(session, tenant),
            tenant_id=old.tenant_id,
            type=old.type,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=list(old.scopes or []),
            allowed_origins=list(old.allowed_origins or []),
            expires_at=old.expires_at,
        )
        session.add(new)
        await session.flush()
        await session.refresh(new)
        _audit(
            session,
            tenant_id=tenant_id,
            operator=operator,
            action="tenant_key.rotate",
            key=new,
            before=before,
            after={**_snapshot(new), "replaces": str(key_id), "grace_hours": body.grace_hours},
        )
        out = TenantKeyOut(**ApiKeyOut.model_validate(new).model_dump(), created_by=operator.email)
    return TenantKeyCreatedOut(key=out, plaintext=generated.plaintext)


@router.post("/{tenant_id}/api-keys/{key_id}/revoke", response_model=ApiKeyOut)
async def revoke_tenant_key(
    tenant_id: uuid.UUID,
    key_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> ApiKeyOut:
    """Sin gracia: la clave deja de valer ya."""
    async with _client_transaction(tenant_id) as session:
        key = await _key_of_tenant(session, tenant_id, key_id)
        before = _snapshot(key)
        key.revoked_at = datetime.now(UTC)
        key.grace_expires_at = None
        await session.flush()
        _audit(
            session,
            tenant_id=tenant_id,
            operator=operator,
            action="tenant_key.revoke",
            key=key,
            before=before,
            after=_snapshot(key),
        )
        return ApiKeyOut.model_validate(key)
