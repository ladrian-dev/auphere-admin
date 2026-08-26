"""Admin F4 inbox — tickets persistidos desde POST /console/support/tickets.

``partner_id`` nunca viaja en el cuerpo: filtro de query o path.
Listado unscoped (dueño de tabla, como GET /admin/partners).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminTicketListQuery(BaseModel):
    """Query extra=forbid. ``partner_id`` es filtro, no GUC ni cuerpo."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, pattern="^(open|pending|closed)$")
    partner_id: uuid.UUID | None = None


class AdminTicketStatusIn(BaseModel):
    """Solo ``status``. El partner sale del ticket, nunca del cuerpo."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(open|pending|closed)$")


class AdminTicketEventOut(BaseModel):
    id: uuid.UUID
    kind: str
    from_status: str | None
    to_status: str | None
    actor: str
    created_at: datetime


class AdminTicketLinksOut(BaseModel):
    consumo: str
    modelos: str
    conocimiento: str
    auditoria: str


class AdminTicketOut(BaseModel):
    id: uuid.UUID
    ticket_ref: str
    partner_id: uuid.UUID
    partner_name: str
    partner_slug: str
    category: str
    topic: str
    sla: str
    status: str
    client_ref: str | None
    need: str
    checked: list[str]
    alternative: str | None
    bridge: bool
    opened_by: str
    opened_at: datetime
    created_at: datetime
    updated_at: datetime


class AdminTicketDetailOut(AdminTicketOut):
    events: list[AdminTicketEventOut]
    links: AdminTicketLinksOut


__all__ = [
    "AdminTicketDetailOut",
    "AdminTicketEventOut",
    "AdminTicketLinksOut",
    "AdminTicketListQuery",
    "AdminTicketOut",
    "AdminTicketStatusIn",
]
