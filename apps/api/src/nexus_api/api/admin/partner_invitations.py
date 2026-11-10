"""``/admin/partners/{partner_id}/invitations…`` — spec 052.

El operador invita al propietario de un partner que no lo tiene, reenvía un
enlace y revoca. Crear un partner, que también invita, vive en ``partners.py``.

Dos reglas de esta puerta, como en ``client_access.py``:

* **El partner es la ruta y la persona, ``X-Operator-Id``.** El token del panel
  es de servicio: sin un operador habilitado no hay cambio, y la auditoría nombra
  a esa persona (constitución §IV). Las reglas están en
  ``services/owner_invitation.py``.
* **El enlace sale una vez.** Va en el correo y en esta respuesta para que el
  operador pueda pasarlo a mano; en la base solo queda su hash.

``tests/isolation/test_owner_invitation_scope.py`` barre estas rutas al montarse.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_enabled_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.schemas.partner import (
    OwnerInvitationActionIn,
    OwnerInvitationResultOut,
    OwnerInvitationRevokedOut,
    OwnerInviteIn,
)
from nexus_api.services import owner_invitation
from nexus_api.services.owner_invitation import Delivered, OwnerInvitationError

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


def invitation_error(exc: OwnerInvitationError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


def result_out(delivered: Delivered) -> OwnerInvitationResultOut:
    return OwnerInvitationResultOut(
        id=delivered.id,
        email=delivered.email,
        role=delivered.role,
        status=delivered.status,
        expires_at=delivered.expires_at,
        created_at=delivered.created_at,
        last_sent_at=delivered.last_sent_at,
        email_sent=delivered.email_sent,
        accept_url=delivered.accept_url,
    )


@router.post(
    "/{partner_id}/invitations",
    response_model=OwnerInvitationResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_owner(
    partner_id: uuid.UUID,
    body: OwnerInviteIn,
    operator: OperatorAccount = Depends(require_enabled_operator),
    session: AsyncSession = Depends(get_db_session),
) -> OwnerInvitationResultOut:
    try:
        async with session.begin():
            issued = await owner_invitation.invite(
                session, partner_id, email=body.email, actor=operator_actor(operator)
            )
    except OwnerInvitationError as exc:
        raise invitation_error(exc) from None
    except IntegrityError:
        # El partner emitió una a esa dirección justo ahora, desde su consola:
        # esa ruta no toma el bloqueo del partner.
        raise invitation_error(OwnerInvitationError("address_already_invited")) from None
    return result_out(await owner_invitation.deliver(issued))


@router.post(
    "/{partner_id}/invitations/{invitation_id}/resend",
    response_model=OwnerInvitationResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def resend_owner_invitation(
    partner_id: uuid.UUID,
    invitation_id: uuid.UUID,
    _body: OwnerInvitationActionIn,
    operator: OperatorAccount = Depends(require_enabled_operator),
    session: AsyncSession = Depends(get_db_session),
) -> OwnerInvitationResultOut:
    try:
        async with session.begin():
            issued = await owner_invitation.resend(
                session, partner_id, invitation_id, actor=operator_actor(operator)
            )
    except OwnerInvitationError as exc:
        raise invitation_error(exc) from None
    return result_out(await owner_invitation.deliver(issued))


@router.post(
    "/{partner_id}/invitations/{invitation_id}/revoke",
    response_model=OwnerInvitationRevokedOut,
)
async def revoke_owner_invitation(
    partner_id: uuid.UUID,
    invitation_id: uuid.UUID,
    _body: OwnerInvitationActionIn,
    operator: OperatorAccount = Depends(require_enabled_operator),
    session: AsyncSession = Depends(get_db_session),
) -> OwnerInvitationRevokedOut:
    try:
        async with session.begin():
            revoked = await owner_invitation.revoke(
                session, partner_id, invitation_id, actor=operator_actor(operator)
            )
    except OwnerInvitationError as exc:
        raise invitation_error(exc) from None
    return OwnerInvitationRevokedOut(
        id=revoked.id, email=revoked.email, status=revoked.status, changed=revoked.changed
    )
