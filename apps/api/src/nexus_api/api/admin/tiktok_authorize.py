"""Admin endpoints for the TikTok Business Messaging authorisation flow.

Three surfaces, with deliberately different auth models:

``POST /admin/tenants/{tenant_id}/integrations/tiktok/authorize-url``
    Operator-facing. Bearer admin token, tenant from the path. Returns the
    URL to send the business owner to, carrying a signed, tenant-bound
    ``state``.

``GET /admin/integrations/tiktok/callback``
    **Browser-facing and unauthenticated by design.** TikTok redirects the
    business owner's browser here; there is no admin token in that request
    and no session to read. The signed ``state`` is the authentication: it
    is the only thing that says which tenant is connecting, and it is
    HMAC-verified before anything is written. An unsigned or expired state
    is rejected outright — accepting a tenant id from an unauthenticated
    query parameter would be a cross-tenant write.

``DELETE /admin/tenants/{tenant_id}/integrations/tiktok``
    Operator-facing offboarding. Bearer admin token, tenant from the path.

Note the asymmetry with the Meta flow: Embedded Signup hands the OAuth code
to *our own frontend*, which POSTs it back with an admin token, so the tenant
can come from the URL path. TikTok uses a plain server-side redirect, so the
tenant has to travel inside the state instead. That is the reason
:mod:`nexus_api.services.tiktok_oauth_state` exists and why it is treated as
an isolation-boundary component rather than a convenience.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis, scoped_session_from_path
from nexus_api.config import get_settings
from nexus_api.core.security import require_admin_token
from nexus_api.repositories import TenantRepository
from nexus_api.services.tiktok_authorize_service import (
    build_authorization_url,
    complete_tiktok_authorization,
    disconnect_tiktok,
    require_tiktok_enabled,
)
from nexus_api.services.tiktok_oauth_state import (
    OAuthStateExpired,
    OAuthStateInvalid,
    verify_oauth_state,
)

router = APIRouter()
log = structlog.get_logger()


# ── shapes ──────────────────────────────────────────────────────────────────


class TikTokAuthorizeUrlOut(BaseModel):
    authorize_url: str


class TikTokDisconnectOut(BaseModel):
    status: str
    audit_log_id: uuid.UUID


# ── operator: start the flow ────────────────────────────────────────────────


@router.post(
    "/tenants/{tenant_id}/integrations/tiktok/authorize-url",
    response_model=TikTokAuthorizeUrlOut,
)
async def tiktok_authorize_url(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TikTokAuthorizeUrlOut:
    """Mint the URL the business owner opens to authorise the Auphere app.

    Depends on ``scoped_session_from_path`` purely so a request for a tenant
    that does not exist 404s here rather than producing a working URL that
    fails minutes later in the callback.
    """
    return TikTokAuthorizeUrlOut(authorize_url=build_authorization_url(tenant_id=tenant_id))


# ── browser: TikTok's redirect lands here ───────────────────────────────────


@router.get("/integrations/tiktok/callback")
async def tiktok_callback(
    auth_code: str = Query(..., min_length=1, max_length=1024, alias="auth_code"),
    state: str = Query(..., min_length=1, max_length=2048),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> RedirectResponse:
    """Complete the authorisation for whichever tenant the state names.

    No admin token: this is the business owner's browser coming back from
    TikTok. Everything hangs off the signed state, so it is verified first
    and nothing else in the query string is trusted.

    On success and on failure the owner is redirected back to the panel with
    a status in the query string — a raw JSON body here would leave a person
    staring at an API response in their browser.
    """
    require_tiktok_enabled()
    settings = get_settings()

    try:
        payload = verify_oauth_state(state=state, secret=settings.tiktok_oauth_state_secret)
    except OAuthStateExpired as exc:
        log.warning("tiktok.callback.state_expired", reason=str(exc))
        return _redirect_to_panel(tenant_id=None, status_key="state_expired")
    except OAuthStateInvalid as exc:
        # Not a user error — a mismatched HMAC means forgery or a rotated
        # secret. Log it and give the browser nothing to work with.
        log.warning("tiktok.callback.state_invalid", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization state",
        ) from exc

    tenant_id = payload.tenant_id

    # Scope the session by hand: the tenant came from the verified state, not
    # from the path, so ``scoped_session_from_path`` cannot be used here.
    from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session

    token = _current_tenant.set(tenant_id)
    try:
        async with session.begin():
            tenant = await TenantRepository(session).get(tenant_id)
            if tenant is None:
                log.warning("tiktok.callback.unknown_tenant", tenant_id=str(tenant_id))
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="tenant not found",
                )
            await apply_tenant_to_session(session, tenant_id)
            try:
                await complete_tiktok_authorization(
                    session=session,
                    redis=redis,
                    auth_code=auth_code,
                    tenant_id=tenant_id,
                    actor="tiktok:oauth_callback",
                    audit_action="channel.tiktok.authorize",
                )
            except HTTPException as exc:
                # The service layer already logged and classified this. Roll
                # the transaction back, then send the owner somewhere they
                # can read the reason.
                log.warning(
                    "tiktok.callback.failed",
                    tenant_id=str(tenant_id),
                    status=exc.status_code,
                )
                raise _CallbackFailure(exc.status_code) from exc
    except _CallbackFailure as failure:
        return _redirect_to_panel(tenant_id=tenant_id, status_key=f"error_{failure.status_code}")
    finally:
        _current_tenant.reset(token)

    return _redirect_to_panel(tenant_id=tenant_id, status_key="connected")


class _CallbackFailure(Exception):
    """Internal: unwinds the transaction while keeping the HTTP status so the
    redirect can tell the owner what happened."""

    def __init__(self, status_code: int) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code


def _redirect_to_panel(*, tenant_id: uuid.UUID | None, status_key: str) -> RedirectResponse:
    settings = get_settings()
    base = settings.admin_panel_base_url.rstrip("/")
    target = (
        f"{base}/tenants/{tenant_id}/connectors?tiktok={status_key}"
        if tenant_id is not None
        else f"{base}/connectors?tiktok={status_key}"
    )
    # 303: the callback is a GET but the browser must not re-run it on
    # refresh — a consumed auth_code would fail the second time.
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


# ── operator: offboard ──────────────────────────────────────────────────────


@router.delete(
    "/tenants/{tenant_id}/integrations/tiktok",
    response_model=TikTokDisconnectOut,
)
async def tiktok_disconnect(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
) -> TikTokDisconnectOut:
    """Delete the TikTok webhook registration, drop the credentials and mark
    the channel disconnected."""
    audit_log_id = await disconnect_tiktok(
        session=session,
        redis=redis,
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
    )
    return TikTokDisconnectOut(status="disconnected", audit_log_id=audit_log_id)
