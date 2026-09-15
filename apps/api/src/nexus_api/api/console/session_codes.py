"""Las dos rutas del código de sesión — spec 009, Requisitos 3 y 4.

**Canjear no puede exigir sesión de persona**: el código *es* la credencial, y
pedirle sesión a quien viene a conseguir una sería pedirle la llave para darle
la llave. Lo que sustituye a esa autenticación son tres cosas, todas en
``services/session_codes.py``: el código vive diez minutos y sirve una vez.
**No se ata a la máquina** — se intentó y no hay a qué atarlo: quien lo pide es
el navegador del sistema (spec 009, «Enmienda del 2026-09-15»).

**Pero no autenticar a la persona no es no autenticar.** El canje exige la
credencial de servicio del BFF (``require_console_service``), como los otros dos
flujos previos a la pertenencia — el login y el callback de Google. La ruta que
es pública para la cáscara es **la de la consola**, nunca ésta: en esta API no
hay ni una ruta ``/console/*`` sin credencial, y
``tests/isolation/test_console_scope.py`` lo comprueba una por una. Esa suite
cazó este fallo exacto cuando aquí no había dependencia.

**Emitir no pide ningún permiso** —``require_console_principal()`` sin
argumentos— porque llevarse la propia sesión a la propia aplicación no es una
capacidad que un rol conceda o niegue: es de la persona.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexus_api.core.client_ip import client_ip_for_storage
from nexus_api.core.console_auth import (
    ConsolePrincipal,
    ConsoleService,
    require_console_principal,
    require_console_service,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.services.session_codes import (
    SessionCodeRejected,
    issue_session_code,
    redeem_session_code,
)

router = APIRouter(prefix="/auth/session-code")


class IssueOut(BaseModel):
    #: En claro y una sola vez: la pantalla lo enseña y la base guarda su hash.
    code: str


class RedeemIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class RedeemOut(BaseModel):
    session_token: str
    expires_at: str


@router.post("", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
async def issue(
    principal: ConsolePrincipal = Depends(require_console_principal()),
) -> IssueOut:
    """Emite el código para **quien lo pide**, nunca para otro (R3.1, R5.1)."""
    async with get_sessionmaker()() as session, session.begin():
        code = await issue_session_code(session, principal_id=uuid.UUID(principal.user_id))
    return IssueOut(code=code)


@router.post("/redeem", response_model=RedeemOut)
async def redeem(
    body: RedeemIn,
    request: Request,
    _svc: ConsoleService = Depends(require_console_service()),
) -> RedeemOut | JSONResponse:
    """Canjea el código por una sesión nueva.

    **Sin sesión de persona a propósito, pero con la credencial de servicio del
    BFF**: quien llega aquí es la consola, no la cáscara.

    El rechazo es **uno solo y siempre el mismo** (R4.5): caducado, usado,
    inexistente o mal escrito se contestan igual. Por eso no
    se traduce la excepción a varios códigos de error — hacerlo devolvería
    exactamente la información que el diseño esconde.
    """
    async with get_sessionmaker()() as session, session.begin():
        try:
            token, expires_at = await redeem_session_code(
                session,
                code=body.code,
                ip=client_ip_for_storage(request),
                user_agent=request.headers.get("user-agent"),
            )
        except SessionCodeRejected:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"code": "session_code_invalid"},
            )
    return RedeemOut(session_token=token, expires_at=expires_at.isoformat())
