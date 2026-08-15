"""``/console/clients`` — a partner's clients (= tenants), by
``external_client_ref``.

List, detail with health, creation through the SAME code path as the
partner API (``services/partner_clients.py`` — idempotent, quota-checked,
blueprint), rename, lifecycle transitions and the irreversible delete on
top of WP-29 (archive first, cascade, anonymised audit).

Nothing here takes a tenant id. The list is built FROM ``partner_tenants``
under the principal's partner; every ``{ref}`` route goes through
:func:`client_scope`, which resolves the tenant the only sanctioned way and
opens the RLS-scoped transaction.
"""

from __future__ import annotations

from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.schemas.partner import ClientAgentIn, ClientProvisionIn
from nexus_api.services.partner_clients import (
    ProvisioningFailed,
    ProvisioningQuotaExceeded,
    provision_partner_client,
)
from nexus_api.services.tenant_lifecycle import TenantDeleteBlocked, hard_delete_tenant

from .deps import ClientScope, client_health, client_scope, health_for_tenant
from .me import quota_out
from .schemas import (
    ClientCreateIn,
    ClientCreateOut,
    ClientDeleteIn,
    ClientOut,
    ClientPageOut,
    ClientStatusIn,
    ClientSummaryOut,
    ClientUpdateIn,
)

router = APIRouter(prefix="/clients")

_SORTABLE = {
    "created_at": Tenant.created_at,
    "updated_at": Tenant.updated_at,
    "name": Tenant.name,
    "status": Tenant.status,
}


