"""Alta de un partner piloto en la consola (PLAN-CONSOLE-V1 CP-33).

Enciende ``partners.console_enabled`` y emite la **invitación de owner**
para la persona que va a administrar la consola. Por defecto NO crea la
membresía: nace cuando la persona abre el enlace y elige su contraseña
(``POST /console/invitations/{token}/accept``, que además crea el
principal en ``console_auth.principals`` desde ADR-032). Ese flujo es el
mismo que usa cualquier invitado y NO exige que exista un owner previo,
así que la primera persona entra directamente como owner.

Idempotente: si ya hay una invitación PENDING para ese correo la reutiliza
(no puede recuperar el token en claro: el script la revoca y emite una
nueva SOLO con ``--reissue``); si ya existe una membresía activa para ese
correo, no hace nada más que encender la consola.

Uso (lee NEXUS_DATABASE_URL del entorno):

    python scripts/seed_console_memberships.py \
        --partner-slug facelad --owner-email maria@facelad.com \
        --display-name "María" --enable-console

Opciones: ``--role`` (owner por defecto), ``--reissue`` (revoca la
pendiente y emite otra), ``--console-origin https://console.auphere.com``
(prefijo del enlace impreso), ``--email`` (intenta enviar el enlace con
``services/email.py``; best-effort — el enlace se imprime SIEMPRE).

``--set-password '…'`` es el atajo de **desarrollo y piloto**: crea el
principal y la membresía directamente, sin invitación ni enlace. Sirve
para levantar un entorno local o para desbloquear a alguien que perdió el
acceso. En un alta real se prefiere la invitación: nadie debería teclear
la contraseña de otra persona. Si el correo ya tiene principal, no la
reescribe (imprime que ya existe) y se limita a colgar la membresía —
incluida la reasignación del ``user_id`` de una membresía que apuntaba al
better-auth anterior.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from nexus_api.db.models import (
    InvitationStatus,
    MembershipStatus,
    Partner,
    PartnerInvitation,
    PartnerMembership,
    PartnerRole,
)
from nexus_api.repositories.partner_membership import PartnerInvitationRepository

ACCEPT_PATH = "/invite/{token}"


async def _seed_with_password(
    session: AsyncSession,
    *,
    partner: Partner,
    email: str,
    password: str,
    display_name: str | None,
    role: str,
    member: PartnerMembership | None,
) -> int:
    """``--set-password``: principal + membresía, sin enlace.

    Reasignar el ``user_id`` de una membresía existente es lo que hace
    utilizable este atajo tras ADR-032: las membresías sembradas antes
    apuntan al id de better-auth, que ya no autentica nada. Se apunta a
    la cuenta nueva y el resto de la fila (rol, invitado por, fechas) se
    conserva.
    """
    from nexus_api.services import console_identity

    try:
        console_identity.validate_password(password)
    except console_identity.PasswordPolicyError as exc:
        print(f"! {exc}", file=sys.stderr)
        return 2

    account = await console_identity.get_by_email(session, email)
    if account is None:
        account = await console_identity.create_account(
            session, email=email, password=password, display_name=display_name
        )
        print(f"✓ created console principal {email} ({account.id})")
    else:
        print(f"✓ console principal already exists for {email} ({account.id}) — password untouched")

    if member is not None:
        if member.user_id != str(account.id):
            previous = member.user_id
            member.user_id = str(account.id)
            await session.flush()
            print(f"✓ membership re-pointed from {previous} to {account.id}")
        else:
            print(f"✓ {email} is already an active {member.role} of {partner.slug}")
        return 0

    session.add(
        PartnerMembership(
            partner_id=partner.id,
            user_id=str(account.id),
            email=email,
            display_name=display_name,
            role=role,
            status=MembershipStatus.ACTIVE.value,
            accepted_at=datetime.now(UTC),
        )
    )
    await session.flush()
    print(f"✓ {email} is now {role} of {partner.slug} — sign in at the console with that password")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--partner-slug", required=True)
    ap.add_argument("--owner-email", required=True)
    ap.add_argument("--display-name", default=None)
    ap.add_argument(
        "--role", default=PartnerRole.OWNER.value, choices=[r.value for r in PartnerRole]
    )
    ap.add_argument(
        "--enable-console", action="store_true", help="set partners.console_enabled = true"
    )
    ap.add_argument(
        "--reissue", action="store_true", help="revoke a pending invitation and issue a new one"
    )
    ap.add_argument("--console-origin", default=os.environ.get("NEXUS_CONSOLE_ORIGIN", ""))
    ap.add_argument(
        "--email", action="store_true", help="also try to e-mail the link (best-effort)"
    )
    ap.add_argument(
        "--set-password",
        default=None,
        metavar="PASSWORD",
        help=(
            "dev/pilot only: create the principal and the membership directly, "
            "with no invitation link (min 12 characters)"
        ),
    )
    args = ap.parse_args()

    url = os.environ.get("NEXUS_DATABASE_URL")
    if not url:
        print("NEXUS_DATABASE_URL is not set", file=sys.stderr)
        return 2
    # Secret managers store the plain ``postgresql://`` form (that is what
    # psql and pgbouncer want); the async stack needs the driver spelled
    # out or SQLAlchemy reaches for psycopg2, which is not in the runtime
    # image. ``config.py`` does the same normalisation.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    email = args.owner_email.strip().lower()

    async with factory() as session, session.begin():
        partner = await session.scalar(sa.select(Partner).where(Partner.slug == args.partner_slug))
        if partner is None:
            print(f"partner {args.partner_slug!r} not found", file=sys.stderr)
            return 1
        if args.enable_console and not partner.console_enabled:
            partner.console_enabled = True
            print(f"✓ console enabled for {partner.slug}")
        elif partner.console_enabled:
            print(f"✓ console already enabled for {partner.slug}")
        else:
            print(f"! console NOT enabled for {partner.slug} (pass --enable-console)")

        member = await session.scalar(
            sa.select(PartnerMembership).where(
                PartnerMembership.partner_id == partner.id,
                PartnerMembership.email == email,
                PartnerMembership.status == MembershipStatus.ACTIVE.value,
            )
        )

        if args.set_password:
            return await _seed_with_password(
                session,
                partner=partner,
                email=email,
                password=args.set_password,
                display_name=args.display_name,
                role=args.role,
                member=member,
            )

        if member is not None:
            print(
                f"✓ {email} is already an active {member.role} of {partner.slug} — nothing to invite"
            )
            return 0

        pending = await session.scalar(
            sa.select(PartnerInvitation).where(
                PartnerInvitation.partner_id == partner.id,
                PartnerInvitation.email == email,
                PartnerInvitation.status == InvitationStatus.PENDING.value,
            )
        )
        if pending is not None and not args.reissue:
            print(
                f"✓ pending invitation for {email} already exists (expires {pending.expires_at:%Y-%m-%d}); "
                "the plaintext token cannot be recovered — pass --reissue to revoke it and issue a new link"
            )
            return 0
        if pending is not None:
            pending.status = InvitationStatus.REVOKED.value
            await session.flush()
            print("✓ revoked the previous pending invitation")

        invitation, token = await PartnerInvitationRepository(session).create(
            partner_id=partner.id, email=email, role=args.role, invited_by=None
        )
        accept_path = ACCEPT_PATH.format(token=token)
        link = (
            f"{args.console_origin.rstrip('/')}{accept_path}"
            if args.console_origin
            else accept_path
        )
        print(
            f"✓ invitation {invitation.id} ({args.role}) for {email}, expires {invitation.expires_at:%Y-%m-%d}"
        )
        print(f"  accept link: {link}")

        if args.email:
            from nexus_api.services.email import send_email

            sent = await send_email(
                to=email,
                subject=f"Invitación a la consola de {partner.name}",
                html=(
                    f"<p>{args.display_name or email}, te han invitado como <b>{args.role}</b> "
                    f"a la consola de partner de <b>{partner.name}</b> en Auphere.</p>"
                    f'<p><a href="{link}">Aceptar invitación</a> (el enlace caduca el '
                    f"{invitation.expires_at:%Y-%m-%d}).</p>"
                ),
            )
            print(
                f"  e-mail {'sent' if sent else 'NOT sent (email disabled or provider error) — send the link by hand'}"
            )
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
