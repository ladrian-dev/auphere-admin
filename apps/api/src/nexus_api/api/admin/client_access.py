"""``/admin/tenants/{tenant_id}/client-access`` y ``…/client-members`` — spec
030, Requisito 1.

El equipo de Auphere enciende la consola lite de un cliente, elige sus
módulos e invita o revoca a sus personas. Dos reglas de esta puerta:

* **El operador se identifica.** El token del panel es de servicio; quién
  actúa viaja en ``X-Operator-Id`` (ADR-034) y se comprueba contra
  ``operator_auth.principals``. Sin operador, no hay cambio: la auditoría tiene
  que nombrar a una persona (``operator:<correo>``), no un prefijo del token.
* **El token de la invitación sale una vez.** Va en el correo y en la
  respuesta (``accept_url``) para que el operador pueda pasarlo a mano si el
  correo no llega; en la base solo queda su hash. ``accept_url`` lo construye
  ``console_link``, como el del correo: el panel vive en otro host y una ruta
  relativa no le sirve para nada.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.api.schemas_client_access import (
    ClientAccessIn,
    ClientAccessOut,
    ClientInvitationOut,
    ClientMemberIn,
    access_out,
    invitation_out,
    send_invitation,
)
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import declare_tenant
from nexus_api.db.models import ClientPhone, OperatorAccount
from nexus_api.services import client_access, client_phones
from nexus_api.services.client_access import ClientAccessError

router = APIRouter(prefix="/tenants", dependencies=[Depends(require_admin_token)])


def _actor(operator: OperatorAccount) -> str:
    return operator_actor(operator)


def _error(exc: ClientAccessError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.info})


# Spec 056 (research R3): los esquemas viven en ``api/schemas_client_access.py``,
# compartidos con la pestaña Acceso de la consola de partners.


@router.get("/{tenant_id}/client-access", response_model=ClientAccessOut)
async def read_client_access(
    tenant_id: uuid.UUID,
    _operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ClientAccessOut:
    try:
        async with session.begin():
            # Production blocks tenant tables without a declared tenant.
            await declare_tenant(session, tenant_id)
            return access_out(await client_access.read_access(session, tenant_id))
    except ClientAccessError as exc:
        raise _error(exc) from None


@router.put("/{tenant_id}/client-access", response_model=ClientAccessOut)
async def set_client_access(
    tenant_id: uuid.UUID,
    body: ClientAccessIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ClientAccessOut:
    try:
        async with session.begin():
            # Production blocks tenant tables without a declared tenant.
            await declare_tenant(session, tenant_id)
            view = await client_access.set_access(
                session,
                tenant_id,
                enabled=body.enabled,
                modules=list(body.modules),
                actor=_actor(operator),
                reservas=body.reservas.choice() if body.reservas is not None else None,
            )
            return access_out(view)
    except ClientAccessError as exc:
        raise _error(exc) from None


@router.post(
    "/{tenant_id}/client-members",
    response_model=ClientInvitationOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_client_member(
    tenant_id: uuid.UUID,
    body: ClientMemberIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ClientInvitationOut:
    try:
        async with session.begin():
            # Production blocks tenant tables without a declared tenant.
            await declare_tenant(session, tenant_id)
            invitation, token = await client_access.invite(
                session, tenant_id, email=body.email, name=body.name, actor=_actor(operator)
            )
            client = await client_access.client_name(session, invitation)
    except ClientAccessError as exc:
        raise _error(exc) from None
    sent = await send_invitation(
        invitation.tenant_id, invitation.email, token, client, invitation.expires_at
    )
    return invitation_out(invitation, token, sent)


@router.post(
    "/{tenant_id}/client-members/{member_id}/resend",
    response_model=ClientInvitationOut,
    status_code=status.HTTP_201_CREATED,
)
async def resend_client_invitation(
    tenant_id: uuid.UUID,
    member_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> ClientInvitationOut:
    try:
        async with session.begin():
            # Production blocks tenant tables without a declared tenant.
            await declare_tenant(session, tenant_id)
            invitation, token = await client_access.resend(
                session, tenant_id, member_id, actor=_actor(operator)
            )
            client = await client_access.client_name(session, invitation)
    except ClientAccessError as exc:
        raise _error(exc) from None
    sent = await send_invitation(
        invitation.tenant_id, invitation.email, token, client, invitation.expires_at
    )
    return invitation_out(invitation, token, sent)


@router.post(
    "/{tenant_id}/client-members/{member_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_client_member(
    tenant_id: uuid.UUID,
    member_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        async with session.begin():
            # Production blocks tenant tables without a declared tenant.
            await declare_tenant(session, tenant_id)
            await client_access.revoke(session, tenant_id, member_id, actor=_actor(operator))
    except ClientAccessError as exc:
        raise _error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Spec 031: los teléfonos de cada persona (R7.4) ────────────────────


class ClientPhoneOut(BaseModel):
    id: uuid.UUID
    display_name: str
    platform: Literal["ios", "android"]
    app_version: str
    last_seen_at: datetime
    enrolled_at: datetime
    revoked_at: datetime | None
    revoked_reason: str | None
    revoked_by: str | None


def _phone_out(p: ClientPhone) -> ClientPhoneOut:
    return ClientPhoneOut(
        id=p.id,
        display_name=p.display_name,
        platform=p.platform,  # type: ignore[arg-type]
        app_version=p.app_version,
        last_seen_at=p.last_seen_at,
        enrolled_at=p.enrolled_at,
        revoked_at=p.revoked_at,
        revoked_reason=p.revoked_reason,
        revoked_by=p.revoked_by,
    )


@router.get("/{tenant_id}/client-members/{member_id}/phones", response_model=list[ClientPhoneOut])
async def list_member_phones(
    tenant_id: uuid.UUID,
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[ClientPhoneOut]:
    """Los teléfonos de una persona del cliente: activos y los últimos cerrados."""
    async with session.begin():
        await declare_tenant(session, tenant_id)
        phones = await client_phones.for_membership(
            session, tenant_id=tenant_id, membership_id=member_id
        )
    return [_phone_out(p) for p in phones]


@router.delete(
    "/{tenant_id}/client-members/{member_id}/phones/{phone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def close_member_phone(
    tenant_id: uuid.UUID,
    member_id: uuid.UUID,
    phone_id: uuid.UUID,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Cierra un teléfono, por ejemplo uno perdido (R7.4). Queda en la auditoría
    con el operador (``operator:<correo>``). Idempotente."""
    async with session.begin():
        await declare_tenant(session, tenant_id)
        phone = await session.get(ClientPhone, phone_id)
        if phone is None or phone.tenant_id != tenant_id or phone.client_membership_id != member_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        client_phones.revoke(session, phone, reason="closed_by_auphere", by=_actor(operator))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
