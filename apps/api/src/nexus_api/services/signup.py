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
from nexus_api.services.console_v2 import born_on_new_console

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

    partner = born_on_new_console(
        Partner(
            id=uuid.uuid4(),
            name=name,
            slug=await _free_slug(session, slugify(name)),
            status="active",
            # La consola es lo único que esta persona puede usar el primer día.
            console_enabled=True,
        )
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


async def send_signup_mail(*, email: str, token: str | None, locale: str = "es") -> bool:
    """Dos correos distintos, una sola respuesta HTTP.

    Con ``token`` es el enlace del alta (``signup_link``); sin él, la dirección
    ya tiene cuenta y lo que llega es «ya tienes una cuenta, inicia sesión»
    (``signup_existing``). Quien llamó no puede distinguir los dos casos: la
    diferencia sólo la ve quien abre el buzón, que es precisamente el dueño de
    la dirección. Por eso los dos tipos comparten remitente en el catálogo
    (spec 051, R5.3): si vinieran de sitios distintos, el remitente delataría
    cuál tocó.

    **Vive aquí y no en el router de la consola** desde que el panel de operador
    puede reenviar el enlace (R8.2). Dos sitios que mandan el mismo correo con
    dos plantillas distintas es cómo se empieza a tener dos productos.

    El idioma es el del formulario, con la regla de la spec 051: inglés solo si
    se pide inglés. Antes era al revés —todo lo que no fuera ``es`` salía en
    inglés— y el alta era el único correo que lo hacía así.
    """
    from nexus_api.config import get_settings
    from nexus_api.services.email import send_template
    from nexus_api.services.email_catalog import EmailKind, console_link, email_locale

    lang = email_locale(locale)
    # ``send_template`` nunca lanza. Devuelve False tanto si este entorno no
    # envía como si el proveedor rechazó, y **quien llama tiene que
    # distinguirlo** con ``settings.email_delivers``: lo primero es una
    # decisión de despliegue, lo segundo una avería. El remitente no se pasa:
    # sale de la ficha del tipo, que no es la de los cobros.
    if token is not None:
        return await send_template(
            EmailKind.SIGNUP_LINK,
            to=email,
            subject=(
                "Confirm your email to create your Auphere account"
                if lang == "en"
                else "Confirma tu correo para crear tu cuenta en Auphere"
            ),
            variables={
                "EXPIRES_IN": _hours(get_settings().signup_token_ttl_hours, lang),
                "SIGNUP_URL": console_link(f"/signup/{token}"),
            },
            locale=lang,
        )
    return await send_template(
        EmailKind.SIGNUP_EXISTING,
        to=email,
        subject=(
            "You already have an Auphere account"
            if lang == "en"
            else "Ya tienes una cuenta en Auphere"
        ),
        variables={"LOGIN_URL": console_link("/login"), "FORGOT_URL": console_link("/forgot")},
        locale=lang,
    )


def _hours(n: int, lang: str) -> str:
    """«24 horas» / «24 hours», en singular para una."""
    if lang == "en":
        return f"{n} hour" if n == 1 else f"{n} hours"
    return f"{n} hora" if n == 1 else f"{n} horas"
