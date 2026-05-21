"""Admin endpoints for the Meta Embedded Signup flow.

The frontend (admin.auphere.com) opens Facebook Login for Business with
one of the registered configuration IDs. On success Meta returns a single-
use OAuth ``code`` together with a ``data`` envelope carrying the WABA /
phone_number / business IDs. The frontend POSTs everything to
``/admin/tenants/{tenant_id}/integrations/meta/signup`` and this module
hands it off to :class:`EmbeddedSignupOrchestrator`, which performs the
post-signup dance (exchange code → register phone → subscribe webhook →
persist credentials → upsert channel).

Auth: Bearer admin token (same pattern as the YCloud manual wizard). The
``tenant_id`` MUST come from the URL path, never from the request body —
``scoped_session_from_path`` enforces the tenant context for RLS before
the orchestrator runs.

This endpoint is the *only* place where a freshly-issued BISUAT crosses
into the database. The orchestrator handles encryption transparently via
the ``FernetEncrypted`` column type, so the response body never echoes
the token back. The caller sees the resulting ``channel_id`` and the
public-ish metadata (display phone, WABA id, expiry).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import (
    EmbeddedSignupOrchestrator,
    MetaAPIError,
    MetaClient,
    SignupIngressPayload,
)
from nexus_channels.whatsapp_meta.exceptions import (
    RegisterPhoneError,
    SubscribeWebhookError,
    TokenExchangeError,
)
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_redis, scoped_session_from_path
from nexus_api.config import get_settings
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog

router = APIRouter()
log = structlog.get_logger()


# ── request / response shapes ──────────────────────────────────────────────


class MetaSignupIn(BaseModel):
    """What the Embedded Signup frontend POSTs to the backend.

    ``code`` is the single-use OAuth code returned by Meta's
    ``FB.login({response_type: 'code'})``. ``waba_id`` is always present.

    ``phone_number_id`` and ``business_id`` are populated for the Cloud API
    flow (Meta sends them in the ``FINISH`` postMessage data envelope) but
    are absent for Coexistence — the
    ``FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`` event only carries
    ``waba_id``. The orchestrator derives ``phone_number_id`` from
    ``GET /{waba_id}/phone_numbers`` when missing.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=512)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str | None = Field(default=None, max_length=64)
    business_id: str | None = Field(default=None, max_length=64)
    mode: str = Field(
        default="cloud_api",
        pattern="^(cloud_api|coexistence)$",
        description=(
            "``cloud_api`` (Cloud-only) or ``coexistence`` (preserves the "
            "tenant's WhatsApp Business mobile app). The frontend picks "
            "this based on which configuration ID drove FB.login."
        ),
    )


class MetaSignupOut(BaseModel):
    status: str
    channel_id: uuid.UUID
    waba_id: str
    phone_number_id: str  # always present on output — orchestrator derives it for Coexistence
    display_phone_number: str
    mode: str
    bisuat_expires_at: str | None
    audit_log_id: uuid.UUID


# ── dependency factories ───────────────────────────────────────────────────


def _build_meta_client() -> MetaClient:
    """Constructor isolated so tests can override via
    ``app.dependency_overrides`` to swap in a respx-mocked HTTP client.
    """
    settings = get_settings()
    return MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )


# ── endpoint ───────────────────────────────────────────────────────────────


@router.post(
    "/tenants/{tenant_id}/integrations/meta/signup",
    response_model=MetaSignupOut,
    status_code=status.HTTP_201_CREATED,
)
async def meta_signup(
    body: MetaSignupIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
) -> MetaSignupOut:
    """Complete an Embedded Signup flow for the path tenant.

    The orchestrator is responsible for:

    1. Exchanging ``code`` → BISUAT via Graph OAuth.
    2. Registering the phone number under the Auphere app.
    3. Subscribing the WABA's webhook to our callback URL with a
       per-tenant verify token.
    4. Persisting the encrypted credentials.
    5. Upserting the ``channels`` row with ``provider="meta"``.
    6. Invalidating the tenant-resolver Redis cache for the business phone.

    Failures are mapped to HTTP codes the panel can act on:

    - ``400`` — bad ``code`` (TokenExchangeError) or Meta rejected register
      / subscribed_apps with a 4xx.
    - ``502`` — Meta unreachable or transient 5xx after retries.
    - ``409`` — the resolved business phone is already mapped to a *different*
      tenant. This happens when a Cultor-style migration off YCloud overlaps —
      the operator must offboard the YCloud channel first.
    """
    settings = get_settings()
    client = _build_meta_client()
    orchestrator = EmbeddedSignupOrchestrator(
        session=session,
        redis=redis,
        client=client,
        app_id=settings.meta_app_id,
        webhook_callback_url=settings.meta_webhook_callback_url,
    )
    payload = SignupIngressPayload(
        code=body.code,
        waba_id=body.waba_id,
        phone_number_id=body.phone_number_id,
        business_id=body.business_id,
        mode=body.mode,
    )
    try:
        result = await orchestrator.complete(payload)
    except TokenExchangeError as exc:
        log.warning("meta.signup.code_exchange_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Meta rechazó el OAuth code — probablemente expiró o ya fue "
                "consumido. El cliente debe repetir el flow desde el panel."
            ),
        ) from exc
    except RegisterPhoneError as exc:
        log.warning("meta.signup.register_phone_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Meta no aceptó el registro del número de teléfono. Causa "
                "habitual: el número ya está registrado bajo otra app con "
                "un PIN distinto, o no tiene display_phone_number todavía."
            ),
        ) from exc
    except SubscribeWebhookError as exc:
        log.warning("meta.signup.subscribe_webhook_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Meta no aceptó subscribed_apps — la WABA quedó sin "
                "webhook configurado. Revisar dashboard de la Meta App."
            ),
        ) from exc
    except MetaAPIError as exc:
        log.warning(
            "meta.signup.api_error",
            status=exc.status_code,
            code=exc.code,
            reason=exc.message,
        )
        http_status = (
            status.HTTP_502_BAD_GATEWAY
            if exc.status_code and exc.status_code >= 500
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=http_status,
            detail=f"Meta API error: {exc.message}",
        ) from exc
    finally:
        await client.close()

    # ``scoped_session_from_path`` already set the tenant context var;
    # ``require_current_tenant`` is the canonical way to read it back
    # (and asserts it's populated — guards against accidental misuse).
    from nexus_api.core.tenant_context import require_current_tenant

    tenant_id = require_current_tenant()
    audit = AuditLog(
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
        action="channel.whatsapp.meta_signup",
        target=f"channel:{result.channel_id}",
        before_json=None,
        after_json={
            "waba_id": result.waba_id,
            "phone_number_id": result.phone_number_id,
            "display_phone_number": result.display_phone_number,
            "mode": result.mode,
            "channel_id": str(result.channel_id),
            "bisuat_expires_at": (
                result.bisuat_expires_at.isoformat()
                if result.bisuat_expires_at is not None
                else None
            ),
        },
    )
    session.add(audit)
    await session.flush()

    log.info(
        "meta.signup.success",
        tenant_id=str(tenant_id),
        channel_id=str(result.channel_id),
        waba_id=result.waba_id,
        mode=result.mode,
    )

    return MetaSignupOut(
        status="connected",
        channel_id=result.channel_id,
        waba_id=result.waba_id,
        phone_number_id=result.phone_number_id,
        display_phone_number=result.display_phone_number,
        mode=result.mode,
        bisuat_expires_at=(
            result.bisuat_expires_at.isoformat() if result.bisuat_expires_at is not None else None
        ),
        audit_log_id=audit.id,
    )


__all__ = ["router"]
