"""Admin CRUD for the Auphere channel registry (Bloque D Fase 2).

Global endpoints — NOT scoped by ``scoped_session_from_path``. The
registry is platform-wide (one per Auphere installation), same shape
as ``connectors`` and ``tool_catalog``. Every write is audit-logged
with ``tenant_id = NULL`` (audit_log allows it for platform-level
actions; the rule applies the same as for connectors changes).

Operations:

- ``GET    /admin/auphere/channels``       list (active by default; ?include_inactive=true)
- ``POST   /admin/auphere/channels``       create
- ``GET    /admin/auphere/channels/{id}``  get one
- ``PATCH  /admin/auphere/channels/{id}``  update / rotate secret
- ``DELETE /admin/auphere/channels/{id}``  soft-deactivate (set active=false)

There is no hard-delete endpoint: deactivation is reversible via PATCH
and preserves any ``owner_phone_index.auphere_channel_id`` references
(which keep resolving via SET NULL fallback should the row ever be
removed by ops directly in SQL).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuphereOwnerChannel
from nexus_api.repositories import AuditRepository, AuphereChannelRepository
from nexus_api.schemas.auphere_channels import (
    AuphereOwnerChannelCreateIn,
    AuphereOwnerChannelOut,
    AuphereOwnerChannelUpdateIn,
)

router = APIRouter()
log = structlog.get_logger()


def _to_out(row: AuphereOwnerChannel) -> AuphereOwnerChannelOut:
    return AuphereOwnerChannelOut(
        id=row.id,
        phone_e164=row.phone_e164,
        display_name=row.display_name,
        country_code=row.country_code,
        provider=row.provider,
        provider_phone_id=row.provider_phone_id,
        active=row.active,
        is_default=row.is_default,
        has_webhook_secret=row.webhook_secret_encrypted is not None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _audit_snapshot(row: AuphereOwnerChannel) -> dict:
    """Snapshot fields we want in the audit log. The encrypted secret
    column is INTENTIONALLY excluded — even bytes form leaks rotation
    cadence to anyone reading audit. We only record whether it exists."""
    return {
        "phone_e164": row.phone_e164,
        "display_name": row.display_name,
        "country_code": row.country_code,
        "provider": row.provider,
        "provider_phone_id": row.provider_phone_id,
        "active": row.active,
        "is_default": row.is_default,
        "has_webhook_secret": row.webhook_secret_encrypted is not None,
    }


async def _record_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    row: AuphereOwnerChannel,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """Write a platform-level audit row (tenant_id = NULL). Uses
    :meth:`AuditRepository.record` with ``platform=True`` — migration
    0039 made ``audit_log.tenant_id`` nullable specifically for this
    class of action."""
    await AuditRepository(session).record(
        actor=actor,
        action=action,
        target=f"auphere_channel:{row.phone_e164}",
        before=before,
        after=after,
        platform=True,
    )


@router.get(
    "/auphere/channels",
    response_model=list[AuphereOwnerChannelOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_channels(
    include_inactive: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
) -> list[AuphereOwnerChannelOut]:
    repo = AuphereChannelRepository(session)
    rows = await repo.list_all(include_inactive=include_inactive)
    return [_to_out(r) for r in rows]


@router.get(
    "/auphere/channels/{channel_id}",
    response_model=AuphereOwnerChannelOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_channel(
    channel_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> AuphereOwnerChannelOut:
    repo = AuphereChannelRepository(session)
    row = await repo.get_by_id(channel_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"auphere channel {channel_id} not found",
        )
    return _to_out(row)


@router.post(
    "/auphere/channels",
    response_model=AuphereOwnerChannelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    body: AuphereOwnerChannelCreateIn,
    actor: str = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> AuphereOwnerChannelOut:
    # ``get_db_session`` yields a bare session without a transaction
    # wrapper — opposite of ``scoped_session_from_path``. Writes here
    # therefore need an explicit ``session.begin()`` so the row + the
    # audit_log entry land atomically (and so the test client sees the
    # data on subsequent requests).
    async with session.begin():
        # Pre-flight: phone must be unique. The DB constraint will catch
        # this too, but a 409 with a clean message beats a 500 from the
        # asyncpg integrity error.
        existing = await AuphereChannelRepository(session).get_by_phone(
            body.phone_e164, only_active=False
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"auphere channel with phone {body.phone_e164} already exists",
            )
        # Pre-flight: only one default per provider — short-circuit the
        # constraint with a friendly error.
        if body.is_default:
            repo = AuphereChannelRepository(session)
            prior_default = await repo.get_default(provider=body.provider)
            if prior_default is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"provider {body.provider!r} already has a default "
                        f"channel ({prior_default.phone_e164}); deactivate "
                        "is_default on the existing row first"
                    ),
                )

        row = AuphereOwnerChannel(
            phone_e164=body.phone_e164,
            display_name=body.display_name,
            country_code=body.country_code,
            provider=body.provider,
            provider_phone_id=body.provider_phone_id,
            is_default=body.is_default,
            active=True,
            webhook_secret_encrypted=(
                body.webhook_secret.encode("utf-8") if body.webhook_secret else None
            ),
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        await _record_audit(
            session,
            actor=f"admin:{actor[:8]}",
            action="auphere_channel.created",
            row=row,
            after=_audit_snapshot(row),
        )
        log.info(
            "auphere_channel.created",
            phone=body.phone_e164,
            display_name=body.display_name,
            is_default=body.is_default,
        )
        return _to_out(row)


@router.patch(
    "/auphere/channels/{channel_id}",
    response_model=AuphereOwnerChannelOut,
)
async def update_channel(
    channel_id: uuid.UUID,
    body: AuphereOwnerChannelUpdateIn,
    actor: str = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> AuphereOwnerChannelOut:
    async with session.begin():
        repo = AuphereChannelRepository(session)
        row = await repo.get_by_id(channel_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"auphere channel {channel_id} not found",
            )
        before = _audit_snapshot(row)

        # Apply only the fields the caller provided. ``model_dump(
        # exclude_unset=True)`` distinguishes "field omitted" from "field
        # set to null" — important for ``is_default=False`` toggles.
        patch = body.model_dump(exclude_unset=True)

        # Handle is_default flipping: if turning ON, ensure no other default
        # exists for this provider. If turning OFF, no-op (DB allows it).
        if patch.get("is_default") is True and not row.is_default:
            existing_default = await repo.get_default(provider=row.provider)
            if existing_default is not None and existing_default.id != row.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"provider {row.provider!r} already has a default "
                        f"channel ({existing_default.phone_e164}); deactivate "
                        "the other default first"
                    ),
                )

        for field in (
            "display_name",
            "country_code",
            "provider_phone_id",
            "active",
            "is_default",
        ):
            if field in patch:
                setattr(row, field, patch[field])

        # Webhook secret rotation: empty string ⇒ clear; non-empty ⇒
        # encrypt + store; omitted ⇒ leave untouched. The Fernet column
        # encrypts on the way in via the TypeDecorator.
        if "webhook_secret" in patch:
            secret = patch["webhook_secret"]
            row.webhook_secret_encrypted = (
                secret.encode("utf-8") if secret else None
            )

        await session.flush()
        await session.refresh(row)
        await _record_audit(
            session,
            actor=f"admin:{actor[:8]}",
            action="auphere_channel.updated",
            row=row,
            before=before,
            after=_audit_snapshot(row),
        )
        log.info(
            "auphere_channel.updated",
            channel_id=str(channel_id),
            fields=sorted(patch.keys()),
        )
        return _to_out(row)


@router.delete(
    "/auphere/channels/{channel_id}",
    response_model=AuphereOwnerChannelOut,
)
async def deactivate_channel(
    channel_id: uuid.UUID,
    actor: str = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> AuphereOwnerChannelOut:
    """Soft-deactivate. Sets ``active=false`` (and clears
    ``is_default`` if set) so the inbound webhook treats further
    traffic to this number as foreign destination + the resolver stops
    picking it. Reversible via PATCH ``active=true``. No hard-delete
    endpoint — keeps audit references stable."""
    async with session.begin():
        repo = AuphereChannelRepository(session)
        row = await repo.get_by_id(channel_id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"auphere channel {channel_id} not found",
            )
        before = _audit_snapshot(row)
        row.active = False
        row.is_default = False
        await session.flush()
        await session.refresh(row)
        await _record_audit(
            session,
            actor=f"admin:{actor[:8]}",
            action="auphere_channel.deactivated",
            row=row,
            before=before,
            after=_audit_snapshot(row),
        )
        log.info(
            "auphere_channel.deactivated",
            channel_id=str(channel_id),
            phone=row.phone_e164,
        )
        return _to_out(row)
