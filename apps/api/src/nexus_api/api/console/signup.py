"""``/console/signup/*`` — el alta autónoma de un partner (spec 006).

**Estos endpoints NO son anónimos en la API, y no es un descuido.** Van detrás
del token de servicio del BFF (``svc: "console"``), igual que ``/console/auth/*``
y ``/console/invitations/*``. Dos razones, y la segunda es la que manda:

1. Es la forma del sistema desde ADR-032: el navegador nunca habla con esta
   API, habla con el BFF, que acuña un token de 60 s por llamada.
2. ``tests/isolation/test_console_scope.py`` exige **401 sin token en todas**
   las rutas registradas, y esa suite bloquea el merge. Un endpoint abierto la
   pondría en rojo el día que se monta.

La anonimidad del registro vive en el borde **navegador ↔ BFF**. El borde
**BFF ↔ API** nunca es anónimo.

**Nada de lo que sale de aquí permite enumerar correos.** La respuesta del alta
es idéntica exista o no la dirección; lo que cambia es el correo que llega. Y
los cuatro casos de token muerto —inexistente, caducado, usado, revocado— dan
el mismo 404 con el mismo cuerpo.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.client_ip import client_ip, client_ip_for_storage
from nexus_api.core.console_auth import ConsoleService, require_console_service
from nexus_api.core.rate_limit import allow
from nexus_api.db.models import AuditLog
from nexus_api.repositories.signup import SignupRequestRepository
from nexus_api.services import console_identity
from nexus_api.services.signup import SignupBirthError, complete_signup

from .schemas_signup import (
    SignupCompleteIn,
    SignupCompleteOut,
    SignupLookupOut,
    SignupStartIn,
    SignupStartOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/signup")

Token = Path(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")

#: Más estricto que el login (10): pedir el alta manda un correo, y un correo
#: cuesta dinero y reputación de dominio. El login sólo cuesta un hash.
SIGNUP_ATTEMPTS_PER_MINUTE = 3
_RETRY_AFTER_SECONDS = 60

#: Cuerpo único para los cuatro casos de token muerto. Es una constante y no un
#: literal repetido para que nadie los haga divergir sin darse cuenta.
_DEAD_TOKEN = "signup request not found or expired"


def _dead_token() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_DEAD_TOKEN)


def _disabled() -> HTTPException:
    """Con la bandera apagada la consola no pinta el formulario. No hay botón
    gris ni pantalla que explique lo que no hay (constitución §V)."""
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="signup_disabled")


async def check_signup_rate_limit(redis: Redis, *, email: str, ip: str) -> None:
    """Dos cubos independientes, igual que el login: uno por correo y otro por
    IP. El correo va hasheado — una clave de Redis no es sitio para un dato
    personal — y la IP sale de ``core/client_ip``, no del socket."""
    import hashlib

    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]
    ip_key = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]
    for key in (f"rl:signup:email:{email_key}", f"rl:signup:ip:{ip_key}"):
        if not await allow(
            redis, key=key, per_minute=SIGNUP_ATTEMPTS_PER_MINUTE, surface="console_signup"
        ):
            log.warning("console_signup.rate_limited", bucket=key.rsplit(":", 2)[1])
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts",
                headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
            )


@router.post("", response_model=SignupStartOut, status_code=status.HTTP_202_ACCEPTED)
async def start_signup(
    body: SignupStartIn,
    request: Request,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> SignupStartOut:
    """Pide el alta. **No crea ni partner, ni cuenta, ni membresía.**"""
    settings = get_settings()
    if not settings.signup_enabled:
        raise _disabled()

    email = console_identity.normalize_email(str(body.email))
    # El límite se comprueba ANTES de mirar si el correo existe y, sobre todo,
    # antes de mandar nada: un limitador que responde 429 después de haber
    # mandado el correo no contiene el abuso, sólo lo documenta.
    await check_signup_rate_limit(redis, email=email, ip=client_ip(request))

    async with session.begin():
        existing = await console_identity.get_by_email(session, email)
        if existing is None:
            _row, plaintext = await SignupRequestRepository(session).create(
                email=email,
                ttl_hours=settings.signup_token_ttl_hours,
                ip=client_ip_for_storage(request),
            )
        else:
            plaintext = None

    # Fuera de la transacción: mandar correo no debe mantener abierta una
    # transacción, y que falle el envío no debe deshacer la solicitud.
    await _send_signup_mail(email=email, token=plaintext, locale=body.locale)
    return SignupStartOut()


async def _send_signup_mail(*, email: str, token: str | None, locale: str) -> None:
    """Dos correos distintos, una sola respuesta HTTP.

    Con ``token`` es el enlace del alta; sin él, la dirección ya tiene cuenta y
    lo que llega es «ya tienes cuenta, entra por aquí». Quien llamó no puede
    distinguir los dos casos: la diferencia sólo la ve quien abre el buzón, que
    es precisamente el dueño de la dirección.
    """
    from nexus_api.services.email import send_email

    settings = get_settings()
    base = settings.console_base_url.rstrip("/")
    if token is not None:
        subject = "Crea tu cuenta de Auphere" if locale == "es" else "Create your Auphere account"
        link = f"{base}/signup/{token}"
        body = f'<p><a href="{link}">{link}</a></p>'
    else:
        subject = "Ya tienes cuenta en Auphere" if locale == "es" else "You already have an account"
        body = f'<p><a href="{base}/login">{base}/login</a></p>'
    # ``send_email`` nunca lanza: devuelve False si no está configurado.
    await send_email(to=email, subject=subject, html=body)


@router.get("/{token}", response_model=SignupLookupOut)
async def lookup_signup(
    token: str = Token,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
) -> SignupLookupOut:
    if not get_settings().signup_enabled:
        raise _disabled()
    async with session.begin():
        row = await SignupRequestRepository(session).get_pending_by_token(token)
        if row is None:
            raise _dead_token()
        return SignupLookupOut(
            email=row.email,
            provider=row.provider,  # type: ignore[arg-type]
            expires_at=row.expires_at.isoformat(),
        )


@router.post(
    "/{token}/complete",
    response_model=SignupCompleteOut,
    status_code=status.HTTP_201_CREATED,
)
async def complete(
    body: SignupCompleteIn,
    request: Request,
    token: str = Token,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
) -> SignupCompleteOut:
    """Nace el partner. **Una transacción o ninguna.**"""
    if not get_settings().signup_enabled:
        raise _disabled()

    async with session.begin():
        repo = SignupRequestRepository(session)
        row = await repo.get_pending_by_token(token)
        if row is None:
            raise _dead_token()

        if body.password is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="password is required for this signup",
            )
        account = await console_identity.create_account(
            session,
            email=row.email,
            password=body.password,
            display_name=body.display_name,
        )
        try:
            outcome = await complete_signup(
                session,
                signup=row,
                company_name=body.company_name,
                user_id=str(account.id),
                display_name=body.display_name,
            )
        except SignupBirthError as exc:
            if exc.reason == "already_member":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="already_member"
                ) from exc
            if exc.reason in {"not_pending", "expired"}:
                raise _dead_token() from exc
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.reason
            ) from exc

        session_token, expires_at = await console_identity.start_session(
            session,
            account,
            ip=client_ip_for_storage(request),
            user_agent=request.headers.get("user-agent"),
        )
        # La auditoría nombra a la PERSONA, también aquí, donde esa persona
        # todavía no era principal cuando empezó el recorrido. Y no lleva
        # contraseña, ni token en claro, ni IP en claro.
        session.add(
            AuditLog(
                tenant_id=None,
                actor=f"console:{account.email}",
                action="partner.signup.completed",
                target=str(outcome.partner.id),
                after_json={
                    "partner_slug": outcome.partner.slug,
                    "via": row.provider or "password",
                },
            )
        )

    return SignupCompleteOut(
        session_token=session_token,
        expires_at=expires_at.isoformat(),
        partner_slug=outcome.partner.slug,
    )
