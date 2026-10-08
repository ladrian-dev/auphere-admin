"""La persona de un cliente ante ``/console/lite/*`` — spec 030 (plan D2, D3).

Es la otra mitad de :mod:`nexus_api.core.console_auth`, y la frontera entre
las dos no depende de que alguien declare bien un permiso:

- :func:`require_console_principal` resuelve SOLO contra
  ``partner_memberships``. Una persona de cliente no está ahí: recibe 403 en
  todas las rutas del partner sin que ninguna se toque.
- :func:`require_client_principal` resuelve SOLO contra
  ``client_memberships``. Un miembro del partner no está ahí: recibe 403 en
  todas las rutas lite.

El token es el mismo que acuña la consola (``{sub, partner_id, role}`` con
la misma clave y 60 s de vida) y pasa por la misma verificación: firma,
caducidad, tope de vida y anti-replay. El claim ``role`` no decide nada: la
tabla en la que está la cuenta decide.

Lo que se comprueba después, y en este orden, porque cada paso necesita el
anterior: membresía activa para ``(partner_id, sub)``, partner activo, tenant
en el partner y no archivado, acceso del cliente encendido, y los módulos que
pide la ruta. **No** se exige ``partners.console_enabled``: ese interruptor es
de la consola del partner, y apagarla no puede dejar fuera a sus clientes.

El cliente sale de la membresía, nunca de la petición. Ninguna ruta lite lleva
``ref``, ``tenant_id`` ni ``partner_id``.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import sqlalchemy as sa
import structlog
from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import _SERVICE_CLAIM, _verify_bearer
from nexus_api.db.models import (
    CLIENT_MODULES,
    ClientAccess,
    ClientMembership,
    ClientMemberStatus,
    Partner,
    PartnerStatus,
    PartnerTenant,
    Tenant,
    TenantStatus,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ClientPrincipal:
    """Una petición verificada de la persona de un cliente.

    ``tenant_id`` y ``client_ref`` salen de la membresía y de
    ``partner_tenants``, nunca del token. ``modules`` es el único permiso que
    tiene: lo que Auphere eligió para su cliente, en el orden de la barra.
    """

    user_id: str
    partner: Partner
    membership: ClientMembership
    tenant_id: uuid.UUID
    client_ref: str
    client_name: str
    modules: tuple[str, ...]
    jti: str

    @property
    def actor(self) -> str:
        """Actor de auditoría: ``client:<correo>``. Se distingue a simple vista
        de ``console:<correo>`` (un miembro del partner) en la Auditoría."""
        return f"client:{self.membership.email}"

    def has(self, module: str) -> bool:
        return module in self.modules


def _forbidden() -> HTTPException:
    # Una sola respuesta para todos los motivos: no se dice si la cuenta no
    # existe, si es de otro partner o si el acceso está apagado.
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No client access")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid console token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def resolve_client_principal(
    session: AsyncSession, *, partner_id: uuid.UUID, user_id: str, jti: str
) -> ClientPrincipal | None:
    """La membresía de cliente detrás de ``(partner_id, user_id)`` con todo lo
    que hace falta para usarla, o ``None`` si algún paso no se cumple.

    Corre en su propia transacción corta. Lee como el usuario de conexión
    (sin la RLS de ``nexus_app``): igual que la resolución de la membresía del
    partner, es identidad, no datos del cliente.
    """
    async with session.begin():
        membership = await session.scalar(
            sa.select(ClientMembership).where(
                ClientMembership.partner_id == partner_id,
                ClientMembership.user_id == user_id,
            )
        )
        if membership is None or membership.status != ClientMemberStatus.ACTIVE.value:
            return None
        partner = await session.get(Partner, partner_id)
        if partner is None or partner.status != PartnerStatus.ACTIVE.value:
            return None
        tenant = await session.get(Tenant, membership.tenant_id)
        if tenant is None or tenant.status == TenantStatus.ARCHIVED:
            return None
        mapping = await session.scalar(
            sa.select(PartnerTenant).where(
                PartnerTenant.partner_id == partner_id,
                PartnerTenant.tenant_id == membership.tenant_id,
            )
        )
        if mapping is None:
            return None
        access = await session.get(ClientAccess, membership.tenant_id)
        if access is None or not access.enabled or access.partner_id != partner_id:
            return None
        modules = access.ordered_modules()
        if not modules:
            return None
    return ClientPrincipal(
        user_id=user_id,
        partner=partner,
        membership=membership,
        tenant_id=membership.tenant_id,
        client_ref=mapping.external_client_ref,
        client_name=mapping.client_name or tenant.name,
        modules=modules,
        jti=jti,
    )


def require_client_principal(
    *modules: str,
) -> Callable[..., Awaitable[ClientPrincipal]]:
    """Dependency factory: ``Depends(require_client_principal("inbox"))``.

    Cada módulo nombrado tiene que estar entre los del cliente. Sin módulos,
    basta con tener acceso (las rutas de identidad y de avisos).
    """
    for module in modules:
        if module not in CLIENT_MODULES:  # error de programación, salta al importar
            raise ValueError(f"unknown client module: {module!r}")

    async def _dependency(
        authorization: str | None = Header(default=None, alias="Authorization"),
        session: AsyncSession = Depends(get_db_session),
        redis: Redis = Depends(get_redis),
    ) -> ClientPrincipal:
        payload = await _verify_bearer(authorization, redis)
        if payload.get("svc") == _SERVICE_CLAIM:
            raise _forbidden()
        try:
            partner_id = uuid.UUID(str(payload.get("partner_id")))
        except (ValueError, TypeError, AttributeError):
            raise _unauthorized() from None

        principal = await resolve_client_principal(
            session, partner_id=partner_id, user_id=payload["sub"], jti=payload["jti"]
        )
        if principal is None:
            raise _forbidden()
        if any(not principal.has(m) for m in modules):
            raise _forbidden()

        structlog.contextvars.bind_contextvars(
            partner=principal.partner.slug,
            console_user=principal.membership.email,
            console_kind="client",
        )
        return principal

    return _dependency


__all__ = ["ClientPrincipal", "require_client_principal", "resolve_client_principal"]
