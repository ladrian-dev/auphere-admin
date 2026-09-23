"""``/console/clients/{ref}/integrations/*`` — spec 016 (R6).

AgendaPro has no OAuth and no API key: what the runtime needs is the
client's **public booking page** (``tenants.agendapro_public_url``), the
same column the operator panel sets. The partner links it here; nothing
secret is typed or stored, and the ``booking.*`` tools (native, no
connector row) run against that page.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status

from nexus_api.db.models import AuditLog

from .deps import ClientScope, client_scope
from .schemas_agent_tools import AgendaProPublicUrlIn, AgendaProPublicUrlOut

router = APIRouter(prefix="/clients/{ref}/integrations")

AGENDAPRO_DOMAIN = "agendapro.com"


def _invalid(reason: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "invalid_url", "reason": reason},
    )


def normalize_agendapro_url(raw: str | None) -> str | None:
    """``None`` when empty; otherwise an ``https`` URL on an AgendaPro host.

    The runtime scrapes this page, so a typo here is a booking that never
    happens: it is rejected now, with a reason the screen can name.
    """
    value = (raw or "").strip()
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise _invalid("scheme")
    host = (parts.hostname or "").lower()
    if host != AGENDAPRO_DOMAIN and not host.endswith("." + AGENDAPRO_DOMAIN):
        raise _invalid("host")
    return value


@router.put(
    "/agendapro/public-url",
    response_model=AgendaProPublicUrlOut,
    responses={
        404: {"description": "Unknown client reference."},
        422: {"description": "Not an https URL on agendapro.com (`invalid_url`)."},
    },
)
async def put_agendapro_public_url(
    body: AgendaProPublicUrlIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> AgendaProPublicUrlOut:
    """Link (or unlink) the client's public AgendaPro page."""
    url = normalize_agendapro_url(body.public_url)
    before = scope.tenant.agendapro_public_url
    scope.tenant.agendapro_public_url = url
    scope.session.add(
        AuditLog(
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            action="console.integration.agendapro_url",
            target=f"tenant:{scope.tenant.id}",
            before_json={"public_url": before},
            after_json={"set": url is not None, "public_url": url},
        )
    )
    await scope.session.flush()
    return AgendaProPublicUrlOut(public_url=url, updated_at=datetime.now(UTC))


__all__ = ["AGENDAPRO_DOMAIN", "normalize_agendapro_url", "router"]
