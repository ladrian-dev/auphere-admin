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

**Spec 031: la misma puerta acepta el teléfono.** Un token HS256 de la app
Auphere Customers (``core.phone_credential``) entra por una segunda rama que
termina en **el mismo** :func:`resolve_client_principal`, así que ninguna ruta
lite cambia su autorización. La fila del teléfono se lee como identidad, igual
que la membresía; de ella salen partner y cuenta (research D3). Cada petición
vuelve a mirar la fila: un teléfono cerrado deja de leer en la siguiente.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core import phone_credential
from nexus_api.core.console_auth import (
    _SERVICE_CLAIM,
    _bearer,
    _require_console_switch,
    _verify_bearer,
)
from nexus_api.db.models import (
    CLIENT_MODULES,
    ClientAccess,
    ClientMembership,
    ClientMemberStatus,
    ClientPhone,
    Partner,
    PartnerStatus,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.db.models.client_access import CONSOLE_V2_MODULES
from nexus_api.desktop_version import MinimumVersion, is_blocked

log = structlog.get_logger(__name__)

#: Como ``client_phones.TOUCH_INTERVAL``: el uso se anota como mucho cada 5 min.
TOUCH_INTERVAL = timedelta(minutes=5)


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
    #: Spec 031: el teléfono desde el que llama, si llama desde la app. ``None``
    #: es la consola web (la BFF).
    phone_id: uuid.UUID | None = None

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


async def _refusal(session: AsyncSession, *, partner_id: uuid.UUID, user_id: str) -> HTTPException:
    """El 403 de quien no entra. Spec 047 (requisito 6.4): a la persona de un
    cliente archivado se le dice (``client_archived``) para que la lite y la app
    lo expliquen; es su propio cliente, no se le revela nada de nadie. Cualquier
    otro motivo es el mismo 403 sin código."""
    async with session.begin():
        membership = await session.scalar(
            sa.select(ClientMembership).where(
                ClientMembership.partner_id == partner_id,
                ClientMembership.user_id == user_id,
            )
        )
        if membership is None or membership.status != ClientMemberStatus.ACTIVE.value:
            return _forbidden()
        partner = await session.get(Partner, partner_id)
        tenant = await session.get(Tenant, membership.tenant_id)
        mapped = await session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.partner_id == partner_id,
                PartnerTenant.tenant_id == membership.tenant_id,
            )
        )
        if (
            partner is not None
            and partner.status == PartnerStatus.ACTIVE.value
            and tenant is not None
            and tenant.status == TenantStatus.ARCHIVED
            and mapped is not None
        ):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail={"code": "client_archived"}
            )
    return _forbidden()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid console token",
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True)
class OpenClient:
    """Un cliente al que sus personas pueden entrar ahora mismo."""

    partner: Partner
    tenant: Tenant
    mapping: PartnerTenant
    access: ClientAccess
    modules: tuple[str, ...]


async def open_client(
    session: AsyncSession, *, partner_id: uuid.UUID, tenant_id: uuid.UUID
) -> OpenClient | None:
    """**La** regla de «este cliente está abierto para sus personas»: partner
    activo, tenant sin archivar, todavía de ese partner, acceso encendido y con
    algún módulo. La usan cada petición (``resolve_client_principal``) y el
    reparto de avisos (``push_fanout``): dos copias de la regla acabarían
    diciendo cosas distintas, y un aviso no puede llegar a quien ya no puede
    leer. No abre transacción: corre en la de quien llama.
    """
    partner = await session.get(Partner, partner_id)
    if partner is None or partner.status != PartnerStatus.ACTIVE.value:
        return None
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.status == TenantStatus.ARCHIVED:
        return None
    mapping = await session.scalar(
        sa.select(PartnerTenant).where(
            PartnerTenant.partner_id == partner_id,
            PartnerTenant.tenant_id == tenant_id,
        )
    )
    if mapping is None:
        return None
    access = await session.get(ClientAccess, tenant_id)
    if access is None or not access.enabled or access.partner_id != partner_id:
        return None
    if not access.ordered_modules():
        return None
    # Spec 047 (``data-model.md`` §10): con la consola nueva, Agentes y Negocio
    # vienen por defecto.
    modules = access.ordered_modules(
        also=CONSOLE_V2_MODULES if partner.console_v2_enabled_at is not None else ()
    )
    return OpenClient(
        partner=partner, tenant=tenant, mapping=mapping, access=access, modules=modules
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
        client = await open_client(session, partner_id=partner_id, tenant_id=membership.tenant_id)
        if client is None:
            return None
    return ClientPrincipal(
        user_id=user_id,
        partner=client.partner,
        membership=membership,
        tenant_id=membership.tenant_id,
        client_ref=client.mapping.external_client_ref,
        client_name=client.mapping.client_name or client.tenant.name,
        modules=client.modules,
        jti=jti,
    )


def _phone_refused(code: str, status_code: int, **info: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, **info})


