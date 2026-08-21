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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import (
    _current_tenant,
    apply_tenant_to_session,
)
from nexus_api.db.models import (
    AgentSale,
    AuditLog,
    BillingPlan,
    Channel,
    Partner,
    Tenant,
    TenantPlan,
    TenantStatus,
    TenantTier,
)
from nexus_api.repositories import AuditRepository, ChannelRepository, TenantRepository
from nexus_api.schemas.billing import (
    TenantBillingOut,
    TenantBillingUpdateIn,
)
from nexus_api.schemas.tenant import (
    ChannelOut,
    ChannelRoleIn,
    SlugAvailabilityOut,
    TenantCreateIn,
    TenantOut,
    TenantUpdateIn,
)
from nexus_api.services.channel_routing import channel_agent_enabled, channel_role
from nexus_api.services.tenant_lifecycle import TenantDeleteBlocked, hard_delete_tenant

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
        "tier": t.tier.value,
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
    if "tier" in payload:
        tenant.tier = TenantTier(payload["tier"])
        # WP-10: the webhook caches the tier for stream routing — flush it so
        # the new tier applies on the next message, not one TTL later.
        from nexus_api.core.redis_client import get_redis
        from nexus_api.core.tenant_resolver import invalidate_tenant_tier_cache

        await invalidate_tenant_tier_cache(get_redis(), tenant_id)
    if "market" in payload:
        tenant.market = payload["market"]
    if "timezone" in payload:
        tenant.timezone = payload["timezone"]
        # The worker caches the tenant's timezone on the AgentBundle (it is
        # what renders "today" into every turn) and that cache is invalidated
        # only by the promote channel. Without this publish the agent would
        # keep resolving "hoy" in the OLD timezone until the next promote or
        # restart — silently, which is the failure mode this whole change
        # exists to remove.
        from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
        from nexus_api.core.redis_client import get_redis

        try:
            await get_redis().publish(PROMOTE_CHANNEL, str(tenant_id))
        except Exception as exc:  # stale-cache risk only, never fail the write
            log.warning(
                "tenant.timezone_invalidate_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
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
    via PUT status='active'. Delete is NOT reversible.

    **El borrado lo hace el esquema** (0077), no este handler. Antes había
    aquí una limpieza a mano de ``tenant_connectors`` y
    ``tenant_connector_tool_overrides``, los dos únicos hijos con FK
    RESTRICT que alguien se había acordado de tocar; el resto —bajas de
    contacto, difusiones, el mapeo de partner— seguía bloqueando el
    borrado con un 502 ilegible, y `agent_sales`, `usage_records` y
    `embed_audit_log` se quedaban huérfanos sin decir nada. Con las FKs
    puestas, todo eso cascadea solo y este handler se queda con las dos
    cosas que un esquema no puede decidir:

    1. **Qué NO se borra**: una factura emitida tiene obligación legal de
       conservación (RGPD art. 17.3.b la excluye del derecho de
       supresión), así que su FK sigue en RESTRICT y aquí se comprueba
       ANTES para responder 409 explicando qué hay que resolver, en vez
       de dejar que Postgres lo rechace y devolver un 502.
    2. **Qué se anonimiza en vez de borrarse**: la traza de auditoría
       sobrevive sin tenant y sin payloads. El derecho de supresión pide
       quitar los datos personales, no destruir el registro de quién hizo
       qué — y con el CASCADE anterior se perdía entera, incluida la fila
       que registraba este mismo borrado.

    Los checkpoints de LangGraph se borran explícitamente: sus tablas las
    crea y recrea la librería, así que ponerles una FK nuestra es una
    carrera que perderíamos en el siguiente ``setup()``.
    """
    repo = TenantRepository(session)
    tenant = await repo.get(tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {tenant_id} not found",
        )
    # Shared with the partner console (CP-09): ``services/tenant_lifecycle``
    # holds the archive-first guard, the invoice RESTRICT check, the audit
    # anonymisation and the LangGraph checkpoint sweep.
    try:
        await hard_delete_tenant(session, tenant, actor=f"admin:{actor[:8]}")
    except TenantDeleteBlocked as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
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


@router.patch(
    "/tenants/{tenant_id}/channels/{channel_id}",
    response_model=ChannelOut,
)
async def update_tenant_channel_role(
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    body: ChannelRoleIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> ChannelOut:
    """Assign what a WhatsApp number is for.

    Two independent flags, both living in ``channels.config``:

    - ``role`` — which number a business-initiated send leaves from. A tenant
      with two active numbers and no ``notifications`` role gets a refusal
      rather than a guess, so this is what unblocks broadcasts and cobranza
      reminders for a multi-number client.
    - ``agent_enabled`` — whether inbound on this number reaches the agent.
      ``false`` makes it a pure notifications line: replies are still stored
      and visible here, but nothing answers them and no read receipt is sent.

    They are deliberately separate. A business can legitimately want its
    notifications line to answer too; collapsing them would make that
    unexpressable.

    Both are optional — an omitted field is left untouched, and passing
    ``role: null`` clears it back to the pre-roles behaviour.
    """
    channel = await ChannelRepository(session).get(channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")

    before = {
        "role": channel_role(channel),
        "agent_enabled": channel_agent_enabled(channel),
    }
    # Rebind the whole dict: SQLAlchemy does not track in-place JSONB mutation,
    # so mutating ``channel.config`` would flush nothing.
    config = dict(channel.config or {})
    fields = body.model_dump(exclude_unset=True)
    if "role" in fields:
        if fields["role"] is None:
            config.pop("role", None)
        else:
            config["role"] = fields["role"]
    if "agent_enabled" in fields:
        config["agent_enabled"] = bool(fields["agent_enabled"])
    channel.config = config
    await session.flush()
    # ``updated_at`` carries an onupdate, so the flush expires it. Refresh
    # while we are still in async context — serialising the response would
    # otherwise trigger a lazy load from the sync validator and blow up with
    # MissingGreenlet.
    await session.refresh(channel)

    after = {
        "role": channel_role(channel),
        "agent_enabled": channel_agent_enabled(channel),
    }
    if before != after:
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=actor,
                action="channel.role_changed",
                target=f"channel:{channel_id}",
                before_json=before,
                after_json=after,
            )
        )
        log.info(
            "channel.role_changed",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            identifier=channel.provider_identifier,
            before=before,
            after=after,
        )
    return ChannelOut.model_validate(channel)


# Reference Channel so mypy doesn't drop the import when only used through
# ChannelOut.model_validate; the type is read off the SQLAlchemy row above.
_ = Channel


# ── billing (Facturación tab) ───────────────────────────────────────────────


async def _billing_view(session: AsyncSession, tenant: Tenant) -> TenantBillingOut:
    """Resolve a tenant's billing config (partner + plan) for the panel."""
    partner_name: str | None = None
    if tenant.partner_id is not None:
        partner_name = await session.scalar(
            sa.select(Partner.name).where(Partner.id == tenant.partner_id)
        )
    plan_name: str | None = None
    plan_amount: int | None = None
    if tenant.billing_plan_id is not None:
        row = (
            await session.execute(
                sa.select(BillingPlan.name, BillingPlan.monthly_amount_cents).where(
                    BillingPlan.id == tenant.billing_plan_id
                )
            )
        ).first()
        if row is not None:
            plan_name, plan_amount = row

    if tenant.billing_plan_id is not None:
        model = "subscription"
        effective = (
            tenant.price_override_cents if tenant.price_override_cents is not None else plan_amount
        )
    else:
        has_sales = await session.scalar(sa.select(AgentSale.id).limit(1)) is not None
        model = "commission" if has_sales else "inactive"
        effective = None

    return TenantBillingOut(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        partner_id=tenant.partner_id,
        partner_name=partner_name,
        billing_plan_id=tenant.billing_plan_id,
        plan_name=plan_name,
        plan_amount_cents=plan_amount,
        price_override_cents=tenant.price_override_cents,
        billing_effective_from=tenant.billing_effective_from,
        effective_monthly_cents=effective,
        model=model,
    )


@router.get("/tenants/{tenant_id}/billing", response_model=TenantBillingOut)
async def get_tenant_billing(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> TenantBillingOut:
    tenant = await TenantRepository(session).get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"tenant {tenant_id} not found")
    return await _billing_view(session, tenant)


@router.put("/tenants/{tenant_id}/billing", response_model=TenantBillingOut)
async def update_tenant_billing(
    tenant_id: uuid.UUID,
    body: TenantBillingUpdateIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> TenantBillingOut:
    """Set a tenant's partner / plan / price override / start date. PATCH
    semantics — only fields present in the body change; send ``null`` to
    clear one (e.g. detach the partner)."""
    tenant = await TenantRepository(session).get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"tenant {tenant_id} not found")

    payload = body.model_dump(exclude_unset=True)

    if "partner_id" in payload:
        pid = payload["partner_id"]
        if pid is not None and not await session.scalar(
            sa.select(Partner.id).where(Partner.id == pid)
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"partner {pid} not found")
        tenant.partner_id = pid
    if "billing_plan_id" in payload:
        plan_id = payload["billing_plan_id"]
        if plan_id is not None and not await session.scalar(
            sa.select(BillingPlan.id).where(BillingPlan.id == plan_id)
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"billing plan {plan_id} not found"
            )
        tenant.billing_plan_id = plan_id
    if "price_override_cents" in payload:
        tenant.price_override_cents = payload["price_override_cents"]
    if "billing_effective_from" in payload:
        tenant.billing_effective_from = payload["billing_effective_from"]

    await session.flush()
    log.info(
        "tenant.billing_updated",
        tenant_id=str(tenant_id),
        partner_id=str(tenant.partner_id) if tenant.partner_id else None,
        billing_plan_id=str(tenant.billing_plan_id) if tenant.billing_plan_id else None,
        price_override_cents=tenant.price_override_cents,
    )
    return await _billing_view(session, tenant)