def _summary(mapping: PartnerTenant, tenant: Tenant) -> ClientSummaryOut:
    return ClientSummaryOut(
        external_client_ref=mapping.external_client_ref,
        name=tenant.name,
        status=tenant.status.value,
        timezone=tenant.timezone,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


# ── list / create ──────────────────────────────────────────────────────


@router.get("", response_model=ClientPageOut)
async def list_clients(
    principal: ConsolePrincipal = Depends(require_console_principal("clients:read")),
    session: AsyncSession = Depends(get_db_session),
    q: str | None = Query(default=None, max_length=120, description="Search name or ref"),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    sort: Literal["created_at", "updated_at", "name", "status"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ClientPageOut:
    """The partner's clients. Search, status filter, sort and offset paging.
    Bounded by ``partner_tenants.partner_id = <principal's partner>`` — the
    query cannot express another partner."""
    base = (
        sa.select(PartnerTenant, Tenant)
        .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
        .where(PartnerTenant.partner_id == principal.partner.id)
    )
    if q:
        needle = f"%{q.strip()}%"
        base = base.where(
            sa.or_(
                Tenant.name.ilike(needle),
                PartnerTenant.external_client_ref.ilike(needle),
                PartnerTenant.client_name.ilike(needle),
            )
        )
    if status_filter:
        try:
            wanted = TenantStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown status {status_filter!r}",
            ) from None
        base = base.where(Tenant.status == wanted)

    column = _SORTABLE[sort]
    ordering = column.asc() if order == "asc" else column.desc()
    async with session.begin():
        total = await session.scalar(sa.select(sa.func.count()).select_from(base.subquery()))
        rows = (
            await session.execute(
                base.order_by(ordering, PartnerTenant.external_client_ref)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    return ClientPageOut(
        items=[_summary(mapping, tenant) for mapping, tenant in rows],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ClientCreateOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Client quota reached — nothing was created."},
        422: {"description": "The partner's blueprint failed to provision the client."},
    },
)
async def create_client(
    body: ClientCreateIn,
    request: Request,
    principal: ConsolePrincipal = Depends(require_console_principal("clients:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ClientCreateOut:
    """Same semantics as ``POST /v2/partners/clients``: idempotent on the
    ref, quota checked before anything is written (CP-06)."""
    provision_in = ClientProvisionIn(
        external_client_ref=body.external_client_ref,
        name=body.name,
        timezone=body.timezone,
        agent=ClientAgentIn(placeholders=body.placeholders) if body.placeholders else None,
        connector=None,
    )
    try:
        out = await provision_partner_client(
            session,
            redis,
            partner=principal.partner,
            body=provision_in,
            api_key_id=None,
            actor=principal.actor,
            ip=request.client.host if request.client else None,
        )
    except ProvisioningQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ProvisioningFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ClientCreateOut(
        external_client_ref=out.external_client_ref,
        status=out.status,
        agent_status=out.agent.status,
        whatsapp_connected=out.whatsapp.status == "connected",
        quota=await quota_out(session, principal),
    )


# ── detail / update / lifecycle ────────────────────────────────────────


@router.get("/{ref}", response_model=ClientOut)
async def get_client(scope: ClientScope = Depends(client_scope("clients:read"))) -> ClientOut:
    health = await client_health(scope.session, scope.tenant)
    return ClientOut(**_summary(scope.mapping, scope.tenant).model_dump(), health=health)


@router.patch("/{ref}", response_model=ClientOut)
async def update_client(
    body: ClientUpdateIn,
    scope: ClientScope = Depends(client_scope("clients:write")),
) -> ClientOut:
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(scope.tenant, k) for k in changes}
    for key, value in changes.items():
        setattr(scope.tenant, key, value)
    if "name" in changes:
        scope.mapping.client_name = changes["name"]
    if changes and any(before[k] != changes[k] for k in changes):
        scope.session.add(
            AuditLog(
                tenant_id=scope.tenant.id,
                actor=scope.principal.actor,
                action="console.client.update",
                target=f"tenant:{scope.tenant.id}",
                before_json=before,
                after_json=changes,
            )
        )
    await scope.session.flush()
    # ``updated_at`` is a server-side ``onupdate``: reload before serialising.
    await scope.session.refresh(scope.tenant)
    health = await client_health(scope.session, scope.tenant)
    return ClientOut(**_summary(scope.mapping, scope.tenant).model_dump(), health=health)


_ALLOWED: dict[TenantStatus, set[str]] = {
    TenantStatus.PROVISIONING: {"active", "archived"},
    TenantStatus.ACTIVE: {"paused", "archived"},
    TenantStatus.PAUSED: {"active", "archived"},
    TenantStatus.ARCHIVED: {"active", "paused"},
}


@router.post(
    "/{ref}/status",
    response_model=ClientOut,
    responses={409: {"description": "Transition not allowed from the current status."}},
)
async def set_client_status(
    body: ClientStatusIn,
    scope: ClientScope = Depends(client_scope("clients:write")),
) -> ClientOut:
    """Suspend / reactivate / archive. Reversible; only delete is not.
    Activating a client that is still provisioning requires an active
    agent version — otherwise there is nothing to serve."""
    current = scope.tenant.status
    if body.status == current.value:
        health = await client_health(scope.session, scope.tenant)
        return ClientOut(**_summary(scope.mapping, scope.tenant).model_dump(), health=health)
    if body.status not in _ALLOWED[current]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot move a {current.value} client to {body.status}",
        )
    if body.status == "active" and current is TenantStatus.PROVISIONING:
        has_agent = await scope.session.scalar(
            sa.select(AgentConfig.id).where(AgentConfig.status == AgentConfigStatus.ACTIVE).limit(1)
        )
        if has_agent is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="publish an agent version before activating the client",
            )
    scope.tenant.status = TenantStatus(body.status)
    scope.session.add(
        AuditLog(
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            action="console.client.status",
            target=f"tenant:{scope.tenant.id}",
            before_json={"status": current.value},
            after_json={"status": body.status},
        )
    )
    await scope.session.flush()
    # ``updated_at`` is a server-side ``onupdate``: reload before serialising.
    await scope.session.refresh(scope.tenant)
    health = await client_health(scope.session, scope.tenant)
    return ClientOut(**_summary(scope.mapping, scope.tenant).model_dump(), health=health)


@router.delete(
    "/{ref}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        409: {"description": "Not archived, name mismatch, or invoices retained by law."},
    },
)
async def delete_client(
    body: ClientDeleteIn,
    scope: ClientScope = Depends(client_scope("clients:delete")),
) -> Response:
    """Irreversible. The partner types the client's name (``confirm_name``)
    and the client must already be archived (WP-29 two-step)."""
    if body.confirm_name.strip() != scope.tenant.name.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="confirm_name does not match the client's name",
        )
    try:
        await hard_delete_tenant(scope.session, scope.tenant, actor=scope.principal.actor)
    except TenantDeleteBlocked as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Re-exported for the list's health lookups (kept here so the deps module
# stays free of route knowledge).
__all__ = ["health_for_tenant", "router"]
