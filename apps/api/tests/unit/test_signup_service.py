"""El nacimiento de un partner — spec 006, Requisito 3.

Lo que se fija aquí:

- el alta crea **partner + invitación + membresía `owner`** en una sola
  operación, y si algo falla **no queda nada** (3.1, 3.2);
- el partner nace en Free —sin fila en ``partner_subscriptions``— y con la
  consola habilitada (3.3);
- la membresía se crea por el **único** camino que existe,
  ``PartnerInvitationRepository.accept()``, y no por uno paralelo (R1 de la
  investigación);
- un partner sin owner es el peor estado posible de esa tabla: nadie entra y
  nadie invita. Por eso el caso del fallo a mitad se prueba a propósito.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from nexus_api.services.signup import SignupBirthError, complete_signup

from nexus_api.db.models import (
    InvitationStatus,
    MembershipStatus,
    Partner,
    PartnerInvitation,
    PartnerMembership,
    SignupRequest,
    SignupStatus,
)

pytestmark = pytest.mark.asyncio


def _pending(email: str) -> SignupRequest:
    return SignupRequest(
        id=uuid.uuid4(),
        email=email,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        status=SignupStatus.PENDING.value,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )


async def _count(db_session, model, **where) -> int:
    stmt = sa.select(sa.func.count()).select_from(model)
    for col, val in where.items():
        stmt = stmt.where(getattr(model, col) == val)
    return int((await db_session.execute(stmt)).scalar_one())


class TestNaceEntero:
    async def test_crea_partner_cuenta_y_membresia_owner(self, db_session) -> None:
        email = f"maria-{uuid.uuid4().hex[:8]}@agencia.com"
        signup = _pending(email)
        db_session.add(signup)
        await db_session.flush()

        outcome = await complete_signup(
            db_session,
            signup=signup,
            company_name="Agencia Bonita",
            user_id=f"acct_{uuid.uuid4().hex[:12]}",
            display_name="María",
        )
        await db_session.commit()

        assert outcome.membership.role == "owner"
        assert outcome.membership.status == MembershipStatus.ACTIVE.value
        assert outcome.partner.console_enabled is True
        assert outcome.partner.status == "active"

    async def test_la_membresia_llega_por_una_invitacion_aceptada(self, db_session) -> None:
        """No hay un segundo camino a ``partner_memberships``: el alta emite una
        invitación de owner y la acepta. Si algún día alguien escribe la
        membresía a mano, esta prueba deja de encontrar la invitación."""
        email = f"ana-{uuid.uuid4().hex[:8]}@agencia.com"
        signup = _pending(email)
        db_session.add(signup)
        await db_session.flush()

        outcome = await complete_signup(
            db_session,
            signup=signup,
            company_name="Otra Agencia",
            user_id=f"acct_{uuid.uuid4().hex[:12]}",
            display_name=None,
        )
        await db_session.commit()

        inv = (
            await db_session.execute(
                sa.select(PartnerInvitation).where(
                    PartnerInvitation.partner_id == outcome.partner.id
                )
            )
        ).scalar_one()
        assert inv.role == "owner"
        assert inv.status == InvitationStatus.ACCEPTED.value
        assert inv.accepted_membership_id == outcome.membership.id

    async def test_la_solicitud_queda_consumida(self, db_session) -> None:
        email = f"luis-{uuid.uuid4().hex[:8]}@agencia.com"
        signup = _pending(email)
        db_session.add(signup)
        await db_session.flush()

        await complete_signup(
            db_session,
            signup=signup,
            company_name="Tercera",
            user_id=f"acct_{uuid.uuid4().hex[:12]}",
            display_name=None,
        )
        await db_session.commit()
        assert signup.status == SignupStatus.CONSUMED.value
        assert signup.consumed_at is not None


class TestNaceEnFree:
    async def test_sin_fila_de_suscripcion(self, db_session) -> None:
        """Un partner sin fila **es** Free: la ausencia es un estado válido y
        diseñado. Si algún día aparece una fila con ``free``, alguien sembró
        algo que no hacía falta."""
        from nexus_api.db.models.membership import PartnerSubscription

        signup = _pending(f"free-{uuid.uuid4().hex[:8]}@agencia.com")
        db_session.add(signup)
        await db_session.flush()
        outcome = await complete_signup(
            db_session,
            signup=signup,
            company_name="Sin Plan",
            user_id=f"acct_{uuid.uuid4().hex[:12]}",
            display_name=None,
        )
        await db_session.commit()
        assert await _count(db_session, PartnerSubscription, partner_id=outcome.partner.id) == 0


class TestOnoNaceNada:
    async def test_si_falla_a_mitad_no_queda_partner_sin_owner(self, db_session) -> None:
        """El peor estado de ``partner_memberships``: un partner al que nadie
        puede entrar y en el que nadie puede invitar.

        Se fuerza con un ``user_id`` que ya pertenece a otro partner, que es el
        fallo real que ``accept()`` levanta (``already_member``).
        """
        otro = Partner(id=uuid.uuid4(), name="Ya existe", slug=f"ya-{uuid.uuid4().hex[:8]}")
        db_session.add(otro)
        await db_session.flush()
        ocupado = f"acct_{uuid.uuid4().hex[:12]}"
        db_session.add(
            PartnerMembership(
                id=uuid.uuid4(),
                partner_id=otro.id,
                user_id=ocupado,
                email="ya@existe.com",
                role="owner",
                status=MembershipStatus.ACTIVE.value,
                accepted_at=datetime.now(UTC),
            )
        )
        await db_session.commit()

        email = f"choca-{uuid.uuid4().hex[:8]}@agencia.com"
        signup = _pending(email)
        db_session.add(signup)
        await db_session.commit()
        antes = await _count(db_session, Partner)

        with pytest.raises(SignupBirthError):
            await complete_signup(
                db_session,
                signup=signup,
                company_name="No Debe Nacer",
                user_id=ocupado,
                display_name=None,
            )
        await db_session.rollback()

        assert await _count(db_session, Partner) == antes, "quedó un partner huérfano"
        assert await _count(db_session, PartnerMembership, email=email) == 0
        await db_session.refresh(signup)
        assert signup.status == SignupStatus.PENDING.value, "la solicitud debe seguir usable"


class TestElSlug:
    async def test_dos_empresas_con_el_mismo_nombre_no_chocan(self, db_session) -> None:
        """Dos agencias pueden llamarse igual; lo que no puede repetirse es la
        referencia técnica con la que se las nombra."""
        slugs = []
        for _ in range(2):
            signup = _pending(f"dup-{uuid.uuid4().hex[:8]}@agencia.com")
            db_session.add(signup)
            await db_session.flush()
            outcome = await complete_signup(
                db_session,
                signup=signup,
                company_name="Agencia Repetida",
                user_id=f"acct_{uuid.uuid4().hex[:12]}",
                display_name=None,
            )
            await db_session.commit()
            slugs.append(outcome.partner.slug)
        assert slugs[0] != slugs[1]
        assert all(s.startswith("agencia-repetida") for s in slugs)
