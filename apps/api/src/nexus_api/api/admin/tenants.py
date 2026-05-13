"""Admin endpoints for tenant CRUD (Block B + J).

Block B shipped GET list + GET by id. Block J adds the wizard endpoints:

- ``GET  /admin/tenants/check-slug?slug=...`` — async uniqueness probe used
  by the wizard form (debounced) so Lee sees red/green before submit.
  Returns ``{slug, available}``. Backstop is the DB UNIQUE constraint on
  ``tenants.slug`` which produces a 409 on the POST below.
- ``POST /admin/tenants`` — creates a row with ACTIVE status, RLS-scoped
  audit row recorded under the new tenant's id.
- ``PUT  /admin/tenants/:id`` — partial update; audit row captures
  before/after for every changed field.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import (
    _current_tenant,
    apply_tenant_to_session,
)
from nexus_api.db.models import (
    AuditLog,
    Channel,
    Tenant,
    TenantConnector,
    TenantConnectorToolOverride,
    TenantPlan,
    TenantStatus,
)
from nexus_api.repositories import AuditRepository, ChannelRepository, TenantRepository
from nexus_api.schemas.tenant import (
    ChannelOut,
    SlugAvailabilityOut,
    TenantCreateIn,
    TenantOut,
    TenantUpdateIn,
)

router = APIRouter()
log = structlog.get_logger()


# ── helpers ────────────────────────────────────────────────────────────────


def _diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (before_changed, after_changed) — only fields that actually changed.

    Mirrors the audit_log convention used elsewhere (integrations.py): we
    record what shifted, not the whole row.
    """
    b: dict[str, Any] = {}
    a: dict[str, Any] = {}
    for key, new in after.items():
        old = before.get(key)
        if old != new:
            b[key] = old
            a[key] = new
    return b, a


def _tenant_to_dict(t: Tenant) -> dict[str, Any]:
    return {
        "name": t.name,
        "slug": t.slug,
        "plan": t.plan.value,
        "status": t.status.value,
        "market": t.market,
        "timezone": t.timezone,
        "owner_email": t.owner_email,
        "owner_phone": t.owner_phone,
        "business_hours": t.business_hours,
        "cost_alert_threshold_usd_per_day": str(t.cost_alert_threshold_usd_per_day),
    }


# ── endpoints ──────────────────────────────────────────────────────────────


