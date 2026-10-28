"""Ámbito de las rutas lite — spec 030 (plan D2, D5).

Es la contraparte de :func:`nexus_api.api.console.deps.client_scope` para la
persona de un cliente, con una diferencia que es toda la regla: aquí **no hay
``{ref}``**. El cliente sale de la membresía verificada; la ruta no puede
pedir otro aunque quiera.

La ruta no confirma su transacción: la confirma ``lite_scope`` al cerrarse. Lo
que solo debe pasar si se confirma —el aviso de tiempo real— la ruta lo deja en
``scope.after_commit``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.client_auth import ClientPrincipal, require_client_principal
from nexus_api.core.logging_context import bind_tenant
from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
from nexus_api.db.models import Tenant

log = structlog.get_logger(__name__)


def origin_of(principal: ClientPrincipal) -> str:
    """``app`` si la petición llega con la credencial de un teléfono; si no,
    ``lite_web``."""
    return "app" if principal.phone_id is not None else "lite_web"


@dataclass(frozen=True)
class LiteScope:
    """La persona de un cliente dentro de una transacción con su tenant fijado."""

    principal: ClientPrincipal
    tenant: Tenant
    session: AsyncSession
    _after_commit: list[Callable[[], Awaitable[None]]] = field(default_factory=list, repr=False)

    @property
    def origin(self) -> str:
        """Spec 047 (``events.md`` §4): desde dónde escribe la persona, la app
        (su teléfono) o la consola lite web (la BFF)."""
        return origin_of(self.principal)

    @property
    def person_name(self) -> str:
        """Cómo se llama quien escribe, para el aviso al partner."""
        member = self.principal.membership
        return member.display_name or member.email

    def after_commit(self, fn: Callable[[], Awaitable[None]]) -> None:
        """``fn`` corre cuando la transacción se confirma, y nunca si hace
        rollback. Un fallo suyo no tumba la petición: lo escrito ya está."""
        self._after_commit.append(fn)

    async def _run_after_commit(self) -> None:
        for fn in self._after_commit:
            try:
                await fn()
            except Exception as exc:
                log.warning("lite_scope.after_commit_failed", error=str(exc))


def lite_scope(*modules: str) -> Callable[..., AsyncIterator[LiteScope]]:
    """Dependency factory: verifica la persona (y sus ``modules``), abre una
    transacción con ``app.tenant_id`` = su cliente (RLS + contextvar), la
    entrega y, si se confirma, corre lo que la ruta dejó en ``after_commit``."""
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
                scope = LiteScope(principal=principal, tenant=tenant, session=session)
                yield scope
            # Solo se llega aquí si el bloque confirmó: una excepción de la ruta
            # o del commit hace rollback y salta esta línea.
            await scope._run_after_commit()
        finally:
            _current_tenant.reset(token)

    return _dependency
