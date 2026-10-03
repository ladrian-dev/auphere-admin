"""``/console/password-reset`` — recuperar la contraseña (spec 011).

**Estas rutas NO son anónimas en la API, y no es un descuido.** Van detrás del
token de servicio del BFF (``svc: "console"``), igual que ``/console/auth/*`` y
``/console/signup/*``: el navegador nunca habla con esta API, habla con el BFF,
que acuña un token de 60 s por llamada. Y ``tests/isolation/test_console_scope``
exige 401 sin token en **todas** las rutas registradas. La anonimidad vive en el
borde navegador ↔ BFF; el borde BFF ↔ API nunca es anónimo.

Lo que gobierna este fichero entero
-----------------------------------
**Pedir un enlace responde siempre lo mismo.** Cuatro caminos, una respuesta:

1. la dirección **no tiene cuenta**;
2. el **envío falló** — ``send_email`` no lanza, devuelve ``False``;
3. se pasó el **tope** de peticiones;
4. tiene cuenta y todo fue bien.

Decir «no pudimos enviarlo» o contestar 429 revelaría que la cuenta existe, y
eso es exactamente lo que una pantalla de «he olvidado mi contraseña» no puede
regalar: es la única ruta del producto que acepta una dirección de cualquiera.
Que el fallo de envío sea invisible **para quien pregunta** es deliberado; para
Auphere no lo es, y por eso queda en los registros.

**El orden tiene una razón y no es de estilo** (D-2): el tope se comprueba
**antes** de mirar si la cuenta existe. Al revés, una dirección registrada
gastaría una consulta y un envío antes de toparse, y una sin registrar no: el
reloj diría lo que el cuerpo calla.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsoleService, require_console_service
from nexus_api.services import console_identity, password_reset
from nexus_api.services.console_identity import PasswordPolicyError
from nexus_api.services.one_time_code_limits import CodeRateLimited, CodeRateLimiter

from .schemas_password_reset import (
    PasswordResetFinishIn,
    PasswordResetFinishOut,
    PasswordResetStartIn,
    PasswordResetStartOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/password-reset")

Token = Path(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")

#: Cuerpo único para los tres casos de enlace muerto —inexistente, caducado y
#: ya usado—. Es una constante y no un literal repetido para que nadie los haga
#: divergir sin darse cuenta, y no nombra a nadie: quien abre un enlace muerto
#: no puede averiguar de quién era (R2.3).
_DEAD_LINK = "password reset link not found or expired"


def _dead_link() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_DEAD_LINK)


def _limiter(redis: Redis) -> CodeRateLimiter:
    """El limitador **que ya existe** (R5.5), con los números de D-6.

    No se escribe uno nuevo: su forma —dos claves, cuenta dentro de una ventana
    y espera creciente, y las dos borradas al acertar— es la correcta, y un
    segundo limitador con la misma forma y distintos números es cómo dos
    implementaciones acaban divergiendo.

    **Qué hace exactamente, que no es «cinco por hora» a secas.** Cinco
    peticiones dentro de la ventana abren una espera de 60 s que se **dobla**
    con cada tanda hasta un tope de 15 minutos. O sea: cinco seguidas, luego
    cinco más al minuto, luego a los dos… y en régimen, cinco cada cuarto de
    hora. Queda escrito aquí y no redondeado a la cifra de D-6 porque un
    comentario que dice un número y un código que hace otro es peor que no
    tener comentario.

    Sirve para lo que tiene que servir: quien no encuentra el correo pide otro
    sin toparse, y quien quiere barrer direcciones no puede hacerlo rápido ni
    barato.
    """
    return CodeRateLimiter(
        redis=redis,
        limit=password_reset.REQUESTS_PER_WINDOW,
        window=password_reset.REQUEST_WINDOW,
    )


def _attempt_key(email: str) -> str:
    """La dirección es la clave (R5.4), con su prefijo.

    El prefijo separa este cubo del de los códigos de sesión, que comparten
    limitador y llevan una IP. Sin él, dos cosas distintas se castigarían
    entre sí el día que alguien usara la misma cadena para las dos.
    """
    return f"pwreset:{email}"


@router.post("", response_model=PasswordResetStartOut, status_code=status.HTTP_202_ACCEPTED)
async def start_password_reset(
    body: PasswordResetStartIn,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> PasswordResetStartOut:
    """Pide un enlace. **Siempre 202 y siempre el mismo cuerpo.**"""
    email = console_identity.normalize_email(str(body.email))
    limiter = _limiter(redis)
    key = _attempt_key(email)

    try:
        # ANTES de mirar si la cuenta existe (D-2). Y el tope se contesta
        # tragándose la excepción, no traduciéndola a 429: un 429 aquí sería
        # el mismo oráculo por otra puerta.
        await limiter.check(key)
    except CodeRateLimited as exc:
        log.warning("password_reset.rate_limited", retry_after=exc.retry_after_seconds)
        return PasswordResetStartOut()

    # Esta petición cuenta, exista o no la cuenta: si sólo contaran las que
    # aciertan, barrer direcciones saldría gratis.
    await limiter.record_failure(key)

    async with session.begin():
        account = await console_identity.get_by_email(session, email)
        plaintext = (
            await password_reset.create_request(session, account=account) if account else None
        )
        # El idioma del correo es el de la CUENTA, no el del navegador que
        # rellenó el formulario: quien lo va a leer es la persona dueña de la
        # dirección, y puede no ser quien pulsó.
        locale = account.locale if account else "es"

    if plaintext is None:
        # Sin cuenta no sale ningún correo: mandar uno a una dirección que no
        # pidió nada convierte esta ruta en un remitente de correo ajeno.
        return PasswordResetStartOut()

    # Fuera de la transacción: mandar correo no debe mantener abierta una
    # transacción, y que el envío falle no debe deshacer la petición — el
    # enlace ya existe y pedir otro es un gesto de una línea.
    sent = await password_reset.send_reset_mail(email=email, token=plaintext, locale=locale)
    if not sent:
        # **Y aquí se acaba.** El fallo es de Auphere y vive en sus registros;
        # la respuesta no se entera. Sin la dirección: ``services/email`` ya la
        # lleva, y repetirla aquí la duplica en un sitio más.
        log.error("password_reset.mail_not_sent")
    return PasswordResetStartOut()


@router.post("/{token}", response_model=PasswordResetFinishOut)
async def finish_password_reset(
    body: PasswordResetFinishIn,
    token: str = Token,
    _svc: ConsoleService = Depends(require_console_service()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> PasswordResetFinishOut:
    """Fija la contraseña nueva y deja fuera a quien estuviera dentro.

    **Una transacción con las tres cosas** (R3.3): contraseña, sesiones y
    máquinas. Si algo revienta a mitad no queda una contraseña cambiada con las
    sesiones vivas, que es el estado que no puede existir.

    **No devuelve sesión** (D-5): lleva a la entrada. Acabamos de cerrar todas
    las de esta persona; abrir una nueva aquí contradiría lo que se acaba de
    hacer.
    """
    try:
        async with session.begin():
            account = await password_reset.redeem(session, token=token, password=body.password)
    except password_reset.ResetTokenRejected as exc:
        raise _dead_link() from exc
    except PasswordPolicyError as exc:
        # El enlace NO se ha gastado: ``redeem`` valida antes de sellar nada, y
        # la transacción se deshace entera. Equivocarse escribiendo la
        # contraseña nueva no puede obligar a pedir otro correo.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # Quien acaba de restablecer deja de ser sospechoso: se le borran las dos
    # claves del limitador, que es la forma que este módulo ya tenía.
    await _limiter(redis).clear(_attempt_key(account.email))
    log.info("password_reset.completed", account_id=str(account.id))

    # **Fuera de la transacción, y después de todo** (R4.4). El aviso no puede
    # deshacer un restablecimiento que ya ocurrió: si pudiera, un proveedor de
    # correo con un mal día dejaría a la persona sin entrar y sin enterarse.
    # El idioma sale de la cuenta y no del cuerpo de la petición: es el de
    # quien lo va a leer, y aquí quien lee puede no ser quien pulsó.
    if not await password_reset.send_changed_notice(email=account.email, locale=account.locale):
        log.error("password_reset.notice_not_sent", account_id=str(account.id))
    return PasswordResetFinishOut()
