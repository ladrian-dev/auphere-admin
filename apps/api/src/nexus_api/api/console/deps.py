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

from .schemas import ClientHealthOut

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


async def client_health(session: AsyncSession, tenant: Tenant) -> ClientHealthOut:
    """Must run inside a tenant-scoped transaction for ``tenant``."""
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
    if tenant.status is not TenantStatus.ACTIVE:
        missing.append("activation")
    return ClientHealthOut(
        whatsapp_connected=phone is not None,
        display_phone_number=phone,
        agent_version=agent_version,
        agent_configured=agent_version is not None,
        ready=not missing,
        missing=missing,
    )


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
    "client_health",
    "client_scope",
    "health_for_tenant",
    "partner_scope",
    "resolve_mapping",
    "unknown_client",
]
