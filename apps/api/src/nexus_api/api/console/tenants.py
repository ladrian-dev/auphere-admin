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

**Spec 047 — the three-field alta** (``contracts/console-api.md`` §2, T048).
``POST /console/clients`` takes two bodies:

- the new console's ``{name, niche, info?, …}`` (:class:`ClientNewIn`): the
  client is born ``active`` with its business profile and **no agent**, even
  when the partner has a default template; if it has a web or networks, the
  background reading starts (``client_read``);
- today's ``{external_client_ref, name, timezone, …}`` (:class:`ClientCreateIn`)
  for partners without the new console: unchanged, through the same code path
  as the partner API.

Plus what the modal needs while the person types —
``POST /clients/link-detection`` (chips and «Más ajustes») and
``GET /clients/niche-suggestions`` — and the reading card:
``GET``/``POST /clients/{ref}/business/read``. The two literal paths are
declared before ``/{ref}`` so they are never read as a client reference.

**Spec 047 — lifecycle, list and Panel** (T063, T065, T067; ``console-api.md``
§2), for partners on the new console (``console_version = "v2"``); today's
console keeps every route and shape it had:

- ``GET /clients?q=&filter=`` answers each row with its niche, its state with
  the reason (the ONE attention rule, ``services/attention.py``), its agents'
  ``visible_state``, its bag (left of assigned, days and percentage) and the
  actions this person may take, ordered attention first and then by days left;
- ``GET /clients/{ref}`` adds what the edit modal shows and the ``revision`` of
  the basics for ``If-Match``; ``PATCH`` writes them through
  ``business/profile_edits.update_basics`` (the IANA zone checked here) and,
  after commit, tells the runtime (``PROMOTE_CHANNEL``) so the agents use the
  new name and zone from the next message;
