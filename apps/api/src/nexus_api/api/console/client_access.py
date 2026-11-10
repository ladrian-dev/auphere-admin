"""``/console/clients/{ref}/client-access`` y ``…/client-members`` — spec 056
(Requisito 3, D3, D4; research R3; ``contracts/api.md``).

La pestaña «Acceso» de la ficha del cliente en la consola de partners: el owner o
el admin del partner enciende la consola de su cliente, elige sus módulos e
invita o revoca a sus personas. Hace **exactamente** lo que hace la del panel
(``api/admin/client_access.py``), Bandeja incluida y sin aprobación de Auphere
(D3, decisión del owner del 2026-11-07), porque llama a los mismos servicios
(``services/client_access.py``) con las mismas reglas. Lo que cambia:

* **Quién firma.** ``principal.actor`` (``console:<correo>``), no el operador. La
  auditoría lo dice con la frase «{actor} cambió…» (0225).
* **El permiso.** ``client_access:manage``: owner y admin (D4). No es
  ``clients:write``, que tiene el builder.
* **El cliente es suyo.** ``ref`` → tenant con ``resolve_mapping`` (404 opaco), y
  además el partner del acceso tiene que ser el del principal; si no, el mismo
  404 (3.10).
* **Sin ``client_scope``.** Ese ámbito baja a ``nexus_app``, que no tiene permiso
  sobre ``console_auth.*``, y ``invite`` y el cierre de sesiones lo tocan. Se hace
  como el panel: ``declare_tenant`` dentro de la transacción.
* **Un límite al invitar.** ``console_client_invites_per_minute`` por partner, en
  invitar y en reenviar: cada una manda un correo, y Resend se comparte.

**El riesgo aceptado en D3**, dicho tal cual: un partner puede invitar a una
persona suya (con un correo que no sea de su equipo) y, con la Bandeja encendida,
leer las conversaciones del cliente, que es lo que C8 prohíbe. Estas rutas no
devuelven nada de la Bandeja (ni conversaciones, ni contactos, ni avisos: 4.2), y
``invite`` rechaza el correo de una cuenta del partner o de otro cliente.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.api.schemas_client_access import (
    ClientAccessIn,
    ClientAccessPartnerOut,
    ClientInvitationOut,
    ClientMemberIn,
    ClientMemberRevokedOut,
    invitation_out,
    member_out,
    partner_access_out,
    send_invitation,
)
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.rate_limit import allow
from nexus_api.core.tenant_context import declare_tenant
from nexus_api.services import client_access
from nexus_api.services.client_access import AccessView, ClientAccessError

from .deps import ClientRef, resolve_mapping, unknown_client

router = APIRouter()

MANAGE = require_console_principal("client_access:manage")


def _error(exc: ClientAccessError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.info})


async def _own(
    session: AsyncSession, principal: ConsolePrincipal, tenant_id: uuid.UUID
) -> AccessView:
    """El acceso del cliente, si es del partner del principal. Dentro de la
    transacción, con el tenant ya declarado."""
    view = await client_access.read_access(session, tenant_id)
    if view.partner is None or view.partner.id != principal.partner.id:
        raise unknown_client()
    return view


async def _invites_allowed(redis: Redis, principal: ConsolePrincipal) -> None:
    if not await allow(
        redis,
        key=f"console:client_invite:{principal.partner.id}",
        per_minute=get_settings().console_client_invites_per_minute,
        surface="console",
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "rate_limited"}
        )


@router.get("/clients/{ref}/client-access", response_model=ClientAccessPartnerOut)
async def read_client_access(
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(MANAGE),
    session: AsyncSession = Depends(get_db_session),
) -> ClientAccessPartnerOut:
    mapping = await resolve_mapping(session, principal, ref)
    async with session.begin():
        await declare_tenant(session, mapping.tenant_id)
        return partner_access_out(await _own(session, principal, mapping.tenant_id))


@router.put("/clients/{ref}/client-access", response_model=ClientAccessPartnerOut)
async def set_client_access(
    body: ClientAccessIn,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(MANAGE),
    session: AsyncSession = Depends(get_db_session),
) -> ClientAccessPartnerOut:
    mapping = await resolve_mapping(session, principal, ref)
    try:
        async with session.begin():
            await declare_tenant(session, mapping.tenant_id)
            await _own(session, principal, mapping.tenant_id)
            view = await client_access.set_access(
                session,
                mapping.tenant_id,
                enabled=body.enabled,
                modules=list(body.modules),
                actor=principal.actor,
                reservas=body.reservas.choice() if body.reservas is not None else None,
            )
            return partner_access_out(view)
    except ClientAccessError as exc:
        raise _error(exc) from None


@router.post(
    "/clients/{ref}/client-members",
    response_model=ClientInvitationOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_client_member(
    body: ClientMemberIn,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(MANAGE),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ClientInvitationOut:
    mapping = await resolve_mapping(session, principal, ref)
    await _invites_allowed(redis, principal)
    try:
        async with session.begin():
            await declare_tenant(session, mapping.tenant_id)
            await _own(session, principal, mapping.tenant_id)
            invitation, token = await client_access.invite(
                session,
                mapping.tenant_id,
                email=body.email,
                name=body.name,
                actor=principal.actor,
            )
            client = await client_access.client_name(session, invitation)
    except ClientAccessError as exc:
        raise _error(exc) from None
    # Tras confirmar, como el panel: un rollback no deja un enlace en un buzón.
    sent = await send_invitation(
        invitation.tenant_id, invitation.email, token, client, invitation.expires_at
    )
    return invitation_out(invitation, token, sent)


@router.post(
    "/clients/{ref}/client-members/{member_id}/resend",
    response_model=ClientInvitationOut,
    status_code=status.HTTP_201_CREATED,
)
async def resend_client_invitation(
    member_id: uuid.UUID,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(MANAGE),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> ClientInvitationOut:
    mapping = await resolve_mapping(session, principal, ref)
    await _invites_allowed(redis, principal)
    try:
        async with session.begin():
            await declare_tenant(session, mapping.tenant_id)
            await _own(session, principal, mapping.tenant_id)
            invitation, token = await client_access.resend(
                session, mapping.tenant_id, member_id, actor=principal.actor
            )
            client = await client_access.client_name(session, invitation)
    except ClientAccessError as exc:
        raise _error(exc) from None
    sent = await send_invitation(
        invitation.tenant_id, invitation.email, token, client, invitation.expires_at
    )
    return invitation_out(invitation, token, sent)


@router.post(
    "/clients/{ref}/client-members/{member_id}/revoke",
    response_model=ClientMemberRevokedOut,
)
async def revoke_client_member(
    member_id: uuid.UUID,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(MANAGE),
    session: AsyncSession = Depends(get_db_session),
) -> ClientMemberRevokedOut:
    """Retira una invitación o a una persona; a una persona se le cierran las
    sesiones y los teléfonos en la misma transacción (3.7). Idempotente."""
    mapping = await resolve_mapping(session, principal, ref)
    try:
        async with session.begin():
            await declare_tenant(session, mapping.tenant_id)
            await _own(session, principal, mapping.tenant_id)
            await client_access.revoke(session, mapping.tenant_id, member_id, actor=principal.actor)
            view = await client_access.read_access(session, mapping.tenant_id)
    except ClientAccessError as exc:
        raise _error(exc) from None
    row = next((m for m in view.members if m.id == member_id), None)
    if row is None:  # una invitación ya aceptada: su persona es otra fila
        raise _error(ClientAccessError("unknown_member", 404))
    return ClientMemberRevokedOut(member=member_out(row))