@router.get(
    "/tenants",
    response_model=list[TenantOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_tenants(
    session: AsyncSession = Depends(get_db_session),
) -> list[TenantOut]:
    repo = TenantRepository(session)
    return [TenantOut.model_validate(t) for t in await repo.list_all()]


@router.get(
    "/tenants/check-slug",
    response_model=SlugAvailabilityOut,
    dependencies=[Depends(require_admin_token)],
)
async def check_slug(
    slug: str = Query(..., min_length=2, max_length=80),
    session: AsyncSession = Depends(get_db_session),
) -> SlugAvailabilityOut:
    """Async uniqueness check used by the wizard. The backstop is the DB
    UNIQUE constraint — this endpoint just gives the form fast feedback."""
    repo = TenantRepository(session)
    return SlugAvailabilityOut(slug=slug, available=not await repo.slug_taken(slug))


@router.post(
    "/tenants",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    body: TenantCreateIn,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
) -> TenantOut:
    """Create a tenant with ACTIVE status. The audit_log row is written
    inside RLS scope under the new tenant's id."""
    repo = TenantRepository(session)
    async with session.begin():
        if await repo.slug_taken(body.slug):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"slug {body.slug!r} is already taken",
            )
        tenant = Tenant(
            id=uuid.uuid4(),
            name=body.name,
            slug=body.slug,
            plan=TenantPlan(body.plan),
            status=TenantStatus.ACTIVE,
            market=body.market,
            timezone=body.timezone,
            owner_email=body.owner_email,
            owner_phone=body.owner_phone,
            business_hours=body.business_hours,
            cost_alert_threshold_usd_per_day=body.cost_alert_threshold_usd_per_day,
        )
        try:
            await repo.create(tenant)
        except IntegrityError as exc:
            # Race against another in-flight POST with the same slug. The
            # async check above lost — rare but possible.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"slug {body.slug!r} is already taken",
            ) from exc
        # Switch to tenant scope on this transaction so the audit_log row is
        # written via RLS-aware repos. set_config + SET LOCAL ROLE are
        # transaction-bound; the contextvar bridge mirrors what
        # scoped_session_from_path does for path-based endpoints.
        token = _current_tenant.set(tenant.id)
        try:
            await apply_tenant_to_session(session, tenant.id)
            await AuditRepository(session).record(
                actor=f"admin:{actor[:8]}",
                action="tenant.create",
                target=f"tenant:{tenant.id}",
                before=None,
                after=_tenant_to_dict(tenant),
            )
        finally:
            _current_tenant.reset(token)
    await session.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.get(
    "/tenants/{tenant_id}",
    response_model=TenantOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> TenantOut:
    repo = TenantRepository(session)
    tenant = await repo.get(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"tenant {tenant_id} not found"
        )
    return TenantOut.model_validate(tenant)


@router.put(
    "/tenants/{tenant_id}",
    response_model=TenantOut,
)
async def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdateIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TenantOut:
    """Partial update — only fields actually present in the body change.
    Audit captures before/after for every changed field."""
    tenant = await TenantRepository(session).get(tenant_id)
    if tenant is None:
        # ``scoped_session_from_path`` already 404s if the path doesn't
        # exist; this is defensive in case of a race with an archive.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"tenant {tenant_id} not found"
        )

    before_state = _tenant_to_dict(tenant)
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        # Nothing to change. 200 with current state — the wizard's edit form
        # may submit unchanged values; treating as no-op simplifies the UI.
        return TenantOut.model_validate(tenant)

    if "name" in payload:
        tenant.name = payload["name"]
    if "plan" in payload:
        tenant.plan = TenantPlan(payload["plan"])
    if "status" in payload:
        tenant.status = TenantStatus(payload["status"])
    if "market" in payload:
        tenant.market = payload["market"]
    if "timezone" in payload:
        tenant.timezone = payload["timezone"]
    if "owner_email" in payload:
        tenant.owner_email = payload["owner_email"]
    if "owner_phone" in payload:
        tenant.owner_phone = payload["owner_phone"]
    if "business_hours" in payload:
        tenant.business_hours = payload["business_hours"]
    if "cost_alert_threshold_usd_per_day" in payload:
        tenant.cost_alert_threshold_usd_per_day = Decimal(
            str(payload["cost_alert_threshold_usd_per_day"])
        )

    after_state = _tenant_to_dict(tenant)
    before_changed, after_changed = _diff(before_state, after_state)
    if before_changed:
        audit = AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action="tenant.update",
            target=f"tenant:{tenant_id}",
            before_json=before_changed,
            after_json=after_changed,
        )
        session.add(audit)
        await session.flush()
        # `updated_at` has ``onupdate=now()`` server-side — refresh so the
        # response carries the new timestamp instead of triggering a lazy
        # load after the dependency closes its transaction.
        await session.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.delete(
    "/tenants/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> None:
    """Hard-delete a tenant. Guard: tenant must be ARCHIVED first.

    The two-step (archive → delete) is intentional. Archive is reversible
    via PUT status='active'. Delete is NOT reversible. The audit row is
    written BEFORE the cascade so the audit trail survives the row
    removal — it's stored under ``tenant_id`` so RLS pins it under the
    same tenant; once the tenant row is gone, the audit row is orphaned
    by FK CASCADE and removed too. For long-term provenance we rely on
    Langfuse + the structlog event.

    Cleanup order (the 2026-05-13 review caught HTTP 500 here):
    ``tenant_connectors`` and ``tenant_connector_tool_overrides`` carry
    ``ON DELETE RESTRICT`` FKs to ``tenants.id`` (block L deliberately
    chose RESTRICT so an operator can't accidentally wipe live OAuth
    grants by deleting the wrong tenant). The two-step archive→delete
    workflow is the explicit confirmation, so once we get here we
    detach those rows ourselves before the tenant goes — otherwise
    Postgres raises a ForeignKeyViolation that surfaced as a bare
    HTTP 500 to the operator. A migration to flip the FKs to CASCADE
    is the durable fix; this endpoint cleanup is the resilient one.
    """
    repo = TenantRepository(session)
    tenant = await repo.get(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {tenant_id} not found",
        )
    if tenant.status is not TenantStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("tenant must be archived before delete; PATCH status='archived' first"),
        )
    snapshot = _tenant_to_dict(tenant)
    log.warning(
        "tenant.delete.cascade",
        tenant_id=str(tenant_id),
        slug=tenant.slug,
        actor=actor[:8],
    )
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action="tenant.delete",
            target=f"tenant:{tenant_id}",
            before_json=snapshot,
            after_json=None,
        )
    )
    await session.flush()

    # Detach the two RESTRICT-FK children before the tenant goes. RLS is
    # already scoped to this tenant via ``scoped_session_from_path``, so
    # the bulk deletes are bounded — the explicit WHERE is belt-and-
    # suspenders for clarity and for the eventual day RLS gets relaxed
    # for an admin-bypass role.
    overrides_result = await session.execute(
        sa.delete(TenantConnectorToolOverride).where(
            TenantConnectorToolOverride.tenant_id == tenant_id
        )
    )
    connectors_result = await session.execute(
        sa.delete(TenantConnector).where(TenantConnector.tenant_id == tenant_id)
    )
    log.info(
        "tenant.delete.cleanup",
        tenant_id=str(tenant_id),
        tenant_connectors=connectors_result.rowcount,  # type: ignore[attr-defined]
        tool_overrides=overrides_result.rowcount,  # type: ignore[attr-defined]
    )

    try:
        await session.delete(tenant)
        await session.flush()
    except SQLAlchemyError as exc:
        # Any remaining FK violation, RLS-blocked cascade or similar
        # surfaces here. The 500 -> 502 conversion mirrors what we did
        # for the sandbox endpoint (P0-1 review fix): give the operator
        # something they can read in the toast instead of "HTTP 500".
        log.exception(
            "tenant.delete.failed",
            tenant_id=str(tenant_id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(f"no se pudo eliminar el tenant: {type(exc).__name__} — {exc}"),
        ) from exc
    # The outer dependency commits when the response leaves the handler;
    # an explicit commit here used to clash with that block (it tried to
    # close a transaction the ``async with session.begin():`` in
    # ``scoped_session_from_path`` was still managing).


@router.get(
    "/tenants/{tenant_id}/channels",
    response_model=list[ChannelOut],
)
async def list_tenant_channels(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> list[ChannelOut]:
    """List channels for a tenant — used by the integrations page to
    surface ``Conectado / Sin conectar`` for each provider."""
    channels = await ChannelRepository(session).list_all()
    return [ChannelOut.model_validate(c) for c in channels]


# Reference Channel so mypy doesn't drop the import when only used through
# ChannelOut.model_validate; the type is read off the SQLAlchemy row above.
_ = Channel
