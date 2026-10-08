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

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.services import client_access
from nexus_api.services.client_access import AccessView, ClientAccessError
from nexus_api.services.client_invitation_email import send_client_invitation

router = APIRouter(prefix="/tenants", dependencies=[Depends(require_admin_token)])

INVITE_ACCEPT_PATH = "/invite/{token}"


async def require_operator(
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
    session: AsyncSession = Depends(get_db_session),
) -> OperatorAccount:
    """El operador de la sesión del panel, nunca el token (ADR-034). Mismas
    respuestas que la suplantación: 400 si falta o no es un operador."""
    raw = (x_operator_id or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Operator-Id header"
        )
    try:
        operator_id = uuid.UUID(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        ) from None
    async with session.begin():
        account = await session.get(OperatorAccount, operator_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        )
    return account


def _actor(operator: OperatorAccount) -> str:
    return f"operator:{operator.email}"


def _error(exc: ClientAccessError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


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


class ClientAccessOut(BaseModel):
    eligible: bool
    ineligible_reason: str | None
    partner: PartnerRefOut | None
    whatsapp_connected: bool
    enabled: bool
    modules: list[str]
    members: list[ClientMemberOut]


class ClientAccessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    modules: list[Literal["panel", "inbox", "usage"]] = Field(default_factory=list, max_length=3)


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
            view = await client_access.set_access(
                session,
                tenant_id,
                enabled=body.enabled,
                modules=list(body.modules),
                actor=_actor(operator),
            )
            return _out(view)
    except ClientAccessError as exc:
        raise _error(exc) from None


async def _send(
    invitation_id: uuid.UUID, email: str, token: str, client: str, expires_at: datetime
) -> bool:
    return await send_client_invitation(
        email=email,
        client_name=client,
        accept_path=INVITE_ACCEPT_PATH.format(token=token),
        expires_at=expires_at,
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
            invitation, token = await client_access.invite(
                session, tenant_id, email=body.email, name=body.name, actor=_actor(operator)
            )
            client = await client_access.client_name(session, invitation)
    except ClientAccessError as exc:
        raise _error(exc) from None
    sent = await _send(invitation.id, invitation.email, token, client, invitation.expires_at)
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
            invitation, token = await client_access.resend(
                session, tenant_id, member_id, actor=_actor(operator)
            )
            client = await client_access.client_name(session, invitation)
    except ClientAccessError as exc:
        raise _error(exc) from None
    sent = await _send(invitation.id, invitation.email, token, client, invitation.expires_at)
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
            await client_access.revoke(session, tenant_id, member_id, actor=_actor(operator))
    except ClientAccessError as exc:
        raise _error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
