"""Shared Meta Embedded Signup orchestration.

Both the operator panel (``admin/tenants/{id}/integrations/meta/signup``)
and the partner self-serve surface (``/v1/partners/clients/{ref}/whatsapp/
signup``) complete the *same* post-signup dance: exchange code → register
phone → subscribe webhook → persist credentials → upsert channel. This
module is the single place that runs it and maps Meta failures to the HTTP
codes the caller can act on, so the two entry points never drift.

The caller is responsible for having applied the tenant RLS scope to
``session`` (``apply_tenant_to_session`` / ``scoped_session_from_path``)
before calling in — the orchestrator writes the tenant-scoped ``channels``
row. ``tenant_id`` is passed explicitly for the audit row so this helper
never depends on the request-scoped context var.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, status
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
from nexus_channels.whatsapp_meta.signup import SignupResult
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SignupServiceResult:
    """Orchestrator result plus the id of the audit row this helper wrote."""

    result: SignupResult
    audit_log_id: uuid.UUID


def build_meta_client() -> MetaClient:
    """Constructor isolated so tests can override it via
    ``app.dependency_overrides`` to swap in a respx-mocked HTTP client.
    """
    settings = get_settings()
    return MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )


async def complete_meta_signup(
    *,
    session: AsyncSession,
    redis: Redis,
    payload: SignupIngressPayload,
    tenant_id: uuid.UUID,
    actor: str,
    audit_action: str,
) -> SignupServiceResult:
    """Run the Embedded Signup post-flow and write an audit row.

    Maps Meta failures to HTTP codes the caller can act on:

    - ``400`` — bad ``code`` (TokenExchangeError) or Meta rejected register
      / subscribed_apps with a 4xx.
    - ``502`` — Meta unreachable or transient 5xx after retries.

    ``tenant_id`` MUST be the tenant already scoped onto ``session`` — the
    caller enforces that the tenant comes from a trusted source (URL path /
    partner mapping), never from the request body.
    """
    settings = get_settings()
    client = build_meta_client()
    orchestrator = EmbeddedSignupOrchestrator(
        session=session,
        redis=redis,
        client=client,
        app_id=settings.meta_app_id,
        webhook_callback_url=settings.meta_webhook_callback_url,
        webhook_verify_token=settings.meta_webhook_verify_token,
    )
    try:
        result = await orchestrator.complete(payload)
    except TokenExchangeError as exc:
        log.warning("meta.signup.code_exchange_failed", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Meta rechazó el OAuth code — probablemente expiró o ya fue "
                "consumido. El cliente debe repetir el flow desde la app."
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

    audit = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        action=audit_action,
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
        action=audit_action,
    )
    return SignupServiceResult(result=result, audit_log_id=audit.id)


__all__ = ["SignupServiceResult", "build_meta_client", "complete_meta_signup"]
