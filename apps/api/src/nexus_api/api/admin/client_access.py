"""``/admin/tenants/{tenant_id}/client-access`` y ``…/client-members`` — spec
030, Requisito 1.

El equipo de Auphere enciende la consola lite de un cliente, elige sus
módulos e invita o revoca a sus personas. Dos reglas de esta puerta:

* **El operador se identifica.** El token del panel es de servicio; quién
  actúa viaja en ``X-Operator-Id`` (ADR-034) y se comprueba contra
  ``operator_auth.principals``. Sin operador, no hay cambio: la auditoría tiene
  que nombrar a una persona (``operator:<correo>``), no un prefijo del token.
* **El token de la invitación sale una vez.** Va en el correo y en la
  respuesta (``accept_path``) para que el operador pueda pasarlo a mano si el
  correo no llega; en la base solo queda su hash.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import declare_tenant
from nexus_api.db.models import ClientPhone, OperatorAccount
from nexus_api.services import client_access, client_phones
from nexus_api.services.client_access import AccessView, ClientAccessError
from nexus_api.services.client_invitation_email import send_client_invitation
from nexus_api.services.reservations import admin as reservations_admin

router = APIRouter(prefix="/tenants", dependencies=[Depends(require_admin_token)])

INVITE_ACCEPT_PATH = "/invite/{token}"


def _actor(operator: OperatorAccount) -> str:
    return operator_actor(operator)


def _error(exc: ClientAccessError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.info})


class PartnerRefOut(BaseModel):
    id: uuid.UUID
    name: str


class ClientMemberOut(BaseModel):
    id: uuid.UUID
    kind: Literal["member", "invitation"]
    email: str
    name: str | None
    status: str
    since: datetime | None = None
    expires_at: datetime | None = None


class PendingAgentOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    version: int


class ClientReservasOut(BaseModel):
    """Spec 043: el modo de Reservas del cliente (``null`` si nunca lo tuvo)."""

    mode: Literal["services", "capacity"]
    capacity_kind: str | None
    live_future: int
    agents_pending_promotion: list[PendingAgentOut]


class ClientAccessOut(BaseModel):
    eligible: bool
    ineligible_reason: str | None
    partner: PartnerRefOut | None
    whatsapp_connected: bool
    enabled: bool
    modules: list[str]
    members: list[ClientMemberOut]
    reservas: ClientReservasOut | None = None


class ClientReservasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["services", "capacity"]
    capacity_kind: Literal["restaurant", "bar", "classes", "tours", "rooms", "spa"] | None = None
    on_live: Literal["refuse", "cancel_and_notify"] = "refuse"


class ClientAccessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    modules: list[Literal["panel", "inbox", "reservas", "usage"]] = Field(
        default_factory=list, max_length=4
    )
    reservas: ClientReservasIn | None = None


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ClientMemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A propósito no es ``EmailStr``: ese validador rechaza dominios de uso
    # especial y aquí basta con la forma. La prueba de verdad es que el enlace
    # llega y la persona lo abre.
    email: str = Field(max_length=255)
    name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _shape(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("invalid e-mail")
        return v


class ClientInvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    expires_at: datetime
    accept_path: str
    email_sent: bool


def _out(view: AccessView) -> ClientAccessOut:
    return ClientAccessOut(
        eligible=view.eligible,
        ineligible_reason=view.ineligible_reason,
        partner=PartnerRefOut(id=view.partner.id, name=view.partner.name) if view.partner else None,
        whatsapp_connected=view.whatsapp_connected,
        enabled=view.enabled,
        modules=list(view.modules),
        reservas=ClientReservasOut.model_validate(view.reservas) if view.reservas else None,
        members=[
            ClientMemberOut(
                id=m.id,
                kind="member" if m.kind == "member" else "invitation",
                email=m.email,
                name=m.name,
                status=m.status,
                since=m.since,
                expires_at=m.expires_at,
            )
            for m in view.members
        ],
    )


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
            return _out(await client_access.read_access(session, tenant_id))
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
                reservas=reservations_admin.Choice(
                    mode=body.reservas.mode,
                    capacity_kind=body.reservas.capacity_kind,
                    on_live=body.reservas.on_live,
                )
                if body.reservas is not None
                else None,
            )
            return _out(view)
    except ClientAccessError as exc:
        raise _error(exc) from None


async def _send(
    tenant_id: uuid.UUID, email: str, token: str, client: str, expires_at: datetime
) -> bool:
    # El correo es del cliente (spec 051, garantía 6): su registro lleva el tenant.
    return await send_client_invitation(
        email=email,
        client_name=client,
        accept_path=INVITE_ACCEPT_PATH.format(token=token),
        expires_at=expires_at,
        tenant_id=tenant_id,
    )


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
    sent = await _send(invitation.tenant_id, invitation.email, token, client, invitation.expires_at)
    return ClientInvitationOut(
        id=invitation.id,
        email=invitation.email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        accept_path=INVITE_ACCEPT_PATH.format(token=token),
        email_sent=sent,
    )


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
    sent = await _send(invitation.tenant_id, invitation.email, token, client, invitation.expires_at)
    return ClientInvitationOut(
        id=invitation.id,
        email=invitation.email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        accept_path=INVITE_ACCEPT_PATH.format(token=token),
        email_sent=sent,
    )


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
