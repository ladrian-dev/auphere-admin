"""Public partner surface: ``/v1/partners/*`` (ADR-028).

Server-to-server only — authenticated with the partner's secret API key
(``core/partner_auth.py``). A ``tenant_id`` is never accepted from the
caller: it is resolved through the ``partner_tenants`` allow-list under
the authenticated partner's id, which is the platform's only sanctioned
way to pick one.

Responses never contain internal tenant ids: the partner speaks
``external_client_ref``, we translate.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.partner_auth import PartnerContext, require_partner_key
from nexus_api.schemas.partner import ClientProvisionIn, ClientProvisionOut
from nexus_api.services.partner_clients import (
    ProvisioningFailed,
    ProvisioningQuotaExceeded,
    client_slug,
    provision_partner_client,
    whatsapp_status,
)

log = structlog.get_logger(__name__)

# Sin versión en el prefijo: la pone ``main.py`` al montarlo, una vez
# por versión viva. Ver ``api/versioning.py``.
router = APIRouter(tags=["partners"])

# Session scopes a widget token carries. ``widget:connect`` is reserved
# for the Phase 2 self-serve signup; shipping it in the claims now keeps
# the token shape stable.
_WIDGET_SCOPES = ["widget:send", "widget:connect"]

# Kept as public names: other modules import them from here.
_client_slug = client_slug
_whatsapp_status = whatsapp_status


@router.post(
    "/partners/clients",
    response_model=ClientProvisionOut,
    status_code=status.HTTP_200_OK,
    responses={
        409: {
            "description": (
                "Cuota de clientes del partner alcanzada (``max_clients``). No se "
                "creó nada; archivar un cliente o pedir a Auphere que amplíe el límite."
            )
        },
        422: {"description": "El blueprint del partner falló al aprovisionar el cliente."},
    },
)
async def provision_client(
    body: ClientProvisionIn,
    request: Request,
    ctx: PartnerContext = Depends(require_partner_key("provision")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ClientProvisionOut:
    """Idempotent: registering the same ``external_client_ref`` twice
    returns the existing mapping. First registration creates the tenant
    just-in-time with status ``provisioning`` (no channel until the
    WhatsApp signup completes).

    Partners configured with a blueprint (``default_seed_template`` /
    ``default_connector_slug``) also get their agent seeded + promoted
    and the connector installed in the same call — see
    ``services/partner_provisioning.py``. Re-provisioning rotates
    connector credentials but never re-seeds an existing agent.

    Since CP-06 the partner's client quota (``partners.max_clients``,
    migration 0081) is checked before anything is created; the client
    ``max_clients + 1`` gets a 409 and nothing is written. The shared
    implementation lives in ``services/partner_clients.py`` — the
    partner console uses the same code path."""
    try:
        return await provision_partner_client(
            session,
            redis,
            partner=ctx.partner,
            body=body,
            api_key_id=ctx.api_key.id,
            actor=f"partner:{ctx.partner.slug}",
            ip=request.client.host if request.client else None,
        )
    except ProvisioningQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ProvisioningFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
