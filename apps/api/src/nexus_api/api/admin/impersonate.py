"""Admin F5 — impersonation overlay on a partner (not a partner session).

operator_id comes from the operator session the BFF already resolved
(``POST /admin/auth/session`` → ``X-Operator-Id``). The bearer is only
the panel service token; it never becomes the operator.

The cookie ``nexus_impersonate`` is set by the admin BFF, never here.
No partner JWT, no console cookie.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.partners import _admin_actor, _get_partner_or_404
from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_context import apply_admin_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.db.models.admin_impersonation import (
    TTL_DEFAULT_SECONDS,
    AdminImpersonationSession,
)
from nexus_api.repositories import AuditRepository
from nexus_api.schemas.admin_impersonate import AdminImpersonateIn, AdminImpersonateOut

router = APIRouter(dependencies=[Depends(require_admin_token)])

_UNKNOWN = "Unknown impersonation session"
_OPERATOR_HEADER = "X-Operator-Id"


def _unknown() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_UNKNOWN)


def _now() -> datetime:
    return datetime.now(UTC)


def _out(row: AdminImpersonationSession) -> AdminImpersonateOut:
    return AdminImpersonateOut(
        id=row.id,
        partner_id=row.partner_id,
        operator_id=row.operator_id,
        reason=row.reason,
        ttl_seconds=row.ttl_seconds,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


def _is_live(row: AdminImpersonationSession, *, now: datetime | None = None) -> bool:
    stamp = now or _now()
    if row.revoked_at is not None:
        return False
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires > stamp


async def _require_operator(
    session: AsyncSession,
    x_operator_id: str | None,
) -> uuid.UUID:
    """Resolve operator_id from the BFF session header, never from the bearer."""
    if not x_operator_id or not x_operator_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Operator-Id header",
        )
    raw = x_operator_id.strip()
    try:
        operator_id = uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        ) from exc
    account = await session.get(OperatorAccount, operator_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        )
    return account.id


def _assert_no_partner_session_payload(body: AdminImpersonateOut) -> None:
    """Documented contract: this overlay never mints a partner credential."""
    dumped = body.model_dump()
    for forbidden in ("token", "jwt", "access_token", "plaintext"):
        if forbidden in dumped:
            raise RuntimeError(f"impersonation payload leaked {forbidden}")


@router.post(
    "/partners/{partner_id}/impersonate",
    response_model=AdminImpersonateOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Partner not found."},
        422: {"description": "reason < 8, ttl fuera de 60-3600, o campos extra."},
    },
)
async def start_impersonation(
    partner_id: uuid.UUID,
    body: AdminImpersonateIn,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
    x_operator_id: str | None = Header(default=None, alias=_OPERATOR_HEADER),
) -> AdminImpersonateOut:
    """Open an admin overlay on the partner of the path. No cookie, no JWT."""
    ttl = body.ttl_seconds if body.ttl_seconds is not None else TTL_DEFAULT_SECONDS
    async with session.begin():
        # operator_auth has no grant to nexus_app — resolve as table owner.
        operator_id = await _require_operator(session, x_operator_id)
        await _get_partner_or_404(session, partner_id)
        await apply_admin_to_session(session)
        now = _now()
        row = AdminImpersonationSession(
            operator_id=operator_id,
            partner_id=partner_id,
            reason=body.reason,
            ttl_seconds=ttl,
            expires_at=now + timedelta(seconds=ttl),
        )
        session.add(row)
        await session.flush()
        await AuditRepository(session).record(
            actor=_admin_actor(actor),
            action="impersonate.start",
            target=f"partner:{partner_id}",
            before=None,
            after={
                "session_id": str(row.id),
                "operator_id": str(operator_id),
                "partner_id": str(partner_id),
                "reason": body.reason,
                "ttl_seconds": ttl,
                "expires_at": row.expires_at.isoformat(),
            },
            platform=True,
        )
        out = _out(row)
    _assert_no_partner_session_payload(out)
    return out


@router.post(
    "/impersonate/{session_id}/revoke",
    response_model=AdminImpersonateOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Foreign or missing session."}},
)
async def revoke_impersonation(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
    x_operator_id: str | None = Header(default=None, alias=_OPERATOR_HEADER),
) -> AdminImpersonateOut:
    """Revoke a live session of THIS operator. Foreign/missing → opaque 404."""
    async with session.begin():
        operator_id = await _require_operator(session, x_operator_id)
        await apply_admin_to_session(session)
        row = await session.get(AdminImpersonationSession, session_id)
        if row is None or row.operator_id != operator_id:
            raise _unknown()
        if row.revoked_at is None:
            row.revoked_at = _now()
            await session.flush()
            await AuditRepository(session).record(
                actor=_admin_actor(actor),
                action="impersonate.revoke",
                target=f"partner:{row.partner_id}",
                before={"session_id": str(row.id), "revoked_at": None},
                after={
                    "session_id": str(row.id),
                    "operator_id": str(operator_id),
                    "partner_id": str(row.partner_id),
                    "revoked_at": row.revoked_at.isoformat(),
                },
                platform=True,
            )
        out = _out(row)
    return out


@router.get("/impersonate/active", response_model=list[AdminImpersonateOut])
async def list_active_impersonations(
    session: AsyncSession = Depends(get_db_session),
    x_operator_id: str | None = Header(default=None, alias=_OPERATOR_HEADER),
) -> list[AdminImpersonateOut]:
    """Live sessions of THAT operator only. Expired/revoked are omitted."""
    now = _now()
    async with session.begin():
        operator_id = await _require_operator(session, x_operator_id)
        await apply_admin_to_session(session)
        rows = (
            await session.scalars(
                sa.select(AdminImpersonationSession)
                .where(
                    AdminImpersonationSession.operator_id == operator_id,
                    AdminImpersonationSession.revoked_at.is_(None),
                    AdminImpersonationSession.expires_at > now,
                )
                .order_by(AdminImpersonationSession.created_at.desc())
            )
        ).all()
        return [_out(row) for row in rows if _is_live(row, now=now)]


__all__ = ["router"]
