"""``/console/lite/notifications`` — la campana de la persona de un cliente
(spec 030, R15).

La misma lógica que la campana del partner (:mod:`..notifications`) con otro
:class:`Viewer`: avisos ``audience = client`` de SU cliente y nada más —ni
los del partner, ni los de otro cliente del mismo partner.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.client_auth import ClientPrincipal, require_client_principal
from nexus_api.db.models import NotificationAudience

from ..notifications import (
    NotificationId,
    Viewer,
    list_for,
    mark_read_for,
    read_all_for,
    unread_count_for,
)
from ..schemas_onboarding import NotificationOut, NotificationPageOut, ReadAllOut, UnreadCountOut

router = APIRouter(prefix="/notifications")


def client_viewer(principal: ClientPrincipal) -> Viewer:
    return Viewer(
        partner_id=principal.partner.id,
        user_id=principal.user_id,
        audience=NotificationAudience.CLIENT.value,
        client_ref=principal.client_ref,
    )


@router.get("", response_model=NotificationPageOut)
async def list_notifications(
    principal: ClientPrincipal = Depends(require_client_principal()),
    session: AsyncSession = Depends(get_db_session),
    unread: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
) -> NotificationPageOut:
    return await list_for(
        session, client_viewer(principal), unread=unread, limit=limit, cursor=cursor
    )


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    principal: ClientPrincipal = Depends(require_client_principal()),
    session: AsyncSession = Depends(get_db_session),
) -> UnreadCountOut:
    return await unread_count_for(session, client_viewer(principal))


@router.post("/read-all", response_model=ReadAllOut)
async def read_all(
    principal: ClientPrincipal = Depends(require_client_principal()),
    session: AsyncSession = Depends(get_db_session),
) -> ReadAllOut:
    return await read_all_for(session, client_viewer(principal))


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: uuid.UUID = NotificationId,
    principal: ClientPrincipal = Depends(require_client_principal()),
    session: AsyncSession = Depends(get_db_session),
) -> NotificationOut:
    return await mark_read_for(session, client_viewer(principal), notification_id)
