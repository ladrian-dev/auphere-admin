"""Admin CRUD for ``owner_phone_index`` per tenant (Bloque D Fase 2).

Each tenant's backchannel registry — the phone numbers Auphere
recognises as "the owner of this tenant" + optionally which Auphere
channel sends them outbound. Endpoints:

- ``GET    /admin/tenants/{tenant_id}/backchannel/owners``       list
- ``POST   /admin/tenants/{tenant_id}/backchannel/owners``       register
- ``PATCH  /admin/tenants/{tenant_id}/backchannel/owners/{phone}`` update
  (activate / deactivate / change label / repin channel)
- ``DELETE /admin/tenants/{tenant_id}/backchannel/owners/{phone}`` remove

Inserts are guarded by the UNIQUE PK on ``phone_e164`` — a second
tenant trying to register the same phone gets a 409 with a message
pointing at the existing registration. The operator resolves manually
(usually by deactivating the previous one).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuphereOwnerChannel, OwnerPhoneIndex
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.auphere_channels import (
    OwnerPhoneIndexCreateIn,
    OwnerPhoneIndexOut,
    OwnerPhoneIndexUpdateIn,
)

router = APIRouter()
log = structlog.get_logger()


def _to_out(row: OwnerPhoneIndex) -> OwnerPhoneIndexOut:
    return OwnerPhoneIndexOut(
        phone_e164=row.phone_e164,
        tenant_id=row.tenant_id,
        user_label=row.user_label,
        active=row.active,
        added_at=row.added_at,
        auphere_channel_id=row.auphere_channel_id,
        confirmed_at=row.confirmed_at,
    )


def _audit_snapshot(row: OwnerPhoneIndex) -> dict[str, object]:
    return {
        "phone_e164": row.phone_e164,
        "user_label": row.user_label,
        "active": row.active,
        "auphere_channel_id": (str(row.auphere_channel_id) if row.auphere_channel_id else None),
    }


async def _validate_channel_id(global_session: AsyncSession, channel_id: uuid.UUID) -> None:
    """The channel registry is global (no RLS). Validate from the
    unscoped session passed by ``get_db_session`` — calling this from
    the tenant-scoped session would not find any rows."""
    row = await global_session.get(AuphereOwnerChannel, channel_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"auphere_channel_id {channel_id} does not exist",
        )
    if not row.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"auphere_channel_id {channel_id} is inactive — pick an "
                "active channel or omit to use the provider default"
            ),
        )


@router.get(
    "/tenants/{tenant_id}/backchannel/owners",
    response_model=list[OwnerPhoneIndexOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_owners(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> list[OwnerPhoneIndexOut]:
    """List every owner phone registered for this tenant. RLS-free
    table — we still scope the query to the tenant in WHERE so the
    behaviour matches operator expectations (per-tenant view)."""
    rows = await session.execute(
        select(OwnerPhoneIndex)
        .where(OwnerPhoneIndex.tenant_id == tenant_id)
        .order_by(OwnerPhoneIndex.added_at.asc())
    )
    return [_to_out(r) for r in rows.scalars()]


@router.post(
    "/tenants/{tenant_id}/backchannel/owners",
    response_model=OwnerPhoneIndexOut,
    status_code=status.HTTP_201_CREATED,
)
async def register_owner(
    tenant_id: uuid.UUID,
    body: OwnerPhoneIndexCreateIn,
    actor: str = Depends(require_admin_token),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> OwnerPhoneIndexOut:
    # ``OwnerPhoneIndex`` and ``AuphereOwnerChannel`` are both global
    # tables (no RLS) — the scoped session reads them fine. Writes go
    # through the scoped session too so the dependency's
    # ``async with session.begin()`` commits atomically with the
    # ``audit_log`` row.
    if body.auphere_channel_id is not None:
        await _validate_channel_id(session, body.auphere_channel_id)

    # PK collision: the phone is globally unique — a second tenant
    # cannot register it. The DB constraint catches this; we pre-check
    # so the operator gets a friendly 409 instead of an opaque 500.
    existing = await session.execute(
        select(OwnerPhoneIndex).where(OwnerPhoneIndex.phone_e164 == body.phone_e164)
    )
    prior = existing.scalar_one_or_none()
    if prior is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"phone {body.phone_e164} is already registered to tenant "
                f"{prior.tenant_id}. Deactivate the prior registration first."
            ),
        )

    row = OwnerPhoneIndex(
        phone_e164=body.phone_e164,
        tenant_id=tenant_id,
        user_label=body.user_label,
        added_at=datetime.now(UTC),
        active=True,
        auphere_channel_id=body.auphere_channel_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)

    await AuditRepository(session).record(
        actor=f"admin:{actor[:8]}",
        action="backchannel_owner.registered",
        target=f"owner_phone:{body.phone_e164}",
        after=_audit_snapshot(row),
    )
    log.info(
        "backchannel_owner.registered",
        tenant_id=str(tenant_id),
        phone=body.phone_e164,
    )
    return _to_out(row)


@router.patch(
    "/tenants/{tenant_id}/backchannel/owners/{phone_e164}",
    response_model=OwnerPhoneIndexOut,
)
async def update_owner(
    tenant_id: uuid.UUID,
    phone_e164: str,
    body: OwnerPhoneIndexUpdateIn,
    actor: str = Depends(require_admin_token),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> OwnerPhoneIndexOut:
    row = await session.get(OwnerPhoneIndex, phone_e164)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"phone {phone_e164} is not registered for this tenant",
        )

    if body.auphere_channel_id is not None:
        await _validate_channel_id(session, body.auphere_channel_id)

    before = _audit_snapshot(row)
    patch = body.model_dump(exclude_unset=True)
    if "user_label" in patch:
        row.user_label = patch["user_label"]
    if "active" in patch:
        row.active = patch["active"]
    # Channel pin — three cases:
    # - clear_channel_id=True  → set NULL (fallback to default)
    # - auphere_channel_id=<uuid> → set new pin
    # - neither → leave untouched
    if body.clear_channel_id:
        row.auphere_channel_id = None
    elif body.auphere_channel_id is not None:
        row.auphere_channel_id = body.auphere_channel_id

    await session.flush()
    await session.refresh(row)

    await AuditRepository(session).record(
        actor=f"admin:{actor[:8]}",
        action="backchannel_owner.updated",
        target=f"owner_phone:{phone_e164}",
        before=before,
        after=_audit_snapshot(row),
    )
    log.info(
        "backchannel_owner.updated",
        tenant_id=str(tenant_id),
        phone=phone_e164,
        fields=sorted(patch.keys()) + (["auphere_channel_id"] if body.clear_channel_id else []),
    )
    return _to_out(row)


@router.delete(
    "/tenants/{tenant_id}/backchannel/owners/{phone_e164}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deregister_owner(
    tenant_id: uuid.UUID,
    phone_e164: str,
    actor: str = Depends(require_admin_token),
    session: AsyncSession = Depends(scoped_session_from_path),
) -> None:
    """Hard delete — the row IS removed from the index. Owner stops
    being recognised; their inbound messages return 204
    ``ignored:unknown_phone`` at the webhook. Reversible by
    re-registering."""
    row = await session.get(OwnerPhoneIndex, phone_e164)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"phone {phone_e164} is not registered for this tenant",
        )
    before = _audit_snapshot(row)
    await session.delete(row)
    await session.flush()

    await AuditRepository(session).record(
        actor=f"admin:{actor[:8]}",
        action="backchannel_owner.deregistered",
        target=f"owner_phone:{phone_e164}",
        before=before,
    )
    log.info(
        "backchannel_owner.deregistered",
        tenant_id=str(tenant_id),
        phone=phone_e164,
    )
