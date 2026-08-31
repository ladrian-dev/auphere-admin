"""``/console/auth/*`` — identidad de la consola, en la API.

Antes esto vivía en el BFF: better-auth + Drizzle contra el esquema
``console_auth``, y ``lib/principal.ts`` consultaba
``public.partner_memberships`` por SQL. Eso obliga a que Vercel alcance la
Postgres, y la Aurora de producción es privada. **La consola deja de tener
base de datos**: guarda una cookie con un token opaco y pregunta aquí.

Los tres endpoints son PRE-SESIÓN (todavía no hay principal), así que se
autentican con el **token de servicio** del BFF (``svc: "console"``,
firma EdDSA, 60 s, anti-replay por ``jti``), exactamente igual que
``/console/invitations/*``. El navegador nunca los llama: los llama el
servidor de Next.

Lo que NO cambia (y por eso esto no debilita nada):

- la pertenencia sigue siendo ``public.partner_memberships``, y el
  verificador de cada llamada real (``require_console_principal``) la
  vuelve a comprobar contra la base sin fiarse del BFF;
- un login correcto NO implica acceso: si no hay membresía activa, o el
  partner está suspendido o sin ``console_enabled``, el principal sale con
  ``access != "ok"`` y la consola enseña su página "sin acceso".

Respuestas de error, a propósito indistinguibles:

- **401 ``Invalid e-mail or password``** para cuenta inexistente,
  contraseña incorrecta y cuenta bloqueada por intentos. Nada de lo que se
  devuelve permite enumerar correos.
- **429 con ``Retry-After``** al pasar el límite (por correo y por IP).
"""

from __future__ import annotations

import hashlib
from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsoleService, permissions_for, require_console_service
from nexus_api.core.rate_limit import allow
from nexus_api.db.models import AuditLog
from nexus_api.services import console_identity
from nexus_api.services.console_identity import PrincipalView

from .schemas_auth import (
    AccessLiteral,
    LoginIn,
    LoginOut,
    PrincipalOut,
    SessionIn,
    SessionOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth")

#: Intentos por minuto, por correo y por IP de forma independiente.
LOGIN_ATTEMPTS_PER_MINUTE = 10
_RETRY_AFTER_SECONDS = 60

_INVALID_CREDENTIALS = "Invalid e-mail or password"


def principal_out(view: PrincipalView) -> PrincipalOut:
    """Traduce la vista del servicio al modelo que consume la consola.

    Los permisos salen del MISMO mapa que usa el verificador de cada
    llamada (``core/console_auth.PERMISSIONS``), así que la consola nunca
    guarda su propia copia y no puede quedarse desincronizada.
    """
    account = view.account
    if not view.ok or view.membership is None or view.partner is None:
        return PrincipalOut(
            user_id=account.id,
            email=account.email,
            display_name=account.display_name,
            locale=account.locale,
            access=cast(AccessLiteral, view.access),
            partner_name=view.partner.name if view.partner else None,
            partner_status=view.partner.status if view.partner else None,
        )
    return PrincipalOut(
        user_id=account.id,
        email=account.email,
        display_name=account.display_name or view.membership.display_name,
        locale=account.locale,
        access="ok",
        membership_id=view.membership.id,
        partner_id=view.partner.id,
        partner_slug=view.partner.slug,
        partner_name=view.partner.name,
        partner_status=view.partner.status,
        role=view.membership.role,
        permissions=sorted(permissions_for(view.membership.role)),
        console_enabled=view.partner.console_enabled,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_INVALID_CREDENTIALS,
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def check_login_rate_limit(redis: Redis, *, email: str, ip: str | None) -> None:
    """Dos cubos independientes: uno por correo (frena el ataque a UNA
    cuenta desde muchas IPs) y otro por IP (frena el barrido de muchas
    cuentas desde una). El correo se guarda hasheado — una clave de Redis
    no es sitio para un dato personal."""
    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]
    buckets = [f"rl:console:login:email:{email_key}"]
    if ip:
        buckets.append(f"rl:console:login:ip:{ip}")
    for key in buckets:
        if not await allow(
            redis,
            key=key,
            per_minute=LOGIN_ATTEMPTS_PER_MINUTE,
            surface="console_login",
        ):
            log.warning("console_auth.login_rate_limited", bucket=key.rsplit(":", 2)[1])
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts",
                headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
            )


@router.post(
    "/login",
    response_model=LoginOut,
    responses={
        401: {"description": "Invalid e-mail or password (also: locked account)."},
        429: {"description": "Too many attempts; see Retry-After."},
    },
)
async def login(
    body: LoginIn,
    request: Request,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> LoginOut:
    email = console_identity.normalize_email(str(body.email))
    ip = _client_ip(request)
    await check_login_rate_limit(redis, email=email, ip=ip)

    # DOS transacciones a propósito. El intento fallido incrementa el
    # contador de la cuenta, y ese contador es lo que hace que el bloqueo
    # exista: si el 401 se lanzara dentro de la misma transacción, el
    # ``rollback`` se llevaría el incremento por delante y la cuenta nunca
    # se bloquearía. La primera cierra el intento; la segunda abre sesión.
    async with session.begin():
        account = await console_identity.authenticate(session, email=email, password=body.password)
    if account is None:
        raise _unauthorized()

    async with session.begin():
        token, expires_at = await console_identity.start_session(
            session,
            account,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
        view = await console_identity.load_principal_view(session, account)
        if view.ok and view.partner is not None:
            session.add(
                AuditLog(
                    tenant_id=None,
                    actor=f"console:{account.email}",
                    action="console.auth.login",
                    target=f"partner:{view.partner.id}",
                    after_json={"email": account.email},
                )
            )
        out = LoginOut(token=token, expires_at=expires_at, principal=principal_out(view))
    log.info("console_auth.login", account_id=str(account.id), access=view.access)
    return out


@router.post(
    "/session",
    response_model=SessionOut,
    responses={401: {"description": "Unknown or expired session token."}},
)
async def read_session(
    body: SessionIn,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
) -> SessionOut:
    """Quién está detrás de una cookie. La consola la llama una vez por
    petición (memoizada con ``React.cache``)."""
    async with session.begin():
        account = await console_identity.resolve_session(session, body.token)
        if account is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        view = await console_identity.load_principal_view(session, account)
        out = SessionOut(principal=principal_out(view))
    return out


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: SessionIn,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Idempotente: cerrar una sesión que ya no existe devuelve 204."""
    async with session.begin():
        account = await console_identity.resolve_session(session, body.token)
        if account is not None:
            view = await console_identity.load_principal_view(session, account)
            if view.ok and view.partner is not None:
                session.add(
                    AuditLog(
                        tenant_id=None,
                        actor=f"console:{account.email}",
                        action="console.auth.logout",
                        target=f"partner:{view.partner.id}",
                        after_json={"email": account.email},
                    )
                )
        await console_identity.end_session(session, body.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
