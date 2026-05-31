"""Public-facing connector endpoints.

These are NOT under /admin because:

- ``POST /connectors/composio-webhook`` is hit by Composio's outbound
  webhook delivery (HMAC-signed). Composio doesn't know our admin Bearer.
- ``GET /connectors/oauth-callback`` is hit by the tenant owner's browser
  after they consent on the provider's OAuth page. We verify origin via
  the ``consent_token`` query parameter we minted ourselves; the user is
  not authenticated to Auphere at all.

Both paths apply security at the message level (HMAC for webhook, HMAC
signed token for callback) — no session, no bearer.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.connectors import get_composio_client
from nexus_api.api.deps import get_db_session
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import TenantConnector
from nexus_api.services.connectors.composio_client import (
    ComposioClientProtocol,
    verify_composio_webhook,
)
from nexus_api.services.connectors.consent_token import (
    ConsentTokenExpired,
    ConsentTokenInvalid,
    verify_consent_token,
)
from nexus_api.services.connectors.service import complete_consent_from_webhook

log = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/connectors/composio-webhook")
async def composio_webhook(
    request: Request,
    composio: ComposioClientProtocol = Depends(get_composio_client),
    webhook_id: str = Header("", alias="webhook-id"),
    webhook_timestamp: str = Header("", alias="webhook-timestamp"),
    webhook_signature: str = Header("", alias="webhook-signature"),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Receive Composio lifecycle events for connected_accounts.

    Composio uses the Standard Webhooks scheme (Svix-style). Headers:
    ``webhook-id`` / ``webhook-timestamp`` / ``webhook-signature``. Body
    contains ``data`` with ``connection_id`` and the upstream ``status``.

    Flow:
    1. HMAC verify with NEXUS_COMPOSIO_WEBHOOK_SECRET.
    2. Look up the tenant_connector by ``credentials_ref.composio_connection_id``
       with row_security OFF (we don't know tenant_id yet).
    3. Open a tenant-scoped transaction and apply the event.
    """
    settings = get_settings()
    body_bytes = await request.body()
    body = body_bytes.decode("utf-8")
    try:
        verify_composio_webhook(
            webhook_id=webhook_id,
            webhook_timestamp=webhook_timestamp,
            body=body,
            signature_header=webhook_signature,
            secret=settings.composio_webhook_secret,
        )
    except ValueError as exc:
        log.warning("composio_webhook.signature_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="webhook signature invalid",
        ) from exc

    import json

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="malformed JSON") from exc

    data = payload.get("data") or {}
    connection_id = data.get("connection_id") or data.get("id")
    upstream_status = (data.get("status") or payload.get("type", "").split(".")[-1]).upper()
    granted_scopes = data.get("granted_scopes") or data.get("scopes") or []
    if not connection_id:
        raise HTTPException(status_code=400, detail="payload missing connection_id")

    # Resolve tenant_id with RLS off — same pattern as resolve_channel_tenant
    # in the webhook YCloud path. We capture the tenant_id, then turn row_security
    # back ON before switching to the non-superuser role; otherwise PG raises
    # ``query would be affected by row-level security policy`` for the
    # subsequent queries (nexus_app can't bypass RLS, so row_security=off is
    # not legal for it).
    await session.execute(text("SET LOCAL row_security = off"))
    tc_row = await session.scalar(
        select(TenantConnector).where(
            TenantConnector.credentials_ref["composio_connection_id"].astext == connection_id
        )
    )
    if tc_row is None:
        log.info(
            "composio_webhook.unknown_connection",
            connection_id=connection_id,
        )
        # Composio doesn't retry on our 200 — but a 404 might trigger retries.
        # Return 200 to avoid the storm; we logged it.
        return {"status": "ignored", "reason": "unknown_connection_id"}

    tenant_id = tc_row.tenant_id
    await session.execute(text("SET LOCAL row_security = on"))
    await apply_tenant_to_session(session, tenant_id)
    # tenant_context sets the contextvar the repositories read — the SQL
    # GUC from apply_tenant_to_session is not enough once complete_consent
    # fans out to AgentConfigService (auto_enable_connector_tools).
    with tenant_context(tenant_id):
        result = await complete_consent_from_webhook(
            session,
            composio_connection_id=connection_id,
            upstream_status=upstream_status,
            granted_scopes=list(granted_scopes),
            composio=composio,
        )
    await session.commit()
    return {
        "status": "ok",
        "upstream_status": upstream_status,
        "tools_added": str(len(result.tools_added) if result else 0),
    }


@router.get("/connectors/oauth-callback", response_class=HTMLResponse)
async def oauth_callback(
    request: Request,
    consent_token: str = "",
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    """Land the tenant owner here after they consent on the provider's page.

    We do NOT exchange code here — Composio does that side internally and
    fires the webhook. Our only job is to render a friendly "you're set"
    page (or "this link expired" page if the consent_token is bad).

    The consent_token in the query string proves the user came from a link
    we minted. Without it (or with a tampered/expired one) we still render
    a generic landing page — never an error that leaks info.
    """
    settings = get_settings()
    success = False
    if consent_token:
        try:
            verify_consent_token(
                token=consent_token,
                secret=settings.connector_consent_secret,
            )
            success = True
        except (ConsentTokenInvalid, ConsentTokenExpired) as exc:
            log.info("oauth_callback.token_check_failed", error=str(exc))
    # The webhook has likely already arrived; this page is purely UX.
    html = _SUCCESS_PAGE if success else _GENERIC_PAGE
    return HTMLResponse(content=html, status_code=200)


_SUCCESS_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Conexión establecida — Auphere</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
           max-width: 480px; margin: 80px auto; padding: 0 24px; color: #0a0a0a;
           background: #fafafa; line-height: 1.55; }
    .ok { display: inline-block; width: 56px; height: 56px; border-radius: 999px;
          background: #2CC295; color: white; line-height: 56px; text-align: center;
          font-size: 28px; margin-bottom: 16px; }
    h1 { font-size: 22px; margin: 0 0 8px; letter-spacing: -0.01em; }
    p { color: #525252; }
    .small { font-size: 13px; color: #737373; margin-top: 32px; }
  </style>
</head>
<body>
  <div class="ok">✓</div>
  <h1>Conexión establecida</h1>
  <p>Tu agente ya puede acceder al servicio que acabas de autorizar. Puedes
     cerrar esta ventana.</p>
  <p class="small">Si tienes dudas, contacta al equipo de Auphere.</p>
</body>
</html>
"""

_GENERIC_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Auphere</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
           max-width: 480px; margin: 80px auto; padding: 0 24px; color: #0a0a0a;
           background: #fafafa; line-height: 1.55; }
    h1 { font-size: 22px; margin: 0 0 8px; letter-spacing: -0.01em; }
    p { color: #525252; }
  </style>
</head>
<body>
  <h1>Auphere</h1>
  <p>Si llegaste aquí después de autorizar un servicio para tu agente, ya
     deberías ver el connector como conectado. Si no, contacta al equipo.</p>
</body>
</html>
"""


__all__ = ["router"]
