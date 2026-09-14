"""Lo que ve y puede hacer el operador con el alta autónoma — spec 006, R8.

**Existe para no perder el gobierno al abrir la puerta.** Cuando cualquiera
puede crear un partner sin que nadie ejecute nada, el panel deja de ser un sitio
donde se crean cosas y pasa a ser el sitio donde uno se entera de las que se
crearon solas.

Dos situaciones distintas, y el requisito insiste en que no se parezcan:

- una **solicitud a medias** — correo verificado, empresa sin nombrar — que
  todavía no es nadie y caduca;
- un **partner nacido solo**, que ya es una empresa con su fecha, su vía de
  entrada y su nivel.

La vía de entrada sale de ``signup_requests.provider`` y se **nombra**: `null`
en la base significa «con contraseña», pero obligar a quien lee el panel a saber
eso es trasladarle un detalle de almacenamiento.

Suspender no vive aquí: ya se podía con ``PATCH /admin/partners/{id}``. Lo que
faltaba de R8.2 era **reenviar el enlace**, que era lo único que obligaba a
abrir una consola dentro de la VPC.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.config import get_settings
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import Partner, PartnerSubscription, SignupRequest, SignupStatus
from nexus_api.repositories import AuditRepository
from nexus_api.repositories.signup import SignupRequestRepository
from nexus_api.services.signup import send_signup_mail

from .schemas_signups import SignupPartnerOut, SignupRowOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/signups", tags=["admin:signups"])

#: Sin fila en ``partner_subscriptions`` **es** Free: un estado válido y
#: diseñado, no la ausencia de uno (ADR-037).
FREE_TIER = "free"

#: ``provider`` nulo es «con contraseña». Se nombra en la respuesta para que el
#: panel no tenga que traducir un `null`.
PASSWORD = "password"


def _admin_actor(token: str) -> str:
    return f"admin:{token[:8]}"


@router.get("", response_model=list[SignupRowOut])
async def list_signups(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    _actor: str = Depends(require_admin_token),
) -> list[SignupRowOut]:
    """Las solicitudes, de la más reciente a la más vieja, con su desenlace.

    Una consulta y no una por fila: el nivel y el partner llegan en el mismo
    viaje. Con `LEFT JOIN` porque la mayoría de las filas **no** tienen partner
    —están a medias, caducadas o revocadas— y ésas son justo las que el
    operador necesita ver.
    """
    rows = (
        await session.execute(
            sa.select(SignupRequest, Partner, PartnerSubscription.tier_code)
            .outerjoin(Partner, Partner.id == SignupRequest.partner_id)
            .outerjoin(PartnerSubscription, PartnerSubscription.partner_id == Partner.id)
            .order_by(SignupRequest.created_at.desc())
            .limit(limit)
        )
    ).all()

    out: list[SignupRowOut] = []
    for signup, partner, tier_code in rows:
        out.append(
            SignupRowOut(
                id=signup.id,
                email=signup.email,
                status=signup.status,
                provider=signup.provider or PASSWORD,
                created_at=signup.created_at,
                expires_at=signup.expires_at,
                consumed_at=signup.consumed_at,
                partner=(
                    None
                    if partner is None
                    else SignupPartnerOut(
                        id=partner.id,
                        name=partner.name,
                        slug=partner.slug,
                        status=partner.status,
                        tier=tier_code or FREE_TIER,
                    )
                ),
            )
        )
    return out


@router.post("/{signup_id}/resend", response_model=SignupRowOut)
async def resend_signup(
    signup_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
) -> SignupRowOut:
    """Reemite el enlace del alta y lo manda. **Sin entrar en la VPC** (R8.2).

    Emitir uno nuevo **mata el anterior** — ``create`` revoca las pendientes de
    ese correo. Si convivieran dos vivos, reenviar duplicaría la superficie en
    vez de reemplazarla, y el enlace viejo seguiría abriendo una cuenta.

    Sólo sobre una solicitud **viva**. Una consumida ya tiene cuenta y reenviarle
    un alta la mandaría a rehacer lo hecho; una caducada caducó por algo, y
    resucitarla desde el panel convertiría el plazo en una sugerencia. En los
    dos casos el camino es que la persona vuelva a pedirlo.
    """
    # El ``get`` va **dentro** del bloque: fuera abriría una transacción
    # implícita y ``session.begin()`` fallaría con «a transaction is already
    # begun». Es el idiom de ``partners.py``, no una preferencia.
    async with session.begin():
        signup = await session.get(SignupRequest, signup_id)
        if signup is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signup_not_found")
        if signup.status != SignupStatus.PENDING.value or signup.expires_at <= datetime.now(UTC):
            # 409 y no 404: la solicitud existe, lo que no vale es el estado.
            # Aquí no hay nada que ocultar — quien pregunta es un operador
            # autenticado, no un desconocido sondeando correos.
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="signup_not_pending")

        original_id = signup.id
        repo = SignupRequestRepository(session)
        fresh, plaintext = await repo.create(
            email=signup.email,
            ttl_hours=get_settings().signup_token_ttl_hours,
            provider=signup.provider,
            ip=None,
        )
        await AuditRepository(session).record(
            actor=_admin_actor(actor),
            action="signup.resend",
            target=f"signup:{original_id}",
            after={"reissued_as": str(fresh.id), "email": fresh.email},
            platform=True,
        )
        # ``created_at`` es server_default: sin este refresh, leerlo tras el
        # commit expira la instancia y hace IO sin greenlet — un 500 en una
        # petición que ya había escrito.
        await session.refresh(fresh)
        respuesta = SignupRowOut(
            id=fresh.id,
            email=fresh.email,
            status=fresh.status,
            provider=fresh.provider or PASSWORD,
            created_at=fresh.created_at,
            expires_at=fresh.expires_at,
            consumed_at=None,
            partner=None,
        )

    # Fuera de la transacción: mandar el correo es IO de red y no debe alargar
    # una transacción ni deshacer la reemisión si el proveedor tarda.
    await send_signup_mail(email=respuesta.email, token=plaintext, locale="es")
    log.info("admin.signup_resent", signup_id=str(original_id), reissued_as=str(respuesta.id))
    return respuesta
