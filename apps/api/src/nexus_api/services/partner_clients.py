"""Client (tenant) lifecycle for a partner — shared by the public partner
API (``/v1|v2/partners/clients``) and the partner console
(``/console/clients``).

One code path for "a partner creates a client" so the two surfaces can
never drift on the things that matter: idempotency on
``external_client_ref``, the just-in-time ``PROVISIONING`` tenant, the
blueprint, and — since CP-06 — the **provisioning quota**.

Quota (migration 0081): ``partners.max_clients`` counts the partner's
clients whose tenant is not archived. It is checked **before anything is
created**, with the partner row locked (``SELECT … FOR UPDATE``), so two
concurrent creations cannot both slip under the limit, and a refused
creation leaves no tenant, no mapping and no audit row behind. Existing
refs are idempotent and never consume quota.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
import structlog
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Partner,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.metering.wallet import seed_default_allocation
from nexus_api.repositories.partner import EmbedAuditRepository, PartnerTenantRepository
from nexus_api.schemas.partner import (
    ClientAgentOut,
    ClientProvisionIn,
    ClientProvisionOut,
    WhatsAppStatusOut,
)
from nexus_api.services.partner_provisioning import provision_client_blueprint

log = structlog.get_logger(__name__)

_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")


class ProvisioningQuotaExceeded(Exception):
    """The partner is at ``max_clients``. Surfaces as HTTP 409 with an
    actionable message. Nothing was created."""

    def __init__(self, *, used: int, limit: int) -> None:
        super().__init__(
            f"Client quota reached: {used} of {limit} clients in use. "
            "Archive a client you no longer need or ask Auphere to raise the limit."
        )
        self.used = used
        self.limit = limit


@dataclass(frozen=True)
class QuotaState:
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


def client_slug(partner_slug: str, external_client_ref: str) -> str:
    """Deterministic, unique tenant slug for a partner's client.

    The ref is the partner's arbitrary string — slugify what we can and
    append a short digest of the exact ref so two refs that normalise to
    the same text (e.g. ``client_42`` vs ``client 42``) can't collide.
    """
    normalised = _SLUG_SAFE.sub("-", external_client_ref.lower()).strip("-") or "client"
    digest = uuid.uuid5(uuid.NAMESPACE_URL, external_client_ref).hex[:8]
    return f"p-{partner_slug}-{normalised}"[:70] + f"-{digest}"


async def count_quota_usage(session: AsyncSession, partner_id: uuid.UUID) -> int:
    """Clients that count against ``max_clients``: every mapping whose
    tenant is not archived. Archiving frees the slot; deleting too."""
    result = await session.execute(
        sa.select(sa.func.count())
        .select_from(PartnerTenant)
        .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
        .where(
            PartnerTenant.partner_id == partner_id,
            Tenant.status != TenantStatus.ARCHIVED,
        )
    )
    return int(result.scalar_one())


async def quota_state(session: AsyncSession, partner: Partner) -> QuotaState:
    used = await count_quota_usage(session, partner.id)
    return QuotaState(used=used, limit=partner.max_clients)


async def _lock_partner_and_check_quota(session: AsyncSession, partner_id: uuid.UUID) -> None:
    """Inside the creating transaction: lock the partner row, re-read the
    limit, count. Raises :class:`ProvisioningQuotaExceeded`."""
    locked = await session.execute(
        sa.select(Partner.max_clients).where(Partner.id == partner_id).with_for_update()
    )
    limit = int(locked.scalar_one())
    used = await count_quota_usage(session, partner_id)
    if used >= limit:
        raise ProvisioningQuotaExceeded(used=used, limit=limit)


async def whatsapp_status(session: AsyncSession, tenant_id: uuid.UUID) -> WhatsAppStatusOut:
    """Read the tenant's WhatsApp channel under RLS scope.

    Runs in its own short transaction: ``set_config(app.tenant_id)`` is
    transaction-local, so nothing leaks into the caller's work.
    """
    async with session.begin():
        await apply_tenant_to_session(session, tenant_id)
        result = await session.execute(
            sa.select(Channel.provider_identifier)
            .where(
                Channel.type == ChannelType.WHATSAPP,
                Channel.status == ChannelStatus.ACTIVE,
            )
            .limit(1)
        )
        phone = result.scalar_one_or_none()
    if phone is None:
        return WhatsAppStatusOut(status="not_connected", display_phone_number=None)
    return WhatsAppStatusOut(status="connected", display_phone_number=phone)


class ProvisioningFailed(Exception):
    """Wraps ``ProvisioningError`` from the blueprint so callers can map it
    (422 on both surfaces)."""


async def provision_partner_client(
    session: AsyncSession,
    redis: Redis,
    *,
    partner: Partner,
    body: ClientProvisionIn,
    api_key_id: uuid.UUID | None,
    actor: str,
    ip: str | None,
) -> ClientProvisionOut:
    """Idempotent: registering the same ``external_client_ref`` twice
    returns the existing mapping. First registration checks the quota,
    then creates the tenant just-in-time with status ``provisioning`` (no
    channel until the WhatsApp signup completes).

    Partners configured with a blueprint (``default_seed_template`` /
    ``default_connector_slug``) also get their agent seeded + promoted and
    the connector installed in the same call — see
    ``services/partner_provisioning.py``. Re-provisioning rotates
    connector credentials but never re-seeds an existing agent.

    ``actor`` is what lands in the embed audit payload (``partner:<slug>``
    on the API surface, ``console:<email>`` on the console).
    """
    from nexus_api.services.partner_provisioning import ProvisioningError

    mappings = PartnerTenantRepository(session)

    # Reads and writes each run in their own transaction block — SQLAlchemy
    # autobegin would otherwise collide with the explicit ``begin()`` below.
    async with session.begin():
        mapping = await mappings.get_mapping(partner.id, body.external_client_ref)
    if mapping is None:
        try:
            async with session.begin():
                # Quota FIRST, under the partner row lock. Raising here
                # rolls the (empty) transaction back: nothing was touched.
                await _lock_partner_and_check_quota(session, partner.id)
                tenant = Tenant(
                    id=uuid.uuid4(),
                    name=body.name,
                    slug=client_slug(partner.slug, body.external_client_ref),
                    status=TenantStatus.PROVISIONING,
                    timezone=body.timezone,
                    partner_id=partner.id,
                )
                session.add(tenant)
                await session.flush()
                mapping = await mappings.create(
                    PartnerTenant(
                        partner_id=partner.id,
                        external_client_ref=body.external_client_ref,
                        tenant_id=tenant.id,
                        client_name=body.name,
                    )
                )
                # D1 — la cuota nace con el cliente, en esta misma
                # transacción. Sin esto ``allow_channel_turn`` lo deja mudo
                # desde el primer mensaje: la fila de ``partner_allocations``
                # no la creaba nadie, ni el wizard ni esta función ni la 0094.
                granted = await seed_default_allocation(
                    session,
                    partner_id=partner.id,
                    tenant_id=tenant.id,
                    default_cap=get_settings().partner_default_client_allocation_tokens,
                )
                await EmbedAuditRepository(session).record(
                    event="client.provisioned",
                    partner_id=partner.id,
                    api_key_id=api_key_id,
                    tenant_id=tenant.id,
                    payload={
                        "external_client_ref": body.external_client_ref,
                        "actor": actor,
                        "allocation_tokens": granted,
                    },
                    ip=ip,
                )
        except IntegrityError:
            # Lost a race against a concurrent provision of the same ref —
            # the winner's row is the truth.
            async with session.begin():
                mapping = await mappings.get_mapping(partner.id, body.external_client_ref)
            if mapping is None:  # pragma: no cover - defensive
                raise ProvisioningFailed("provisioning conflict") from None

    agent_out = ClientAgentOut(status="not_configured")
    connector_connected = False
    run_blueprint = partner.default_seed_template is not None or (
        partner.default_connector_slug is not None and body.connector is not None
    )
    if run_blueprint:
        ctx_token = _current_tenant.set(mapping.tenant_id)
        try:
            async with session.begin():
                await apply_tenant_to_session(session, mapping.tenant_id)
                blueprint_tenant = await session.get(Tenant, mapping.tenant_id)
                if blueprint_tenant is None:  # pragma: no cover - FK guarantees the row
                    raise ProvisioningFailed("tenant row missing for mapping")
                result = await provision_client_blueprint(
                    session,
                    partner=partner,
                    tenant=blueprint_tenant,
                    placeholders=body.agent.placeholders if body.agent else None,
                    connector_credentials=(body.connector.credentials if body.connector else None),
                    connector_meta=body.connector.meta if body.connector else None,
                    api_key_id=api_key_id,
                    ip=ip,
                )
        except ProvisioningError as exc:
            raise ProvisioningFailed(str(exc)) from exc
        finally:
            _current_tenant.reset(ctx_token)

        connector_connected = result.connector_connected
        if partner.default_seed_template is not None:
            agent_out = ClientAgentOut(
                status="provisioned" if result.agent_provisioned else "already_provisioned"
            )
        if result.agent_provisioned:
            # Same channel the admin promote uses — a worker with a warm
            # cache for this tenant (unlikely for a fresh one) reloads.
            from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL

            try:
                await redis.publish(PROMOTE_CHANNEL, str(mapping.tenant_id))
            except Exception as exc:  # pragma: no cover - stale-cache risk only
                log.warning(
                    "partner.promote_publish_failed",
                    tenant_id=str(mapping.tenant_id),
                    error=str(exc),
                )

    whatsapp = await whatsapp_status(session, mapping.tenant_id)
    return ClientProvisionOut(
        external_client_ref=body.external_client_ref,
        status="provisioned",
        whatsapp=whatsapp,
        agent=agent_out,
        connector_connected=connector_connected,
    )
