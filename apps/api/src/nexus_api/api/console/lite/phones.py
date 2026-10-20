"""Los teléfonos de una persona de cliente — spec 031, R7, R8.2, R11.

* ``GET /console/lite/phones`` y ``DELETE /console/lite/phones/{id}`` — la
  persona ve y cierra **sus** teléfonos, desde la web o desde la app (R7.3).
* ``…/phones/current`` — lo que solo tiene sentido desde la app: salir, el
  destino de avisos y qué tipos le avisan.
* ``POST /console/lite/account/deletion-request`` — pedir que se borre la
  cuenta (R11.4).

Ninguna ruta acepta ni devuelve el tenant. Un teléfono de otra persona —aunque
sea del mismo cliente— es un 404 opaco (R7.5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from nexus_api.db.models import NOTICE_KINDS, AuditLog, ClientPhone
from nexus_api.services import client_phones

from .deps import LiteScope, lite_scope

log = structlog.get_logger(__name__)
router = APIRouter()


def _refused(code: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def _from_phone(scope: LiteScope) -> uuid.UUID:
    if scope.principal.phone_id is None:
        raise _refused("phone_only", status.HTTP_403_FORBIDDEN)
    return scope.principal.phone_id


# ── la lista de teléfonos ─────────────────────────────────────────────


class PhoneOut(BaseModel):
    id: uuid.UUID
    display_name: str
    platform: Literal["ios", "android"]
    app_version: str
    last_seen_at: datetime
    enrolled_at: datetime
    current: bool


def _mine(scope: LiteScope) -> sa.Select[tuple[ClientPhone]]:
    return sa.select(ClientPhone).where(
        ClientPhone.principal_id == scope.principal.user_id,
        ClientPhone.revoked_at.is_(None),
    )


@router.get("/phones", response_model=list[PhoneOut])
async def list_phones(scope: LiteScope = Depends(lite_scope())) -> list[PhoneOut]:
    rows = (
        await scope.session.scalars(_mine(scope).order_by(ClientPhone.last_seen_at.desc()))
    ).all()
    return [
        PhoneOut(
            id=p.id,
            display_name=p.display_name,
            platform=p.platform,  # type: ignore[arg-type]
            app_version=p.app_version,
            last_seen_at=p.last_seen_at,
            enrolled_at=p.enrolled_at,
            current=p.id == scope.principal.phone_id,
        )
        for p in rows
    ]


@router.delete("/phones/current", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(scope: LiteScope = Depends(lite_scope())) -> Response:
    """Salir en este teléfono (R7.1). Los otros teléfonos siguen dentro."""
    phone_id = _from_phone(scope)
    phone = await scope.session.get(ClientPhone, phone_id)
    if phone is not None:
        client_phones.revoke(scope.session, phone, reason="signed_out", by=scope.principal.actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/phones/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_phone(phone_id: uuid.UUID, scope: LiteScope = Depends(lite_scope())) -> Response:
    """Cerrar uno de **mis** teléfonos, por ejemplo uno perdido (R7.3, R7.5)."""
    phone = await scope.session.scalar(_mine(scope).where(ClientPhone.id == phone_id))
    if phone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    reason = "signed_out" if phone.id == scope.principal.phone_id else "closed_by_person"
    client_phones.revoke(scope.session, phone, reason=reason, by=scope.principal.actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── avisos de este teléfono ───────────────────────────────────────────


class PushIn(BaseModel):
    provider: Literal["apns", "fcm"]
    token: str = Field(min_length=8, max_length=512)
    apns_environment: Literal["sandbox", "production"] | None = None


@router.put("/phones/current/push", status_code=status.HTTP_204_NO_CONTENT)
async def register_push(body: PushIn, scope: LiteScope = Depends(lite_scope())) -> Response:
    """El destino de avisos de este teléfono (R8.2).

    Corre bajo la RLS del cliente para leer el teléfono, y suelta el mismo
    destino de cualquier otra fila con una sentencia propia: un destino, un
    dueño (data-model §0158). Esa sentencia no lee nada de otro cliente.
    """
    phone_id = _from_phone(scope)
    phone = await scope.session.get(ClientPhone, phone_id)
    if phone is None or phone.revoked_at is not None:  # pragma: no cover - la dependencia lo cubre
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await client_phones.register_push(
        scope.session,
        phone,
        provider=body.provider,
        token=body.token,
        apns_environment=body.apns_environment,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class NoticesIn(BaseModel):
    kinds: list[str] = Field(max_length=len(NOTICE_KINDS))


class NoticesOut(BaseModel):
    kinds: list[str]


@router.get("/phones/current/notices", response_model=NoticesOut)
async def read_notices(scope: LiteScope = Depends(lite_scope())) -> NoticesOut:
    phone = await scope.session.get(ClientPhone, _from_phone(scope))
    kinds = list(phone.notice_kinds) if phone is not None else []
    return NoticesOut(kinds=[k for k in NOTICE_KINDS if k in kinds])


@router.put("/phones/current/notices", response_model=NoticesOut)
async def set_notices(body: NoticesIn, scope: LiteScope = Depends(lite_scope())) -> NoticesOut:
    """Los interruptores de Ajustes (R11.2). Aplican a este teléfono."""
    unknown = set(body.kinds) - set(NOTICE_KINDS)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "unknown_kind", "kinds": sorted(unknown)},
        )
    phone = await scope.session.get(ClientPhone, _from_phone(scope))
    if phone is None:  # pragma: no cover - la dependencia lo cubre
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    ordered = [k for k in NOTICE_KINDS if k in set(body.kinds)]
    phone.notice_kinds = ordered
    return NoticesOut(kinds=ordered)


# ── pedir que se borre la cuenta ──────────────────────────────────────


#: Una petición por persona y día: repetirla no manda otro correo (R11.4).
_DELETION_THROTTLE = timedelta(hours=24)


@router.post("/account/deletion-request", status_code=status.HTTP_202_ACCEPTED)
async def request_deletion(scope: LiteScope = Depends(lite_scope())) -> Response:
    """Pedir a Auphere que borre la cuenta (R11.4).

    No borra nada: las cuentas las da Auphere y el borrado lo hace una persona
    (constitución §IV). Deja constancia y avisa por correo a la dirección de
    seguridad, la misma a la que se escribe por una cuenta comprometida.
    """
    principal = scope.principal
    since = datetime.now(UTC) - _DELETION_THROTTLE
    recent = await scope.session.scalar(
        sa.select(sa.func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.action == "client_account.deletion_requested",
            AuditLog.actor == principal.actor,
            AuditLog.created_at >= since,
        )
    )
    scope.session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor=principal.actor,
            action="client_account.deletion_requested",
            target=f"client_member:{principal.membership.id}",
            after_json={"email": principal.membership.email},
        )
    )
    if not recent:
        email = principal.membership.email
        client = principal.client_name

        async def _notify() -> None:
            from nexus_api.services.account_deletion import notify_deletion_request

            await notify_deletion_request(email=email, client_name=client)

        scope.after_commit(_notify)
    return Response(status_code=status.HTTP_202_ACCEPTED)
