"""Ámbito de las rutas lite — spec 030 (plan D2, D5).

Es la contraparte de :func:`nexus_api.api.console.deps.client_scope` para la
persona de un cliente, con una diferencia que es toda la regla: aquí **no hay
``{ref}``**. El cliente sale de la membresía verificada; la ruta no puede
pedir otro aunque quiera.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.client_auth import ClientPrincipal, require_client_principal
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
from nexus_api.db.models import Tenant


@dataclass(frozen=True)
class LiteScope:
    """La persona de un cliente dentro de una transacción con su tenant fijado."""

    principal: ClientPrincipal
    tenant: Tenant
    session: AsyncSession


def lite_scope(*modules: str) -> Callable[..., AsyncIterator[LiteScope]]:
    """Dependency factory: verifica la persona (y sus ``modules``), abre una
    transacción con ``app.tenant_id`` = su cliente (RLS + contextvar) y la
    entrega."""
    principal_dep = require_client_principal(*modules)

    async def _dependency(
        principal: ClientPrincipal = Depends(principal_dep),
        session: AsyncSession = Depends(get_db_session),
    ) -> AsyncIterator[LiteScope]:
        token = _current_tenant.set(principal.tenant_id)
        try:
            async with session.begin():
                tenant = await session.get(Tenant, principal.tenant_id)
                if tenant is None:  # pragma: no cover - la membresía lo garantiza
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
                await apply_tenant_to_session(session, principal.tenant_id)
                bind_tenant(principal.tenant_id)
                yield LiteScope(principal=principal, tenant=tenant, session=session)
        finally:
            _current_tenant.reset(token)

    return _dependency