def _customers_minimum(platform: str) -> MinimumVersion | None:
    """La mínima de la app por plataforma (R13), con las reglas del escritorio."""
    s = get_settings()
    raw = (
        s.customers_app_min_version_ios
        if platform == "ios"
        else s.customers_app_min_version_android
    ).strip()
    if not raw:
        return None
    since = datetime.min.replace(tzinfo=UTC)
    if s.customers_app_min_version_from.strip():
        try:
            since = datetime.fromisoformat(s.customers_app_min_version_from.strip())
            if since.tzinfo is None:
                since = since.replace(tzinfo=UTC)
        except ValueError:
            log.warning("client_auth.bad_min_version_from", value=s.customers_app_min_version_from)
    return MinimumVersion(
        version=raw, reason=s.customers_app_min_version_reason, effective_from=since
    )


async def _resolve_phone(
    token: str,
    *,
    session: AsyncSession,
    platform: str | None,
    app_version: str | None,
) -> ClientPrincipal:
    """La rama del teléfono. Cada paso tiene su respuesta, y la app las distingue:

    * 400 sin ``X-App-Platform`` o ``X-App-Version``: la app siempre las manda.
    * 401 con un token que no vale o con otra generación: renovar.
    * 403 ``phone_closed`` (con motivo): volver a entrar y decir por qué.
    * 403 ``app_update_required``: actualizar (R13).
    * 403 sin código: el acceso de la persona o del cliente ya no vale (R1.5).
    """
    _require_console_switch()
    if platform not in ("ios", "android") or not app_version:
        raise _phone_refused("app_headers_required", status.HTTP_400_BAD_REQUEST)
    try:
        claims = phone_credential.verify_access_token(token)
    except phone_credential.PhoneCredentialError:
        raise _unauthorized() from None

    async with session.begin():
        phone = await session.get(ClientPhone, claims.phone_id)
        if phone is None:
            raise _unauthorized()
        if phone.revoked_at is not None:
            raise _phone_refused(
                "phone_closed", status.HTTP_403_FORBIDDEN, reason=phone.revoked_reason
            )
        if phone.credential_generation != claims.generation:
            raise _unauthorized()
        partner_id, principal_id, phone_id = phone.partner_id, phone.principal_id, phone.id
        last_seen = phone.last_seen_at

    minimum = _customers_minimum(platform)
    if is_blocked(app_version, minimum):
        assert minimum is not None
        raise _phone_refused(
            "app_update_required",
            status.HTTP_403_FORBIDDEN,
            reason=minimum.reason,
            minimum_version=minimum.version,
        )

    principal = await resolve_client_principal(
        session,
        partner_id=partner_id,
        user_id=principal_id,
        jti=f"phone:{phone_id}:{claims.generation}",
    )
    if principal is None:
        raise await _refusal(session, partner_id=partner_id, user_id=principal_id)

    if datetime.now(UTC) - (last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=UTC)) >= (
        TOUCH_INTERVAL
    ):
        async with session.begin():
            await session.execute(
                sa.update(ClientPhone)
                .where(ClientPhone.id == phone_id)
                .values(last_seen_at=datetime.now(UTC))
            )
    return replace(principal, phone_id=phone_id)


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
        app_platform: str | None = Header(default=None, alias="X-App-Platform"),
        app_version: str | None = Header(default=None, alias="X-App-Version"),
    ) -> ClientPrincipal:
        token = _bearer(authorization)
        if phone_credential.looks_like_phone_token(token):
            from_phone = await _resolve_phone(
                token, session=session, platform=app_platform, app_version=app_version
            )
            if any(not from_phone.has(m) for m in modules):
                raise _forbidden()
            structlog.contextvars.bind_contextvars(
                partner=from_phone.partner.slug,
                console_user=from_phone.membership.email,
                console_kind="client_phone",
            )
            return from_phone

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
            raise await _refusal(session, partner_id=partner_id, user_id=payload["sub"])
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
