"""Vincular una cuenta de consola con un proveedor externo (spec 006, R5.2/5.3).

**El ancla es el ``subject`` del proveedor, no el correo.** Un correo cambia de
dueño: se libera y se reasigna, y en Google Workspace eso pasa cada vez que
alguien deja una empresa. Si la identidad fuera el correo, quien heredase una
dirección heredaría la cuenta. El ``sub`` de Google no se reasigna nunca.

Las tres respuestas posibles cuando alguien vuelve de Google, y por qué:

1. **Ya hay vínculo** → es esa cuenta. Ni se mira el correo: si la persona
   cambió de dirección en Google, sigue siendo la misma persona.
2. **No hay vínculo pero el correo verificado ya tiene cuenta** → se vincula a
   **esa** cuenta. Nunca se crea una segunda: el requisito dice que entrar por
   las dos puertas aterriza en la misma.
3. **Ni vínculo ni cuenta** → no se crea nada aquí. Se devuelve «desconocido» y
   quien llame decide, porque crear una cuenta es parte del alta y el alta
   tiene sus propias reglas (bandera, solicitud, nombre de empresa).

Quien llama **ya ha comprobado que el proveedor verifica el correo**. Este
módulo no repite esa comprobación porque no tiene el token: si la repitiera a
medias, sería peor que no hacerla.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.console_identity import ConsoleAccount, PrincipalIdentity
from nexus_api.services import console_identity


@dataclass(frozen=True)
class LinkOutcome:
    account: ConsoleAccount | None
    #: ``linked`` — ya existía el vínculo · ``attached`` — se acaba de colgar
    #: de una cuenta que ya existía · ``unknown`` — no hay cuenta todavía.
    kind: str


async def resolve_provider_identity(
    session: AsyncSession,
    *,
    provider: str,
    subject: str,
    email: str,
) -> LinkOutcome:
    """Quién es esta persona, según el proveedor."""
    normalised = console_identity.normalize_email(email)
    now = datetime.now(UTC)

    existing_link = (
        await session.execute(
            sa.select(PrincipalIdentity)
            .where(
                PrincipalIdentity.provider == provider,
                PrincipalIdentity.subject == subject,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_link is not None:
        account = await session.get(ConsoleAccount, existing_link.principal_id)
        existing_link.last_used_at = now
        await session.flush()
        return LinkOutcome(account=account, kind="linked")

    account = await console_identity.get_by_email(session, normalised)
    if account is None:
        return LinkOutcome(account=None, kind="unknown")

    # Existe la cuenta y no el vínculo: se cuelga de ella. **No se crea una
    # segunda cuenta ni una segunda membresía** — entrar con contraseña o con
    # Google tiene que aterrizar en el mismo sitio.
    session.add(
        PrincipalIdentity(
            id=uuid.uuid4(),
            principal_id=account.id,
            provider=provider,
            subject=subject,
            email_at_link=normalised,
            last_used_at=now,
        )
    )
    await session.flush()
    return LinkOutcome(account=account, kind="attached")


async def link_provider(
    session: AsyncSession,
    *,
    account: ConsoleAccount,
    provider: str,
    subject: str,
    email: str,
) -> PrincipalIdentity:
    """Cuelga el vínculo de una cuenta recién creada por el alta."""
    link = PrincipalIdentity(
        id=uuid.uuid4(),
        principal_id=account.id,
        provider=provider,
        subject=subject,
        email_at_link=console_identity.normalize_email(email),
        last_used_at=datetime.now(UTC),
    )
    session.add(link)
    await session.flush()
    return link