- ``POST /clients/{ref}/archive`` · ``/restore`` (``tenant_lifecycle``);
- ``GET /clients/{ref}/panel``: the bag, the days at the 7-day pace, the bar by
  agent, the month, the four agents that spend most, the first thing the ficha
  lacks and the reading card (``console_home_blocks`` + ``client_overview``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.billing.pricing import CURRENCY
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import (
    _current_tenant,
    apply_tenant_to_session,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.db.models.business import BusinessProfile
from nexus_api.schemas.partner import ClientAgentIn, ClientProvisionIn
from nexus_api.services import console_home_blocks as blocks
from nexus_api.services import console_v2
from nexus_api.services.agent_audience import count_of
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.agent_lifecycle import VisibleState
from nexus_api.services.attention import Attention, list_order
from nexus_api.services.attention import attention as attention_of
from nexus_api.services.business import reader as business_reader
from nexus_api.services.business import sources as business_sources
from nexus_api.services.business.links import DetectedLink, detect_links, link_from_choice
from nexus_api.services.business.profile import (
    COUNTRIES,
    Deduction,
    deduce_settings,
    eu_by_default,
    fold,
    is_valid_timezone,
    niche_suggestions,
)
from nexus_api.services.business.sections import Actor
from nexus_api.services.client_overview import (
    ClientDetail,
    agent_figures,
    client_facts,
    month_conversations,
    read_client,
    read_clients,
)
from nexus_api.services.client_overview import bags as client_bags
from nexus_api.services.console_notifications import record_client_activation_detached
from nexus_api.services.jobs import enqueue_job
from nexus_api.services.partner_clients import (
    ProvisioningFailed,
    ProvisioningQuotaExceeded,
    provision_partner_client,
)
from nexus_api.services.tenant_lifecycle import (
    UPDATE_ACTION,
    AgentChange,
    LifecycleError,
    NewClient,
    TenantDeleteBlocked,
    archive_client,
    hard_delete_tenant,
    lifecycle_of,
    restore_client,
)
from nexus_api.services.tenant_lifecycle import create_client as create_new_client
from nexus_api.services.tenant_lifecycle import (
    delete_client as delete_client_v2,
)

from .agent_draft_routes import etag, parse_revision
from .deps import (
    ClientRef,
    ClientScope,
    active_customer_channel,
    client_health,
    client_scope,
    client_sector,
    client_setup,
    client_setup_detail,
    health_for_tenant,
    out_of_quota,
    require_build_room,
    resolve_mapping,
    serving_since,
)
from .jobs import job_out
from .me import quota_out
from .schemas import (
    ClientAudienceOut,
    ClientCreateIn,
    ClientCreateOut,
    ClientDeleteIn,
    ClientOut,
    ClientPageOut,
    ClientQuotaOut,
    ClientStatusIn,
    ClientSummaryOut,
    JobAcceptedOut,
)
from .schemas_business import (
    ClientNewIn,
    ClientNewOut,
    ClientReadOut,
    DeducedSettingsOut,
    DetectedLinkOut,
    LinkDetectionIn,
    LinkDetectionOut,
    NicheSuggestionOut,
    NicheSuggestionsOut,
)
from .schemas_clients import (
    AgentLifecycleOut,
    AgentShareOut,
    AgentsSummaryOut,
    AttentionOut,
    AttentionReasonOut,
    BagOut,
    ClientAgentOut,
    ClientCountsOut,
    ClientDetailOut,
    ClientEditIn,
    ClientLifecycleOut,
    ClientListOut,
    ClientListRowOut,
    ClientPanelOut,
    MissingOut,
    MoneyOut,
    MonthOut,
    TopAgentOut,
    VisibleStateOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/clients")

#: Una alta repetida con la misma ``Idempotency-Key`` devuelve la misma respuesta.
_IDEMPOTENCY_TTL_S = 24 * 3600
#: Los nichos de los clientes del partner, leídos con cada cliente puesto: se
#: guardan un rato para no repetirlo a cada tecla.
_NICHES_TTL_S = 300
_NICHES_MAX_CLIENTS = 300
_NICHES_CONCURRENCY = 8

_SORTABLE = {
    "created_at": Tenant.created_at,
    "updated_at": Tenant.updated_at,
    "name": Tenant.name,
    "status": Tenant.status,
}


def _summary(
    mapping: PartnerTenant, tenant: Tenant, *, out_of_quota: bool = False
) -> ClientSummaryOut:
    return ClientSummaryOut(
        external_client_ref=mapping.external_client_ref,
        name=tenant.name,
        status=tenant.status.value,
        timezone=tenant.timezone,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        out_of_quota=out_of_quota,
        unlimited_consumption=bool(tenant.unlimited_consumption),
    )


async def active_audience(session: AsyncSession) -> ClientAudienceOut | None:
    """Spec 024 (Requisito 3.1): who the ACTIVE version answers — never the
    draft, which is what the settings screen edits. Inside a tenant-scoped
    transaction."""
    policies = await session.scalar(
        sa.select(AgentConfig.policies)
        .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        .order_by(AgentConfig.version.desc())
        .limit(1)
    )
    if policies is None:
        return None
    mode, count = count_of(policies)
    return ClientAudienceOut(mode=mode, count=count)


async def _detail(scope: ClientScope) -> ClientOut:
    """Summary + health with the quota reading (spec 016, R2.1) + the four
    setup steps, the sector and the quota (spec 017, R1)."""
    from nexus_api.metering.wallet import allocations_for

    partner_id = scope.principal.partner.id
    no_quota = await out_of_quota(partner_id, scope.tenant.id)
    health = await client_health(scope.session, scope.tenant, out_of_quota=no_quota)
    allocation = (await allocations_for(partner_id, [scope.tenant.id])).get(scope.tenant.id)
    setup = client_setup_detail(
        agent=health.agent_configured,
        channel=await active_customer_channel(scope.session),
        quota=not no_quota,
        active=scope.tenant.status is TenantStatus.ACTIVE,
    )
    summary = _summary(scope.mapping, scope.tenant, out_of_quota=no_quota).model_dump(
        exclude={"setup", "quota", "audience"}
    )
    return ClientOut(
        **summary,
        health=health,
        sector=await client_sector(scope.session),
        audience=await active_audience(scope.session),
        setup=setup,
        quota=ClientQuotaOut.from_credits(*allocation) if allocation else None,
        # Solo cuando de verdad atiende: una fecha con un paso pendiente
        # diría que atendía antes de poder hacerlo.
        serving_since=(await serving_since(scope.session)) if setup.next is None else None,
    )


# ── list / create ──────────────────────────────────────────────────────


@router.get("", response_model=ClientListOut)
async def list_clients(
    principal: ConsolePrincipal = Depends(require_console_principal("clients:read")),
    session: AsyncSession = Depends(get_db_session),
    q: str | None = Query(default=None, max_length=120, description="Search name or ref"),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    list_filter: Literal["all", "attention", "active", "archived"] | None = Query(
        default=None,
        alias="filter",
        description="Spec 047 (R7.4): the new console's filters, with their counters.",
    ),
    sort: Literal["created_at", "updated_at", "name", "status"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ClientPageOut:
    """The partner's clients. Search, status filter, sort and offset paging.
    Bounded by ``partner_tenants.partner_id = <principal's partner>`` — the
    query cannot express another partner. With the new console (or a
    ``filter``), the spec 047 list (module docstring)."""
    if list_filter is not None or console_v2.console_version(principal.partner) == "v2":
        return await _list_v2(
            principal, session, q=q, wanted=list_filter or "all", limit=limit, offset=offset
        )
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
    from nexus_api.metering.wallet import allocations_for, quota_state
    from nexus_api.services.console_home import tenant_snapshots

    ids = [tenant.id for _, tenant in rows]
    quota = await quota_state(principal.partner.id, ids)
    # Spec 017 (R9.1): who is ready and how much is left, read once per page
    # — the ledger in one partner-scoped query and the per-tenant snapshot
    # the home page already uses (channels and conversations have no
    # reporting policy, so it is one scoped statement per tenant, bounded
    # by the page size, never one HTTP call per row).
    allocations = await allocations_for(principal.partner.id, ids)
    snap = await tenant_snapshots(ids, month_start=datetime.now(UTC) - timedelta(days=7))

    def _row(mapping: PartnerTenant, tenant: Tenant) -> ClientSummaryOut:
        s = snap.snapshots.get(tenant.id)
        no_quota = quota.get(tenant.id, True)
        allocation = allocations.get(tenant.id)
        return _summary(mapping, tenant, out_of_quota=no_quota).model_copy(
            update={
                "setup": client_setup(
                    agent=bool(s and s.agent_version is not None),
                    channel=bool(s and s.active_channels > 0),
                    quota=not no_quota,
                    active=tenant.status is TenantStatus.ACTIVE,
                ),
                "quota": ClientQuotaOut.from_credits(*allocation) if allocation else None,
                "conversations_7d": s.conversations_month if s else 0,
                # Spec 024: what the ACTIVE agent answers, from the same snapshot.
                "audience": ClientAudienceOut(mode=s.audience_mode, count=s.audience_count)
                if s and s.audience_mode is not None
                else None,
            }
        )

    return ClientPageOut(
        items=[_row(mapping, tenant) for mapping, tenant in rows],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


# ── spec 047: the new console's list, header and Panel ─────────────────────────


def _money(cents: int | None, currency: str = CURRENCY) -> MoneyOut | None:
    """Cents as ``{amount_micros, currency}`` (cien milésimas, exact to the cent:
    the same rounding as Consumo and the lite console). Spec 047: a bag carries
    its own currency."""
    if cents is None:
        return None
    return MoneyOut(amount_micros=int(cents) * 1000, currency=currency)  # type: ignore[arg-type]


def _visible_out(state: VisibleState) -> VisibleStateOut:
    return VisibleStateOut(
        code=state.code,  # type: ignore[arg-type]
        tone=state.tone,  # type: ignore[arg-type]
        pause_reason=state.reason,  # type: ignore[arg-type]
    )


def _bag_out(bag: blocks.BagBlock | None) -> BagOut | None:
    if bag is None:
        return None
    return BagOut(
        state=bag.state,  # type: ignore[arg-type]
        balance=_money(bag.remaining_cents, bag.currency),
        assigned=_money(bag.cap_cents, bag.currency),
        spent=_money(bag.spent_cents, bag.currency),
        pct_spent=bag.pct_spent,
        pct_left=bag.pct_left,
        days_left=bag.days_left,
        days_estimable=bag.days_estimable,
        alerts=list(bag.alerts),  # type: ignore[arg-type]
    )


def _attention_out(found: Attention) -> AttentionOut:
    return AttentionOut(
        needs=found.needs_attention,
        reasons=[
            AttentionReasonOut(code=r.code, count=r.count)  # type: ignore[arg-type]
            for r in found.reasons
        ],
    )


def _agents_summary(detail: ClientDetail | None) -> AgentsSummaryOut:
    counts = {"serving": 0, "testing": 0, "ready_no_channel": 0, "draft": 0, "paused": 0}
    total = 0
    for agent in detail.agents if detail else []:
        if agent.visible.code == "archived":
            continue
        total += 1
        counts[agent.visible.code] = counts.get(agent.visible.code, 0) + 1
    return AgentsSummaryOut(total=total, **counts)


def _row_v2(
    mapping: PartnerTenant,
    tenant: Tenant,
    *,
    principal: ConsolePrincipal,
    detail: ClientDetail | None,
    bag: blocks.BagBlock | None,
    found: Attention,
) -> ClientListRowOut:
    archived = tenant.status is TenantStatus.ARCHIVED
    summary = _summary(mapping, tenant, out_of_quota=bool(bag and bag.empty))
    return ClientListRowOut(
        **summary.model_dump(),
        niche=detail.niche if detail else None,
        lifecycle=lifecycle_of(tenant.status),
        attention=_attention_out(found),
        agents=[
            ClientAgentOut(agent_id=a.agent_id, name=a.name, visible_state=_visible_out(a.visible))
            for a in (detail.agents if detail else [])
            if a.visible.code != "archived"
        ],
        agents_summary=_agents_summary(detail),
        bag=_bag_out(bag),
        allowed=blocks.client_actions(principal.permissions, archived=archived),  # type: ignore[arg-type]
    )


async def _list_v2(
    principal: ConsolePrincipal,
    session: AsyncSession,
    *,
    q: str | None,
    wanted: str,
    limit: int,
    offset: int,
) -> ClientListOut:
    """Requisito 7: every client of the partner, read once (platform rows, then
    each client under its RLS and the partner's ledger), searched by name, ref
    or niche, counted per filter and ordered by the one attention rule."""
    async with session.begin():
        rows = (
            await session.execute(
                sa.select(PartnerTenant, Tenant)
                .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
                .where(PartnerTenant.partner_id == principal.partner.id)
                .order_by(PartnerTenant.external_client_ref)
            )
        ).all()
    details = await read_clients([(t.id, t.status) for _m, t in rows])
    bag_by = await client_bags(
        principal.partner.id, [(t.id, bool(t.unlimited_consumption)) for _m, t in rows]
    )
    needle = fold(q) if q and q.strip() else None
    entries = []
    for mapping, tenant in rows:
        detail = details.get(tenant.id)
        if needle is not None:
            hay = " ".join(
                fold(x or "")
                for x in (
                    tenant.name,
                    mapping.client_name,
                    mapping.external_client_ref,
                    detail.niche if detail else None,
                )
            )
            if needle not in hay:
                continue
        archived = tenant.status is TenantStatus.ARCHIVED
        bag = bag_by.get(tenant.id)
        facts = client_facts(mapping.external_client_ref, archived=archived, bag=bag, detail=detail)
        entries.append((mapping, tenant, detail, bag, facts, attention_of(facts)))
    counts = ClientCountsOut(
        all=len(entries),
        attention=sum(1 for e in entries if e[5].needs_attention),
        active=sum(1 for e in entries if lifecycle_of(e[1].status) == "active"),
        archived=sum(1 for e in entries if e[1].status is TenantStatus.ARCHIVED),
    )
    if wanted == "attention":
        entries = [e for e in entries if e[5].needs_attention]
    elif wanted == "active":
        entries = [e for e in entries if lifecycle_of(e[1].status) == "active"]
    elif wanted == "archived":
        entries = [e for e in entries if e[1].status is TenantStatus.ARCHIVED]
    by_ref = {e[0].external_client_ref: e for e in entries}
    ordered = [by_ref[f.ref] for f in list_order(e[4] for e in entries)]
    page = ordered[offset : offset + limit]
    return ClientListOut(
        items=[
            _row_v2(m, t, principal=principal, detail=d, bag=b, found=a)
            for m, t, d, b, _f, a in page
        ],
        total=len(ordered),
        limit=limit,
        offset=offset,
        counts=counts,
    )


async def _detail_v2(scope: ClientScope) -> ClientDetailOut:
    """Today's detail plus what the edit modal shows, the lifecycle, the basics
    ``revision`` (``If-Match``) and what this person may do."""
    from nexus_api.db.models.business import BusinessProfile as Profile
    from nexus_api.services.business.writes import current_revision

    base = await _detail(scope)
    profile = await scope.session.get(Profile, scope.tenant.id)
    revision = await current_revision(scope.session, "basics") if profile is not None else None
    return ClientDetailOut(
        **base.model_dump(),
        niche=profile.niche if profile else None,
        info=profile.info if profile else None,
        website=profile.website if profile else None,
        country=profile.country if profile else None,
        price_currency=profile.price_currency if profile else None,
        wallet_currency=await _bag_currency(scope, profile.country) if profile else None,
        eu_only=profile.eu_only if profile else None,
        sovereign=bool(profile.sovereign) if profile else False,
        lifecycle=lifecycle_of(scope.tenant.status),
        revision=revision,
        allowed=blocks.client_actions(  # type: ignore[arg-type]
            scope.principal.permissions,
            archived=scope.tenant.status is TenantStatus.ARCHIVED,
        ),
    )


async def _bag_currency(scope: ClientScope, country: str | None) -> Literal["EUR", "USD"]:
    """Spec 047 (43.3): la moneda de la bolsa del cliente, la guardada o, si aún no
    tiene bolsa, la de su país."""
    from nexus_api.services.wallet.bags import currency_for, currency_of

    found = await currency_of(scope.principal.partner.id, scope.tenant.id)
    return "EUR" if (found or currency_for(country)) == "EUR" else "USD"


def _lifecycle_out(
    ref: str, lifecycle: str, previous: str | None, agents: list[AgentChange], *, undo: bool
) -> ClientLifecycleOut:
    return ClientLifecycleOut(
        ref=ref,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        previous=previous,  # type: ignore[arg-type]
        agents=[
            AgentLifecycleOut(
                agent_id=a.agent_id,
                name=a.name,
                visible_state=_visible_out(a.after),
                before=_visible_out(a.before),
            )
            for a in agents
            if a.after.code != "archived"
        ],
        undo="restore" if undo else None,
    )


def _lifecycle_error(exc: LifecycleError) -> HTTPException:
    detail: dict[str, object] = {"code": exc.code}
    if exc.code == "legal_retention":
        detail["message"] = exc.message
        detail["fix"] = "keep_archived"
    return HTTPException(status_code=exc.status, detail=detail)


async def _publish_promote(redis: Redis, tenant_id: uuid.UUID) -> None:
    """Tell the worker to drop its cached bundle (name and zone ride on it)."""
    from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL

    try:
        await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    except Exception as exc:  # stale-cache risk only, never fail the write
        log.warning("console.client.promote_publish_failed", error=type(exc).__name__)


# ── the new alta: what the modal asks while the person types ───────────────


async def _partner_niches(principal: ConsolePrincipal, redis: Redis) -> list[tuple[str, int]]:
    """The niches of the partner's own clients, with how many have each.

    ``business_profiles`` is per client with RLS FORCE: it is read with each
    client set (``tenant_scoped_session``), a few at a time, the pattern of
    ``/console/search``. Bounded to the most recent clients and kept a few
    minutes per partner so a keystroke is not one query per client. Another
    partner's clients are not even listed: the mapping is the principal's."""
    key = f"console:niches:{principal.partner.id}"
    try:
        cached = await redis.get(key)
    except Exception:  # pragma: no cover - the cache is a convenience
        cached = None
    if cached:
        return [(str(v), int(n)) for v, n in json.loads(cached)]

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        tenant_ids = list(
            (
                await session.execute(
                    sa.select(PartnerTenant.tenant_id)
                    .where(PartnerTenant.partner_id == principal.partner.id)
                    .order_by(PartnerTenant.created_at.desc())
                    .limit(_NICHES_MAX_CLIENTS)
                )
            ).scalars()
        )
    sem = asyncio.Semaphore(_NICHES_CONCURRENCY)
    found: list[str] = []

    async def one(tenant_id: uuid.UUID) -> None:
        async with sem:
            try:
                async with sm() as session, tenant_scoped_session(session, tenant_id):
                    niche = await session.scalar(
                        sa.select(BusinessProfile.niche).where(
                            BusinessProfile.tenant_id == tenant_id
                        )
                    )
            except Exception as exc:  # one client that fails does not hide the rest
                log.warning("console.niches.read_failed", error=type(exc).__name__)
                return
        if niche:
            found.append(niche)

    await asyncio.gather(*(one(t) for t in tenant_ids))
    counts: dict[str, int] = {}
    for niche in found:
        counts[niche] = counts.get(niche, 0) + 1
    used = sorted(counts.items(), key=lambda item: -item[1])
    with contextlib.suppress(Exception):
        await redis.set(key, json.dumps(used), ex=_NICHES_TTL_S)
    return used


@router.get("/niche-suggestions", response_model=NicheSuggestionsOut)
async def get_niche_suggestions(
    q: str | None = Query(default=None, max_length=80, description="What the person typed."),
    principal: ConsolePrincipal = Depends(require_console_principal("clients:read")),
    redis: Redis = Depends(get_redis),
) -> NicheSuggestionsOut:
    """Requisito 4.2: the templates' niches, in the 6 groups plus «Otro», and
    the partner's most used. They never restrict what is typed, and ``q`` is
    never echoed back."""
    used = await _partner_niches(principal, redis)
    return NicheSuggestionsOut(
        items=[
            NicheSuggestionOut(
                source=s.source, key=s.key, group=s.group, value=s.value, uses=s.uses
            )
            for s in niche_suggestions(q, used=used)
        ]
    )


def _link_out(link: DetectedLink) -> DetectedLinkOut:
    return DetectedLinkOut(
        kind=link.kind,
        network=link.network,  # type: ignore[arg-type]
        value=link.value,
        url=link.url,
        handle=link.handle,
        target=link.target,
        guessed=link.guessed,
        alternatives=list(link.alternatives),  # type: ignore[arg-type]
    )


def _deduced_out(deduced: Deduction) -> DeducedSettingsOut:
    return DeducedSettingsOut(
        country=deduced.country,
        timezone=deduced.timezone,
        price_currency=deduced.price_currency,
        wallet_currency=deduced.wallet_currency,  # type: ignore[arg-type]
        eu_only=deduced.eu_only,
        source=deduced.source,
    )


@router.post("/link-detection", response_model=LinkDetectionOut)
async def detect_client_links(
    body: LinkDetectionIn,
    _principal: ConsolePrincipal = Depends(require_console_principal("clients:write")),
) -> LinkDetectionOut:
    """Requisitos 5.1, 5.2 y 4.5: the chips of «Irá a la ficha» and «Más
    ajustes» filled in, while the person types. Pure: nothing is written."""
    links = detect_links(body.info)
    deduced = deduce_settings(
        info=body.info,
        links=links,
        browser_timezone=body.browser_timezone,
        browser_locale=body.browser_locale,
    )
    return LinkDetectionOut(
        links=[_link_out(link) for link in links], deduced=_deduced_out(deduced)
    )


def _chosen_links(body: ClientNewIn) -> list[DetectedLink]:
    """The chips the person kept; without them, the ones in ``info``."""
    if body.links is None:
        return detect_links(body.info or "")
    out: list[DetectedLink] = []
    seen: set[tuple[str, str]] = set()
    for choice in body.links:
        link = link_from_choice(choice.network, url=choice.url, handle=choice.handle)
        if link is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_link", "network": choice.network},
            )
        if link.key() not in seen:
            seen.add(link.key())
            out.append(link)
    return out


def _new_client(body: ClientNewIn) -> tuple[NewClient, str]:
    """What the person chose wins; the rest is deduced (requisito 4.5). A
    country chosen by hand brings its own zone and currency if those were not
    chosen too. Returns the client and its bag currency."""
    links = _chosen_links(body)
    deduced = deduce_settings(info=body.info or "", links=links)
    country = body.country if body.country is not None else deduced.country
    known = COUNTRIES.get(country) if country else None
    if body.timezone is not None:
        timezone = body.timezone
    elif body.country is not None and known is not None:
        timezone = known.timezones[0]
    else:
        timezone = deduced.timezone
    if body.price_currency is not None:
        price_currency: str | None = body.price_currency
    elif body.country is not None:
        price_currency = known.currency if known else None
    else:
        price_currency = deduced.price_currency
    eu_only = body.eu_only if body.eu_only is not None else eu_by_default(country)
    wallet = body.wallet_currency or deduced.wallet_currency
    return (
        NewClient(
            name=body.name,
            niche=body.niche,
            info=body.info,
            country=country,
            timezone=timezone,
            price_currency=price_currency,
            eu_only=eu_only,
            links=links,
            wallet_currency=body.wallet_currency,
        ),
        wallet,
    )


async def _create_new(
    body: ClientNewIn,
    *,
    request: Request,
    principal: ConsolePrincipal,
    session: AsyncSession,
    redis: Redis,
    idempotency_key: str | None,
) -> ClientNewOut:
    """Requisito 4: three fields, no agent, the reading if there is something
    to read. A repeated ``Idempotency-Key`` answers the same as the first."""
    idem = (
        f"console:idem:{principal.partner.id}:client_create:{idempotency_key[:120]}"
        if idempotency_key
        else None
    )
    if idem is not None:
        prior = await redis.get(idem)
        if prior:
            return ClientNewOut.model_validate_json(prior)
    new, _wallet_currency = _new_client(body)
    try:
        created = await create_new_client(
            session,
            partner=principal.partner,
            new=new,
            person_id=principal.user_id,
            audit_actor=principal.actor,
            ip=request.client.host if request.client else None,
        )
    except ProvisioningQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if created.read_job is not None:
        try:
            await enqueue_job(redis, created.read_job)
        except Exception as exc:
            # The row is the truth: a job nobody heard about expires on its
            # own and the card offers to read again.
            log.warning("console.client.read_enqueue_failed", error=type(exc).__name__)
    out = ClientNewOut(
        ref=created.ref,
        name=created.name,
        status="active",
        duplicate_name=created.duplicate_name,
        read_job_id=created.read_job.id if created.read_job is not None else None,
    )
    with contextlib.suppress(Exception):
        await redis.delete(f"console:niches:{principal.partner.id}")
        if idem is not None:
            await redis.set(idem, out.model_dump_json(), ex=_IDEMPOTENCY_TTL_S)
    return out


@router.post(
    "",
    response_model=ClientCreateOut | ClientNewOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Client quota reached — nothing was created."},
        422: {"description": "The partner's blueprint failed to provision the client."},
    },
)
async def create_client(
    body: ClientNewIn | ClientCreateIn,
    request: Request,
    principal: ConsolePrincipal = Depends(require_console_principal("clients:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
) -> ClientCreateOut | ClientNewOut:
    """Two bodies (module docstring). The new console's never creates an
    agent; today's has the same semantics as ``POST /v2/partners/clients``:
    idempotent on the ref, quota checked before anything is written (CP-06)."""
    if isinstance(body, ClientNewIn):
        return await _create_new(
            body,
            request=request,
            principal=principal,
            session=session,
            redis=redis,
            idempotency_key=idempotency_key,
        )
    if body.seed_template:
        # Spec 047, enmienda del 2026-10-30 (65.10): on the new console a client
        # never comes with an agent mounted from a template; nothing is created.
        from .seed_templates import refuse_on_new_console

        refuse_on_new_console(principal.partner, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)
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
    agent_status: str = out.agent.status
    if body.seed_template and out.agent.status == "not_configured":
        # CP-10: stage a draft v1 from the chosen seed, inside the new
        # client's scope. Idempotent on re-runs: a client that already has
        # versions is left alone (the wizard's retry of stage 1 must not
        # duplicate the draft).
        from .seed_templates import stage_from_seed

        mapping = await resolve_mapping(session, principal, out.external_client_ref)
        token = _current_tenant.set(mapping.tenant_id)
        try:
            async with session.begin():
                tenant = await session.get(Tenant, mapping.tenant_id)
                if tenant is None:  # pragma: no cover - FK guarantees the row
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND, detail="Unknown client reference"
                    )
                await apply_tenant_to_session(session, mapping.tenant_id)
                scope = ClientScope(
                    principal=principal, mapping=mapping, tenant=tenant, session=session
                )
                if await AgentConfigService(session).list_versions():
                    agent_status = "already_provisioned"
                else:
                    await stage_from_seed(
                        session,
                        scope,
                        seed_template=body.seed_template,
                        placeholders=body.placeholders or {},
                    )
                    agent_status = "staged"
        finally:
            _current_tenant.reset(token)
    return ClientCreateOut(
        external_client_ref=out.external_client_ref,
        status=out.status,
        agent_status=agent_status,
        whatsapp_connected=out.whatsapp.status == "connected",
        quota=await quota_out(session, principal),
    )


# ── detail / update / lifecycle ────────────────────────────────────────


@router.get("/{ref}", response_model=ClientDetailOut)
async def get_client(
    response: Response, scope: ClientScope = Depends(client_scope("clients:read"))
) -> ClientDetailOut:
    out = await _detail_v2(scope)
    if out.revision is not None:
        response.headers["ETag"] = etag(out.revision)
    return out


# ── the reading card (requisitos 5.7 y 14.7) ────────────────────────────────


@router.get("/{ref}/business/read", response_model=ClientReadOut)
async def get_client_read(
    scope: ClientScope = Depends(client_scope("clients:read")),
) -> ClientReadOut:
    """The last ``client_read`` job (with the lazy expiry of ``GET
    /console/jobs/{id}``) and what the client has to read. The Panel's card
    polls ``/console/jobs/{id}`` from here."""
    job = await business_sources.latest_site_read(scope.session)
    website, networks = await business_reader.readable(scope.session)
    return ClientReadOut(
        job=job_out(job) if job is not None else None,
        website=website,
        networks=networks,  # type: ignore[arg-type]
    )


@router.post(
    "/{ref}/business/read",
    response_model=JobAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        402: {"description": "build_budget_exhausted: «Construcción y pruebas» is spent."},
        409: {"description": "nothing_to_read: no web and no networks."},
    },
)
async def start_client_read(
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("clients:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> JobAcceptedOut:
    """«Reintentar» / «Volver a leer» (requisitos 5.7 y 12.3). A reading still
    running is returned, not started twice. The job is enqueued after its row
    is committed, so this route opens its own scoped transaction.

    Spec 047, T217: reading spends «Construcción y pruebas», which Auphere pays up
    to the partner's cap — spent, ``402 build_budget_exhausted`` (46.5)."""
    await require_build_room(principal.partner.id)
    mapping = await resolve_mapping(session, principal, ref)
    try:
        async with tenant_scoped_session(session, mapping.tenant_id):
            job, created = await business_sources.request_site_read(
                session, created_by=principal.user_id
            )
    except business_reader.NothingToRead as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "nothing_to_read"}
        ) from exc
    if created:
        try:
            await enqueue_job(redis, job)
        except Exception as exc:
            log.warning("console.client.read_enqueue_failed", error=type(exc).__name__)
    return JobAcceptedOut(job_id=job.id)


@router.patch(
    "/{ref}",
    response_model=ClientDetailOut,
    responses={
        409: {"description": "bag_currency_locked"},
        412: {"description": "revision_conflict"},
        422: {"description": "invalid_timezone and the modal's field codes"},
        428: {"description": "revision_required (new console)"},
    },
)
async def update_client(
    body: ClientEditIn,
    response: Response,
    ref: str = ClientRef,
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: ConsolePrincipal = Depends(require_console_principal("clients:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ClientDetailOut:
    """The edit modal (requisito 6.1). The zone must be IANA — checked here
    (6.2). On the new console the write carries ``If-Match`` with the basics
    revision and goes through the ficha (history, provenance, recompilation);
    after commit the runtime hears about a new name or zone (6.3). Today's
    console keeps its ``{name, timezone}`` edit."""
    from nexus_api.services.business import profile_edits
    from nexus_api.services.business.writes import SectionRevisionConflict

    changes = body.model_dump(exclude_unset=True)
    if "timezone" in changes and not is_valid_timezone(changes["timezone"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_timezone", "field": "timezone"},
        )
    mapping = await resolve_mapping(session, principal, ref)
    v2 = console_v2.console_version(principal.partner) == "v2"
    if v2:
        expected = parse_revision(if_match)
        if expected is None:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={"code": "revision_required"},
            )
    elif set(changes) - {"name", "timezone"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unknown_field",
                "field": sorted(set(changes) - {"name", "timezone"})[0],
            },
        )
    tell_runtime = False
    async with tenant_scoped_session(session, mapping.tenant_id):
        tenant = await session.get(Tenant, mapping.tenant_id)
        assert tenant is not None  # FK RESTRICT
        scope = ClientScope(principal=principal, mapping=mapping, tenant=tenant, session=session)
        if v2:
            try:
                edited = await profile_edits.update_basics(
                    session,
                    changes,
                    actor=Actor(kind="partner_member", id=principal.user_id, origin="console"),
                    expected_revision=expected,
                    audit_actor=principal.actor,
                    audit=False,
                )
            except profile_edits.InvalidField as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": exc.code, "field": exc.field},
                ) from exc
            except profile_edits.BagCurrencyLocked as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail={"code": "bag_currency_locked"}
                ) from exc
            except SectionRevisionConflict as exc:
                raise HTTPException(
                    status_code=status.HTTP_412_PRECONDITION_FAILED,
                    detail={
                        "code": "revision_conflict",
                        "section": "basics",
                        "current": exc.current,
                        "changes": exc.changes,
                    },
                    headers={"ETag": etag(exc.current)},
                ) from exc
            if edited.changed:
                session.add(
                    AuditLog(
                        tenant_id=tenant.id,
                        actor=principal.actor,
                        action=UPDATE_ACTION,
                        target=f"tenant:{tenant.id}",
                        before_json={k: edited.before.get(k) for k in edited.changed},
                        after_json={k: edited.after.get(k) for k in edited.changed},
                    )
                )
            tell_runtime = bool({"name", "timezone"} & set(edited.changed))
        else:
            before = {k: getattr(tenant, k) for k in changes}
            for key, value in changes.items():
                setattr(tenant, key, value)
            if "name" in changes:
                mapping.client_name = changes["name"]
            if changes and any(before[k] != changes[k] for k in changes):
                session.add(
                    AuditLog(
                        tenant_id=tenant.id,
                        actor=principal.actor,
                        action=UPDATE_ACTION,
                        target=f"tenant:{tenant.id}",
                        before_json=before,
                        after_json=changes,
                    )
                )
                tell_runtime = True
        await session.flush()
        # ``updated_at`` is a server-side ``onupdate``: reload before serialising.
        await session.refresh(tenant)
        out = await _detail_v2(scope)
    if tell_runtime:
        await _publish_promote(redis, mapping.tenant_id)
    if out.revision is not None:
        response.headers["ETag"] = etag(out.revision)
    return out


@router.post(
    "/{ref}/archive",
    response_model=ClientLifecycleOut,
    responses={409: {"description": "already_archived"}},
)
async def archive(
    scope: ClientScope = Depends(client_scope("clients:write")),
) -> ClientLifecycleOut:
    """Requisito 6.4: its agents paused with «cliente archivado», remembering
    how each one was; the lite console and the app closed; «Deshacer» = restore."""
    try:
        previous, agents = await archive_client(
            scope.session, scope.tenant, actor=scope.principal.actor
        )
    except LifecycleError as exc:
        raise _lifecycle_error(exc) from exc
    out = _lifecycle_out(scope.ref, "archived", previous, agents, undo=True)
    from nexus_api.services.wallet.bags import balance_left

    left = await balance_left(scope.principal.partner.id, scope.tenant.id)
    if left is not None:
        out.bag_left = MoneyOut(amount_micros=left[0], currency=left[1])  # type: ignore[arg-type]
    return out


@router.post(
    "/{ref}/restore",
    response_model=ClientLifecycleOut,
    responses={409: {"description": "not_archived"}},
)
async def restore(
    scope: ClientScope = Depends(client_scope("clients:write")),
) -> ClientLifecycleOut:
    """Requisito 6.5: back to the status it had, and every agent with it."""
    try:
        lifecycle, agents = await restore_client(
            scope.session, scope.tenant, actor=scope.principal.actor
        )
    except LifecycleError as exc:
        raise _lifecycle_error(exc) from exc
    return _lifecycle_out(scope.ref, lifecycle, "archived", agents, undo=False)


@router.get("/{ref}/panel", response_model=ClientPanelOut)
async def get_client_panel(
    scope: ClientScope = Depends(client_scope("clients:read")),
) -> ClientPanelOut:
    """Requisito 14: the client's Panel. Money from the partner's ledger with
    the lite console's own sums (to the cent); no message body, no end
    customer's phone, no cost."""
    from nexus_api.metering.wallet import credit_burn, credit_burn_by_agent
    from nexus_api.services.console_reporting import month_bounds
    from nexus_api.services.lite_home import split_cents

    now = datetime.now(UTC)
    tenant = scope.tenant
    partner_id = scope.principal.partner.id
    detail = await read_client(scope.session, tenant.id, tenant.status)
    bag = (
        await client_bags(partner_id, [(tenant.id, bool(tenant.unlimited_consumption))], now=now)
    )[tenant.id]
    found = attention_of(
        client_facts(
            scope.ref, archived=tenant.status is TenantStatus.ARCHIVED, bag=bag, detail=detail
        )
    )
    since, until, _elapsed, _days = month_bounds(now)
    month_credits = (await credit_burn(partner_id, [tenant.id], since)).get(tenant.id, 0)
    month_cents = blocks.spend_block(
        [blocks.ClientRow(tenant.id, scope.ref, tenant.name, tenant.status)],
        {tenant.id: month_credits},
        0,
        daily_7d=0.0,
        days_left=0.0,
    ).cents
    try:
        by_agent = await credit_burn_by_agent(partner_id, tenant.id, since)
    except Exception as exc:
        log.warning("console.panel.burn_by_agent_failed", error=type(exc).__name__)
        by_agent = {}
    live = [a for a in detail.agents if a.visible.code != "archived"]
    principal_agent = live[0].agent_id if live else None
    total, handed, per_agent = await month_conversations(
        scope.session, since=since, principal=principal_agent
    )
    figures = agent_figures(detail, credits=by_agent, cents={}, conversations=per_agent)
    cents = split_cents(month_cents, [f.credits for f in figures])
    figures = [replace(f, cents=c) for f, c in zip(figures, cents, strict=True)]
    month = blocks.month_block(since.date(), (until - timedelta(seconds=1)).date(), total, handed)
    missing = blocks.first_missing(detail.sections)
    job = await business_sources.latest_site_read(scope.session)
    website, networks = await business_reader.readable(scope.session)
    visible = {a.agent_id: a.visible for a in detail.agents}
    # Spec 047 (44.1): el tope de cada agente, en la moneda de la bolsa.
    from nexus_api.db.models import Agent

    caps: dict[uuid.UUID, int | None] = {
        agent_id: cap
        for agent_id, cap in (
            await scope.session.execute(
                sa.select(Agent.id, Agent.monthly_cap_micros).where(Agent.tenant_id == tenant.id)
            )
        ).all()
    }
    return ClientPanelOut(
        ref=scope.ref,
        name=tenant.name,
        niche=detail.niche,
        lifecycle=lifecycle_of(tenant.status),
        bag=_bag_out(bag) or BagOut(state="unassigned"),
        attention=_attention_out(found),
        spend_by_agent=[
            AgentShareOut(
                agent_id=sh.agent_id,
                name=sh.name,
                spent=_money(sh.cents),  # type: ignore[arg-type]
                share_pct=sh.share_pct,
            )
            for sh in blocks.spend_shares(figures)
        ],
        month=MonthOut(
            period_start=month.period_start,
            period_end=month.period_end,
            conversations=month.conversations,
            handed_to_person=month.handed_to_person,
            resolved_without_person=month.resolved_without_person,
            resolved_pct=month.resolved_pct,
            spent=_money(month_cents),  # type: ignore[arg-type]
        ),
        top_agents=[
            TopAgentOut(
                agent_id=f.agent_id,
                name=f.name,
                visible_state=_visible_out(visible[f.agent_id]),
                spent=_money(f.cents),  # type: ignore[arg-type]
                conversations=f.conversations,
                spend_per_conversation=_money(
                    blocks.per_conversation_cents(f.cents, f.conversations)
                ),
                cap=MoneyOut(amount_micros=int(caps[f.agent_id]), currency=bag.currency)  # type: ignore[arg-type]
                if caps.get(f.agent_id) is not None
                else None,
            )
            for f in blocks.top_spenders([f for f in figures if f.visible != "archived"])
        ],
        agents_total=len(live),
        missing=MissingOut(section=missing, action=f"add_{missing}")  # type: ignore[arg-type]
        if missing
        else None,
        read=ClientReadOut(
            job=job_out(job) if job is not None else None,
            website=website,
            networks=networks,  # type: ignore[arg-type]
        ),
        allowed=blocks.client_actions(  # type: ignore[arg-type]
            scope.principal.permissions, archived=tenant.status is TenantStatus.ARCHIVED
        ),
    )


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
        return await _detail(scope)
    if body.status not in _ALLOWED[current]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot move a {current.value} client to {body.status}",
        )
    has_agent = await scope.session.scalar(
        sa.select(AgentConfig.id).where(AgentConfig.status == AgentConfigStatus.ACTIVE).limit(1)
    )
    if body.status == "active" and current is TenantStatus.PROVISIONING and has_agent is None:
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
    if body.status == "active" and has_agent is not None:
        # CP-29: an ACTIVE client with a published agent = activation.
        # Platform tables (partners.activated_at, console_notifications)
        # are written in a detached session — this transaction runs as
        # ``nexus_app`` and cannot touch them. Idempotent per client.
        await record_client_activation_detached(
            partner_id=scope.principal.partner.id,
            external_client_ref=scope.ref,
        )
    return await _detail(scope)


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
    and the client must already be archived (WP-29 two-step). The new console
    gets named codes (``archive_first``, ``name_mismatch``, ``legal_retention``
    with the legal reason and «keep it archived» as the fix)."""
    if console_v2.console_version(scope.principal.partner) == "v2":
        try:
            await delete_client_v2(
                scope.session,
                scope.tenant,
                confirm_name=body.confirm_name,
                actor=scope.principal.actor,
            )
        except LifecycleError as exc:
            raise _lifecycle_error(exc) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)
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
