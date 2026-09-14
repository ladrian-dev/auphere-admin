"""El nacimiento de un partner — spec 006, Requisito 3.

**Lo que este módulo NO hace, y es la mitad de su diseño: no escribe
``partner_memberships``.** Crea el partner, emite una invitación de ``owner``
para el correo ya verificado y llama a ``PartnerInvitationRepository.accept()``,
que es el mismo camino por el que entra cualquier invitado desde 0080.

Podría insertar la membresía directamente y serían diez líneas menos. No se
hace porque entonces habría **dos** caminos a esa tabla, y el que menos se usa
es el que se queda sin la regla nueva el día que se añada una — exactamente lo
que ya pasó con los dos contadores de gasto que ADR-037 tuvo que unificar.

**Todo o nada.** El peor estado posible de ``partner_memberships`` es un
partner sin owner: nadie puede entrar y nadie puede invitar. La operación vive
en la transacción del llamante y cualquier fallo la revienta entera.

**El partner nace en Free sin sembrar nada**: un partner sin fila en
``partner_subscriptions`` *es* Free, y la ausencia es un estado válido y
diseñado (``db/models/membership.py``).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Partner,
    PartnerMembership,
    PartnerRole,
    SignupRequest,
    SignupStatus,
)
from nexus_api.repositories.partner_membership import (
    InvitationError,
    PartnerInvitationRepository,
)

#: ``partners.slug`` es ``varchar(80)``. Se deja sitio para el sufijo que
#: desambigua dos empresas con el mismo nombre.
_SLUG_MAX = 72


class SignupBirthError(RuntimeError):
    """El alta no pudo completarse. Lleva el ``reason`` de la causa para que el
    endpoint elija su código sin inspeccionar el texto."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class SignupOutcome:
    partner: Partner
    membership: PartnerMembership


def slugify(name: str) -> str:
    """El nombre de empresa, convertido en referencia técnica.

    Sin acentos ni eñes: un ``slug`` viaja en URLs y en nombres de recurso, y
    ahí una ``ñ`` se convierte en ruido distinto según quién lo lea.
    """
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    return slug[:_SLUG_MAX] or "partner"


async def _free_slug(session: AsyncSession, base: str) -> str:
    """Un ``slug`` libre. Dos agencias pueden llamarse igual; lo que no puede
    repetirse es esto, y ``partners.slug`` es ``UNIQUE``."""
    taken = set(
        (await session.execute(sa.select(Partner.slug).where(Partner.slug.like(f"{base}%"))))
        .scalars()
        .all()
    )
    if base not in taken:
        return base
    # Sufijo aleatorio y no un contador: un contador dice cuántas empresas se
    # llaman igual, que no es asunto de nadie que lea la URL.
    for _ in range(10):
        candidate = f"{base}-{uuid.uuid4().hex[:6]}"
        if candidate not in taken:
            return candidate
    raise SignupBirthError("slug_exhausted", "no free slug for that company name")


async def complete_signup(
    session: AsyncSession,
    *,
    signup: SignupRequest,
    company_name: str,
    user_id: str,
    display_name: str | None,
) -> SignupOutcome:
    """Crea el partner y deja a esta persona dentro como ``owner``.

    El llamante ya ha verificado el correo (la ``signup`` está ``pending``) y ya
    ha resuelto la cuenta: aquí sólo nace la empresa.
    """
    if signup.status != SignupStatus.PENDING.value:
        raise SignupBirthError("not_pending", "signup request is no longer pending")
    now = datetime.now(UTC)
    if signup.expires_at <= now:
        raise SignupBirthError("expired", "signup request has expired")

    name = company_name.strip()
    if not name:
        raise SignupBirthError("empty_company_name", "company name is required")

    partner = Partner(
        id=uuid.uuid4(),
        name=name,
        slug=await _free_slug(session, slugify(name)),
        status="active",
        # La consola es lo único que esta persona puede usar el primer día.
        console_enabled=True,
    )
    session.add(partner)
    await session.flush()

    repo = PartnerInvitationRepository(session)
    # ``invited_by`` es None y es correcto: no la invitó nadie, se invitó sola.
    invitation, _plaintext = await repo.create(
        partner_id=partner.id,
        email=signup.email,
        role=PartnerRole.OWNER.value,
        invited_by=None,
    )
    try:
        membership = await repo.accept(
            invitation,
            user_id=user_id,
            email=signup.email,
            display_name=display_name,
        )
    except InvitationError as exc:
        # Se traduce en vez de propagarse: el endpoint del alta no tiene por
        # qué conocer el vocabulario de las invitaciones, y ``already_member``
        # aquí significa otra cosa para quien lo lee.
        raise SignupBirthError(exc.reason, str(exc)) from exc

    signup.status = SignupStatus.CONSUMED.value
    signup.consumed_at = now
    # El rastro que pide R8.1: de esta solicitud salió ESTE partner. Sin esto,
    # el panel enseña partners y no sabe cuáles llegaron sin que nadie mirara.
    signup.partner_id = partner.id
    await session.flush()

    # NO se inserta nada en ``partner_subscriptions``: sin fila es Free.
    return SignupOutcome(partner=partner, membership=membership)


async def send_signup_mail(*, email: str, token: str | None, locale: str = "es") -> None:
    """Dos correos distintos, una sola respuesta HTTP.

    Con ``token`` es el enlace del alta; sin él, la dirección ya tiene cuenta y
    lo que llega es «ya tienes cuenta, entra por aquí». Quien llamó no puede
    distinguir los dos casos: la diferencia sólo la ve quien abre el buzón, que
    es precisamente el dueño de la dirección.

    **Vive aquí y no en el router de la consola** desde que el panel de operador
    puede reenviar el enlace (R8.2). Dos sitios que mandan el mismo correo con
    dos plantillas distintas es cómo se empieza a tener dos productos.
    """
    from nexus_api.config import get_settings
    from nexus_api.services.email import send_email

    base = get_settings().console_base_url.rstrip("/")
    if token is not None:
        subject = "Crea tu cuenta de Auphere" if locale == "es" else "Create your Auphere account"
        link = f"{base}/signup/{token}"
        body = f'<p><a href="{link}">{link}</a></p>'
    else:
        subject = "Ya tienes cuenta en Auphere" if locale == "es" else "You already have an account"
        body = f'<p><a href="{base}/login">{base}/login</a></p>'
    # ``send_email`` nunca lanza: devuelve False si no está configurado.
    await send_email(to=email, subject=subject, html=body)
