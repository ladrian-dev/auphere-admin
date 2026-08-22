"""``/admin/auth/*`` — identidad del panel de operador, en la API (ADR-034).

Antes esto vivía en el BFF: Better Auth + Drizzle contra el esquema
``auth``, y ``lib/session.ts`` resolvía la sesión por SQL. Eso obliga a que
Vercel alcance la Postgres, y la Aurora de producción es privada — el 500
de ``admin.auphere.com`` del 2026-08-19 fue exactamente eso. **El panel
deja de tener base de datos**: guarda una cookie con un token opaco y
pregunta aquí.

Los tres endpoints son PRE-SESIÓN (todavía no hay principal) y se
autentican con el **token de servicio del panel**, el mismo
``NEXUS_ADMIN_TOKEN`` que ya lleva cada llamada de datos.

**Por qué el token estático y no EdDSA como la consola.** La consola no
puede tener una credencial de backend —es de terceros, y el CI hace grep
para impedirlo—, así que firma un JWT de 60 s por llamada. El panel es
ops-only por ADR-009 y **ya** custodia el token estático para todo su
tráfico: añadirle un segundo mecanismo no le quita ninguna capacidad a
nadie, sólo añade una clave más que distribuir. Cambiar el token estático
por un JWT por sesión es la Fase 2 de ADR-009, un trabajo aparte que
ADR-034 declara fuera de alcance a propósito. El navegador nunca llama
aquí: los llama el servidor de Next.

Lo que NO cambia, y por eso esto no debilita nada:

- quien tiene el token de servicio ya podía leer y escribir todo
  ``/admin/*``; el login no le abre ninguna puerta nueva;
- la contraseña sigue siendo la única prueba de quién eres, y el bloqueo
  por intentos es el mismo de la consola.

Respuestas de error, a propósito indistinguibles:

- **401 ``Invalid e-mail or password``** para cuenta inexistente,
  contraseña incorrecta y cuenta bloqueada por intentos. Nada de lo que se
  devuelve permite enumerar correos. Una cuenta **deshabilitada** entra
  igual y recibe ``access="disabled"``: distinguirla en el login sería otra
  forma de enumerar.
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
from nexus_api.core.rate_limit import allow
from nexus_api.core.security import require_admin_token
from nexus_api.schemas.admin_auth import (
    OperatorLoginIn,
    OperatorLoginOut,
    OperatorOut,
    OperatorSessionIn,
    OperatorSessionOut,
)
from nexus_api.services import operator_identity
from nexus_api.services.operator_identity import OperatorRole

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth")

#: Intentos por minuto, por correo y por IP de forma independiente.
LOGIN_ATTEMPTS_PER_MINUTE = 10
_RETRY_AFTER_SECONDS = 60

_INVALID_CREDENTIALS = "Invalid e-mail or password"


def operator_out(view: operator_identity.OperatorView) -> OperatorOut:
    account = view.account
    return OperatorOut(
        id=str(account.id),
        email=account.email,
        display_name=account.display_name,
        locale=account.locale,
        access=view.access,
        role=cast(OperatorRole, account.role),
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _guard_rate_limit(redis: Redis, *, email: str, ip: str | None) -> None:
    """Dos cubos independientes: por correo y por IP.

    El del correo protege una cuenta concreta de un ataque distribuido; el
    de la IP protege al resto de cuentas de un atacante único. Se mira el
    hash del correo y no el correo: las claves de Redis acaban en volcados
    y en trazas, y una lista de correos de operadores de Auphere es
    exactamente lo que no queremos regalar.
    """
    email_key = hashlib.sha256(
        operator_identity.normalize_email(email).encode("utf-8")
    ).hexdigest()[:32]
    buckets = [f"rl:admin:login:email:{email_key}"]
    if ip:
        buckets.append(f"rl:admin:login:ip:{ip}")
    for key in buckets:
        if not await allow(
            redis,
            key=key,
            per_minute=LOGIN_ATTEMPTS_PER_MINUTE,
            surface="admin_login",
        ):
            log.warning("admin_auth.login_rate_limited", bucket=key.rsplit(":", 2)[1])
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts",
                headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
            )


@router.post("/login", response_model=OperatorLoginOut)
async def login(
    body: OperatorLoginIn,
    request: Request,
    response: Response,
    _token: str = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> OperatorLoginOut:
    """Correo + contraseña → token de sesión opaco.

    El BFF lo guarda en una cookie ``HttpOnly``. Aquí no se emite ninguna
    cookie: quien habla con este endpoint es el servidor de Next, no el
    navegador.
    """
    ip = _client_ip(request)
    await _guard_rate_limit(redis, email=body.email, ip=ip)

    async with session.begin():
        account = await operator_identity.authenticate(
            session, email=body.email, password=body.password
        )
        if account is None:
            log.info("admin_auth.login_failed", ip=ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
            )
        token, expires_at = await operator_identity.start_session(
            session,
            account,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
        view = operator_identity.load_operator_view(account)

    log.info("admin_auth.login_ok", account_id=str(account.id), access=view.access)
    response.status_code = status.HTTP_200_OK
    return OperatorLoginOut(token=token, expires_at=expires_at, operator=operator_out(view))


@router.post("/session", response_model=OperatorSessionOut)
async def read_session(
    body: OperatorSessionIn,
    _token: str = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> OperatorSessionOut:
    """Token de sesión → quién es y si puede entrar.

    Es un POST y no un GET a propósito: el token viaja en el cuerpo, no en
    la URL, que es donde acaban los logs de acceso y el ``Referer``.

    Devuelve 200 con ``operator=null`` cuando el token no vale, en vez de
    401: para el BFF "no hay sesión" es una respuesta normal —enseña el
    login—, no un fallo de credencial suya.
    """
    async with session.begin():
        account = await operator_identity.resolve_session(session, body.token)
        view = operator_identity.load_operator_view(account) if account else None
    return OperatorSessionOut(operator=operator_out(view) if view else None)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: OperatorSessionIn,
    _token: str = Depends(require_admin_token),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Idempotente: cerrar una sesión que no existe no es un error."""
    async with session.begin():
        await operator_identity.end_session(session, body.token)


__all__ = ["router"]
