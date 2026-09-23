"""Shared dependencies of the partner console.

The one rule every ``/console/*`` endpoint obeys (PLAN-CONSOLE-V1 CP-04):
**no endpoint accepts a ``tenant_id`` or a ``partner_id`` from the
client** — not in the path, the query, the body or a header. The partner
comes from the verified principal; the tenant comes from
``external_client_ref`` → ``partner_tenants`` under that partner. An
unknown ref is an opaque 404: we never confirm that a client exists for
someone else.

:func:`client_scope` is the console's counterpart of
``api/deps.py::scoped_session_from_path`` — same transaction + RLS +
contextvar ceremony, different way of choosing the tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.repositories.partner import PartnerTenantRepository

from .schemas import ClientHealthOut, ClientSetupDetailOut, ClientSetupOut, SetupStep

#: Path parameter every client-scoped route uses.
ClientRef = Path(
    ...,
    min_length=1,
    max_length=255,
    description="The partner's own reference for the client (external_client_ref).",
)


def unknown_client() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown client reference")


@dataclass(frozen=True)
class ClientScope:
    """A resolved client inside an open, tenant-scoped transaction."""

    principal: ConsolePrincipal
    mapping: PartnerTenant
    tenant: Tenant
    session: AsyncSession

    @property
    def ref(self) -> str:
        return self.mapping.external_client_ref


async def resolve_mapping(
    session: AsyncSession, principal: ConsolePrincipal, ref: str
) -> PartnerTenant:
    """``partner_tenants`` row behind ``ref`` for the principal's partner,
    or opaque 404. Runs its own short transaction."""
    async with session.begin():
        mapping = await PartnerTenantRepository(session).get_mapping(principal.partner.id, ref)
    if mapping is None:
        raise unknown_client()
    return mapping


def client_scope(*required: str) -> Callable[..., AsyncIterator[ClientScope]]:
    """Dependency factory: resolve ``{ref}`` under the principal, open a
    tenant-scoped transaction (RLS + contextvar) and yield the scope.

    ``required`` are the console permissions the route needs; the
    principal dependency enforces them before the mapping is even read.
    """
    principal_dep = require_console_principal(*required)

    async def _dependency(
        ref: str = ClientRef,
        principal: ConsolePrincipal = Depends(principal_dep),
        session: AsyncSession = Depends(get_db_session),
    ) -> AsyncIterator[ClientScope]:
        mapping = await resolve_mapping(session, principal, ref)
        token = _current_tenant.set(mapping.tenant_id)
        try:
            async with session.begin():
                tenant = await session.get(Tenant, mapping.tenant_id)
                if tenant is None:  # pragma: no cover - FK RESTRICT guarantees the row
                    raise unknown_client()
                await apply_tenant_to_session(session, mapping.tenant_id)
                bind_tenant(mapping.tenant_id)
                yield ClientScope(
                    principal=principal, mapping=mapping, tenant=tenant, session=session
                )
        finally:
            _current_tenant.reset(token)

    return _dependency


@dataclass(frozen=True)
class PartnerScope:
    """Open transaction with ``app.partner_id`` set (playbook / wallet)."""

    principal: ConsolePrincipal
    session: AsyncSession


def partner_scope(*required: str) -> Callable[..., AsyncIterator[PartnerScope]]:
    """Partner-scoped transaction. Body never carries ``partner_id``."""
    principal_dep = require_console_principal(*required)

    async def _dependency(
        principal: ConsolePrincipal = Depends(principal_dep),
        session: AsyncSession = Depends(get_db_session),
    ) -> AsyncIterator[PartnerScope]:
        async with session.begin():
            await apply_partner_to_session(session, principal.partner.id)
            yield PartnerScope(principal=principal, session=session)

    return _dependency


# ── health (used by list, detail and create) ───────────────────────────


async def out_of_quota(partner_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    """Spec 016 (R2.1): the ONE reading of «this client cannot take a turn
    for lack of quota» — ``quota_state``, the same the channel gate uses.
    Opens its own partner-scoped session (the ledger is invisible from a
    tenant-scoped one). Fails closed."""
    from nexus_api.metering.wallet import quota_state

    return (await quota_state(partner_id, [tenant_id])).get(tenant_id, True)


async def client_health(
    session: AsyncSession, tenant: Tenant, *, out_of_quota: bool = False
) -> ClientHealthOut:
    """Must run inside a tenant-scoped transaction for ``tenant``.

    ``out_of_quota`` adds ``"quota"`` to ``missing`` (after ``"whatsapp"``,
    before ``"activation"``) but does NOT clear ``ready``: a ready client can
    run out of quota, and the screen must say both things.
    """
    phone = await session.scalar(
        sa.select(Channel.provider_identifier)
        .where(Channel.type == ChannelType.WHATSAPP, Channel.status == ChannelStatus.ACTIVE)
        .limit(1)
    )
    agent_version = await session.scalar(
        sa.select(AgentConfig.version)
        .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        .limit(1)
    )
    missing: list[str] = []
    if agent_version is None:
        missing.append("agent")
    if phone is None:
        missing.append("whatsapp")
    if out_of_quota:
        missing.append("quota")
    if tenant.status is not TenantStatus.ACTIVE:
        missing.append("activation")
    return ClientHealthOut(
        whatsapp_connected=phone is not None,
        display_phone_number=phone,
        agent_version=agent_version,
        agent_configured=agent_version is not None,
        ready=not [m for m in missing if m != "quota"],
        missing=missing,
    )


def sector_of(seed_template_ref: str | None) -> str | None:
    """Spec 017 (R1, R5): the sector is the vertical of the template the
    agent was seeded from — the same reading ``GET /console/seed-templates``
    gives (``panaderia_v1`` → ``panaderia``). ``None`` for a hand-written agent."""
    if not seed_template_ref:
        return None
    name = seed_template_ref
    return name.rsplit("_v", 1)[0] if "_v" in name else name


async def client_sector(session: AsyncSession) -> str | None:
    """Inside a tenant-scoped transaction: the active version's template,
    or the newest staged one when nothing is active yet."""
    ref = await session.scalar(
        sa.select(AgentConfig.seed_template_ref)
        .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        .order_by(AgentConfig.version.desc())
        .limit(1)
    )
    if ref is None:
        ref = await session.scalar(
            sa.select(AgentConfig.seed_template_ref)
            .where(AgentConfig.status == AgentConfigStatus.STAGED)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    return sector_of(ref)


_SETUP_ORDER: tuple[SetupStep, ...] = ("agent", "channel", "quota", "activation")


def client_setup(*, agent: bool, channel: bool, quota: bool, active: bool) -> ClientSetupOut:
    """Spec 017 (R9.1): the four steps as the list shows them."""
    return ClientSetupOut(agent=agent, channel=channel, quota=quota, active=active)


def client_setup_detail(
    *, agent: bool, channel: bool, quota: bool, active: bool
) -> ClientSetupDetailOut:
    """Spec 017 (R1.1/R1.3): the four steps and the first pending one, in
    the fixed order agent → channel → quota → activation; ``None`` when
    the client is serving."""
    done = {"agent": agent, "channel": channel, "quota": quota, "activation": active}
    nxt: SetupStep | None = next((k for k in _SETUP_ORDER if not done[k]), None)
    return ClientSetupDetailOut(agent=agent, channel=channel, quota=quota, active=active, next=nxt)


async def active_customer_channel(session: AsyncSession) -> bool:
    """Inside a tenant-scoped transaction: is there any ACTIVE channel that
    faces customers? (WhatsApp today; the Playground never counts.)"""
    from nexus_api.services.console_traffic import customer_facing_channel

    found = await session.scalar(
        sa.select(Channel.id)
        .where(Channel.status == ChannelStatus.ACTIVE, customer_facing_channel())
        .limit(1)
    )
    return found is not None


async def health_for_tenant(session: AsyncSession, tenant: Tenant) -> ClientHealthOut:
    """Own short scoped transaction — for callers outside a client scope
    (the list endpoint iterates the partner's clients)."""
    token = _current_tenant.set(tenant.id)
    try:
        async with session.begin():
            await apply_tenant_to_session(session, tenant.id)
            return await client_health(session, tenant)
    finally:
        _current_tenant.reset(token)


__all__ = [
    "ClientRef",
    "ClientScope",
    "PartnerScope",
    "active_customer_channel",
    "client_health",
    "client_scope",
    "client_sector",
    "client_setup",
    "client_setup_detail",
    "health_for_tenant",
    "out_of_quota",
    "partner_scope",
    "resolve_mapping",
    "unknown_client",
]
