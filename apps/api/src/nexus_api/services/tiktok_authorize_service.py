"""Shared TikTok authorisation orchestration.

The counterpart to :mod:`nexus_api.services.meta_signup_service`. Both the
operator panel and (later) the partner self-serve surface complete the same
post-authorisation dance, so it lives in one place and neither entry point
can drift from the other.

Responsibilities beyond delegating to the orchestrator:

- Map TikTok failures to HTTP codes the caller can act on.
- Write the audit row.
- Keep the tokens off the response. Nothing here echoes an access token
  back to the client; callers only see the channel id and public metadata.

The caller is responsible for having applied the tenant RLS scope to
``session`` before calling in. ``tenant_id`` is passed explicitly for the
audit row so this helper never depends on the request-scoped context var.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

import structlog
from fastapi import HTTPException, status
from nexus_channels.tiktok_bm import TikTokClient
from nexus_channels.tiktok_bm.authorize import (
    TikTokAuthorizationOrchestrator,
    TikTokAuthorizationResult,
)
from nexus_channels.tiktok_bm.exceptions import (
    TikTokAPIError,
    TikTokNoBusinessAccountError,
    TikTokRegionNotSupportedError,
    TikTokTokenExchangeError,
    TikTokWebhookSetupError,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog
from nexus_api.services.tiktok_oauth_state import sign_oauth_state

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TikTokAuthorizeServiceResult:
    """Orchestrator result plus the id of the audit row this helper wrote."""

    result: TikTokAuthorizationResult
    audit_log_id: uuid.UUID


def build_tiktok_client() -> TikTokClient:
    """Constructor isolated so tests can override it via
    ``app.dependency_overrides`` to swap in a mocked transport.
    """
    settings = get_settings()
    return TikTokClient(
        settings.tiktok_app_id,
        settings.tiktok_app_secret,
        base_url=settings.tiktok_api_base_url,
        api_version=settings.tiktok_api_version,
    )


def require_tiktok_enabled() -> None:
    """Guard every TikTok entry point.

    The channel ships dark until TikTok approves the Business Messaging
    review. Failing here with an explanation beats letting an operator start
    a flow that will die at the token exchange with an opaque provider error.
    """
    settings = get_settings()
    if not settings.tiktok_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El canal de TikTok está desactivado en este entorno. Se activa "
                "con NEXUS_TIKTOK_ENABLED una vez que TikTok apruebe el acceso "
                "al Business Messaging API."
            ),
        )


def build_authorization_url(*, tenant_id: uuid.UUID) -> str:
    """URL to send the business owner to, with a tenant-bound signed state.

    The base URL is **not constructed here**. TikTok issues the "TikTok
    account holder authorization URL" per app (My Apps > App Detail > Basic
    Information), already carrying the app id and the permission set; our job
    is only to append a signed ``state``, which TikTok echoes back to the
    callback.

    The state is what makes the callback safe: it is the only thing telling
    the callback which tenant is connecting, and it is signed so it cannot be
    pointed at someone else's tenant.
    """
    require_tiktok_enabled()
    settings = get_settings()
    base = settings.tiktok_authorize_url.strip()
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Falta NEXUS_TIKTOK_AUTHORIZE_URL. Es la 'TikTok account holder "
                "authorization URL' que TikTok genera para la app (My Apps > App "
                "Detail > Basic Information); aparece una vez que la app tiene el "
                "permiso TikTok Accounts. Hay que copiarla tal cual."
            ),
        )
    state, _payload = sign_oauth_state(
        tenant_id=tenant_id,
        secret=settings.tiktok_oauth_state_secret,
    )
    # The issued URL already has query parameters, so append rather than
    # assume we own the query string.
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'state': state})}"


async def complete_tiktok_authorization(
    *,
    session: AsyncSession,
    redis: Redis,
    auth_code: str,
    tenant_id: uuid.UUID,
    actor: str,
    audit_action: str,
) -> TikTokAuthorizeServiceResult:
    """Run the post-authorisation flow and write an audit row.

    Maps TikTok failures to HTTP codes:

    - ``400`` — bad or reused ``auth_code``, or no Business Account behind
      the authorisation.
    - ``409`` — the Business Account is in a region TikTok excludes from
      Business Messaging. Not a client error to retry; a permanent conflict
      between the account and the product.
    - ``502`` — TikTok unreachable, or a transient failure after retries,
      including a webhook registration we could not complete.

    ``tenant_id`` MUST be the tenant already scoped onto ``session`` — the
    caller enforces that it comes from a trusted source (the signed OAuth
    state or the URL path), never from the request body.
    """
    require_tiktok_enabled()
    settings = get_settings()
    client = build_tiktok_client()
    orchestrator = TikTokAuthorizationOrchestrator(
        session=session,
        redis=redis,
        client=client,
        webhook_callback_url=settings.tiktok_webhook_callback_url,
        redirect_uri=settings.tiktok_redirect_uri,
    )
    try:
        result = await orchestrator.complete(auth_code=auth_code)
    except TikTokTokenExchangeError as exc:
        log.warning("tiktok.authorize.code_exchange_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "TikTok rechazó el código de autorización — probablemente expiró "
                "o ya fue usado. El cliente debe repetir la conexión desde el panel."
            ),
        ) from exc
    except TikTokNoBusinessAccountError as exc:
        log.warning("tiktok.authorize.no_business_account", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "La autorización no expuso ninguna cuenta TikTok Business. "
                "Business Messaging solo funciona con cuentas Business — si el "
                "cliente autorizó con una cuenta personal, debe convertirla "
                "primero y volver a intentar."
            ),
        ) from exc
    except TikTokRegionNotSupportedError as exc:
        log.warning("tiktok.authorize.region_unsupported", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "TikTok no ofrece Business Messaging para cuentas registradas en "
                "el EEE, Suiza o Reino Unido. Esta cuenta no puede conectarse "
                "como canal."
            ),
        ) from exc
    except TikTokWebhookSetupError as exc:
        log.warning("tiktok.authorize.webhook_setup_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "TikTok aceptó la autorización pero rechazó el registro del "
                "webhook — el canal quedaría sordo. Reintentar la conexión desde "
                "el panel; si persiste, revisar la app en el portal de TikTok."
            ),
        ) from exc
    except TikTokAPIError as exc:
        log.warning(
            "tiktok.authorize.api_error",
            status=exc.status_code,
            code=exc.code,
            request_id=exc.request_id,
            reason=exc.message,
        )
        http_status = (
            status.HTTP_502_BAD_GATEWAY
            if exc.status_code and exc.status_code >= 500
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=http_status,
            detail=f"TikTok API error: {exc.message}",
        ) from exc
    finally:
        await client.close()

    audit = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        action=audit_action,
        target=f"channel:{result.channel_id}",
        before_json=None,
        # Deliberately no token material — an audit row is one of the most
        # widely-read tables in the system.
        after_json={
            "business_id": result.business_id,
            "display_name": result.display_name,
            "region": result.region,
            "channel_id": str(result.channel_id),
            "webhook_config_id": result.webhook_config_id,
            "access_token_expires_at": (
                result.access_token_expires_at.isoformat()
                if result.access_token_expires_at is not None
                else None
            ),
        },
    )
    session.add(audit)
    await session.flush()

    log.info(
        "tiktok.authorize.success",
        tenant_id=str(tenant_id),
        channel_id=str(result.channel_id),
        business_id=result.business_id,
        action=audit_action,
    )
    return TikTokAuthorizeServiceResult(result=result, audit_log_id=audit.id)


async def disconnect_tiktok(
    *,
    session: AsyncSession,
    redis: Redis,
    tenant_id: uuid.UUID,
    actor: str,
) -> uuid.UUID:
    """Offboard the tenant from TikTok and write an audit row."""
    require_tiktok_enabled()
    settings = get_settings()
    client = build_tiktok_client()
    orchestrator = TikTokAuthorizationOrchestrator(
        session=session,
        redis=redis,
        client=client,
        webhook_callback_url=settings.tiktok_webhook_callback_url,
        redirect_uri=settings.tiktok_redirect_uri,
    )
    try:
        await orchestrator.disconnect()
    finally:
        await client.close()

    audit = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        action="channel.tiktok.disconnect",
        target=f"tenant:{tenant_id}",
        before_json=None,
        after_json={"status": "disconnected"},
    )
    session.add(audit)
    await session.flush()
    return audit.id


__all__ = [
    "TikTokAuthorizeServiceResult",
    "build_authorization_url",
    "build_tiktok_client",
    "complete_tiktok_authorization",
    "disconnect_tiktok",
    "require_tiktok_enabled",
]
