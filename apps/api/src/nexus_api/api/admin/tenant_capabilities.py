"""Admin — a client's capabilities (spec 037).

The operator panel shows the same «Habilidades» as the partner console's
client page. Rather than a second implementation, this router runs the
console's own reading and one-change-per-call write
(``api/console/capabilities_client.py``) on a ``ClientScope`` built for the
client's tenant: same names, same groups, same draft rules, same audit row —
signed by the operator (``operator:<email>``, ADR-034) instead of a partner
person. The client is read and written under its own GUC.

Only ``principal.actor`` of the scope is used by that code; the shim below
provides exactly that, and nothing that could pass for a partner identity.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.console import capabilities_client as console_capabilities
from nexus_api.api.console.deps import ClientScope
from nexus_api.api.console.schemas_capabilities_client import (
    CapabilitiesOut,
    CapabilityUpdatedOut,
    CapabilityUpdateIn,
)
from nexus_api.core.console_auth import ConsolePrincipal
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OperatorAccount, PartnerTenant, Tenant
from nexus_api.db.models.agent import Agent, AgentStatus

router = APIRouter(dependencies=[Depends(require_admin_token)])

_PANEL_ACTOR = "operator:panel"


@dataclass(frozen=True)
class _OperatorActor:
    """What the console code reads from a principal: who signs the audit."""

    actor: str


async def _scope_for(
    session: AsyncSession, tenant_id: uuid.UUID, agent: uuid.UUID | None, actor: str
) -> ClientScope:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_tenant")
    if agent is not None:
        found = await session.get(Agent, agent)
        if (
            found is None
            or found.tenant_id != tenant_id
            or found.status != AgentStatus.ACTIVE.value
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
    return ClientScope(
        principal=cast(ConsolePrincipal, _OperatorActor(actor=actor)),
        # No partner mapping: a direct client has none, and this code path
        # never reads it (only ``ref``, which the panel does not use).
        mapping=cast(PartnerTenant, None),
        tenant=tenant,
        session=session,
        agent_id=agent,
    )


@router.get("/tenants/{tenant_id}/capabilities", response_model=CapabilitiesOut)
async def get_capabilities(
    tenant_id: uuid.UUID,
    all: bool = Query(default=False),
    agent: uuid.UUID | None = Query(default=None),
) -> CapabilitiesOut:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        scope = await _scope_for(s, tenant_id, agent, _PANEL_ACTOR)
        return await console_capabilities.list_capabilities(q=None, all=all, lang="es", scope=scope)


@router.put("/tenants/{tenant_id}/capabilities", response_model=CapabilityUpdatedOut)
async def put_capability(
    tenant_id: uuid.UUID,
    body: CapabilityUpdateIn,
    agent: uuid.UUID | None = Query(default=None),
    operator: OperatorAccount = Depends(require_operator),
) -> CapabilityUpdatedOut:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        scope = await _scope_for(s, tenant_id, agent, operator_actor(operator))
        return await console_capabilities.update_capability(body, scope)
