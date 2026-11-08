"""Los esquemas del acceso de un cliente a su consola, compartidos por el panel
(``api/admin/client_access.py``) y la consola de partners
(``api/console/client_access.py``). Spec 030 (Requisito 1) y spec 056
(Requisito 3, research R3).

Las dos puertas llaman a los **mismos** servicios (``services/client_access.py``)
y hablan la misma forma. La única diferencia: la salida del partner no lleva
``partner`` (es el suyo, y su id no viaja por ``/console/*``).

Los módulos entran como texto y los decide el servicio: ``agents``, ``business``
o cualquier otro nombre dan ``422 unknown_module`` (spec 056, requisito 2.3), no
el 422 genérico de la validación.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus_api.db.models import ClientInvitation
from nexus_api.services.client_access import AccessView, MemberRow
from nexus_api.services.client_invitation_email import send_client_invitation
from nexus_api.services.email_catalog import console_link
from nexus_api.services.reservations import admin as reservations_admin

INVITE_ACCEPT_PATH = "/invite/{token}"


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


class OtherCalendarAgentOut(BaseModel):
    agent_id: uuid.UUID
    name: str


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
    #: Ya reservan con un conector: activar Reservas no les da una segunda agenda.
    agents_with_other_calendar: list[OtherCalendarAgentOut] = []


class ClientAccessPartnerOut(BaseModel):
    """Lo que ve el partner (spec 056, ``contracts/api.md``): la forma del panel sin
    ``partner``. Nada de la Bandeja: ni conversaciones, ni contactos, ni avisos."""

    eligible: bool
    ineligible_reason: str | None
    whatsapp_connected: bool
    enabled: bool
    modules: list[str]
    members: list[ClientMemberOut]
    reservas: ClientReservasOut | None = None


class ClientAccessOut(ClientAccessPartnerOut):
    """Lo que ve el operador: lo mismo, con el partner del cliente."""

    partner: PartnerRefOut | None


class ClientReservasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["services", "capacity"]
    capacity_kind: Literal["restaurant", "bar", "classes", "tours", "rooms", "spa"] | None = None
    on_live: Literal["refuse", "cancel_and_notify"] = "refuse"

    def choice(self) -> reservations_admin.Choice:
        return reservations_admin.Choice(
            mode=self.mode, capacity_kind=self.capacity_kind, on_live=self.on_live
        )


class ClientAccessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    #: Texto, no un ``Literal``: el servicio responde ``unknown_module`` a lo que no
    #: es de hoy (``agents`` y ``business`` incluidos).
    modules: list[str] = Field(default_factory=list, max_length=8)
    reservas: ClientReservasIn | None = None

    @field_validator("modules")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        if any(len(m) > 32 for m in v):
            raise ValueError("module name too long")
        return v


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
    # Lo que se pasa a mano: el enlace completo, el mismo que lleva el correo.
    accept_url: str
    email_sent: bool


class ClientMemberRevokedOut(BaseModel):
    """Spec 056 (``contracts/api.md``): revocar desde el partner devuelve la fila,
    ya revocada, para que la lista se pinte sin otra lectura."""

    member: ClientMemberOut


def invitation_out(invitation: ClientInvitation, token: str, sent: bool) -> ClientInvitationOut:
    path = INVITE_ACCEPT_PATH.format(token=token)
    return ClientInvitationOut(
        id=invitation.id,
        email=invitation.email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        accept_path=path,
        accept_url=console_link(path),
        email_sent=sent,
    )


def member_out(m: MemberRow) -> ClientMemberOut:
    return ClientMemberOut(
        id=m.id,
        kind="member" if m.kind == "member" else "invitation",
        email=m.email,
        name=m.name,
        status=m.status,
        since=m.since,
        expires_at=m.expires_at,
    )


def partner_access_out(view: AccessView) -> ClientAccessPartnerOut:
    return ClientAccessPartnerOut(
        eligible=view.eligible,
        ineligible_reason=view.ineligible_reason,
        whatsapp_connected=view.whatsapp_connected,
        enabled=view.enabled,
        modules=list(view.modules),
        reservas=ClientReservasOut.model_validate(view.reservas) if view.reservas else None,
        members=[member_out(m) for m in view.members],
    )


def access_out(view: AccessView) -> ClientAccessOut:
    return ClientAccessOut(
        **partner_access_out(view).model_dump(),
        partner=PartnerRefOut(id=view.partner.id, name=view.partner.name) if view.partner else None,
    )


async def send_invitation(
    tenant_id: uuid.UUID, email: str, token: str, client: str, expires_at: datetime
) -> bool:
    """El correo de la invitación, **después** de confirmar la transacción: un
    rollback no deja un enlace en un buzón."""
    # El correo es del cliente (spec 051, garantía 6): su registro lleva el tenant.
    return await send_client_invitation(
        email=email,
        client_name=client,
        accept_path=INVITE_ACCEPT_PATH.format(token=token),
        expires_at=expires_at,
        tenant_id=tenant_id,
    )


__all__ = [
    "INVITE_ACCEPT_PATH",
    "ClientAccessIn",
    "ClientAccessOut",
    "ClientAccessPartnerOut",
    "ClientInvitationOut",
    "ClientMemberIn",
    "ClientMemberOut",
    "ClientMemberRevokedOut",
    "ClientReservasIn",
    "ClientReservasOut",
    "access_out",
    "invitation_out",
    "member_out",
    "partner_access_out",
    "send_invitation",
]
