"""El mundo del dinero de la consola nueva (spec 047, fase 18).

Un partner con la consola nueva y sin asignaciones de antes (cobra de las bolsas),
su cuenta en USD con lo comprado y el pool, y dos clientes: uno en España (bolsa
en EUR) y otro en Estados Unidos (bolsa en USD). El cambio del BCE del día queda
sembrado: 1 EUR = 1,08 USD.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    ClientWallet,
    FxRate,
    MembershipStatus,
    Partner,
    PartnerMembership,
    PartnerSubscription,
    PartnerTenant,
    PartnerWallet,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_api.db.models.business import BusinessProfile
from nexus_api.services.wallet.bags import as_client
from tests.conftest import add_console_member, console_headers

#: Una unidad de moneda en cien milésimas.
UNIT = 100_000
EUR_USD = Decimal("1.08")


@dataclass
class Client:
    tenant_id: uuid.UUID
    ref: str
    country: str


@dataclass
class MoneyWorld:
    partner_id: uuid.UUID
    user_id: str
    es: Client
    us: Client
    others: dict[str, Callable[..., dict[str, str]]] = field(default_factory=dict)

    def headers(self, **kw: Any) -> dict[str, str]:
        return console_headers(user_id=self.user_id, partner_id=self.partner_id, **kw)

    def as_role(self, role: str) -> dict[str, str]:
        return self.others[role]()


async def _client(
    db_session: AsyncSession, partner_id: uuid.UUID, slug: str, country: str
) -> Client:
    tenant_id = uuid.uuid4()
    ref = f"{slug}-{country.lower()}"
    db_session.add(
        Tenant(
            id=tenant_id,
            name=f"Cliente {country}",
            slug=f"{slug}-{country.lower()}-{tenant_id.hex[:4]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            partner_id=partner_id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=partner_id,
            external_client_ref=ref,
            tenant_id=tenant_id,
            client_name=f"Cliente {country}",
        )
    )
    await db_session.commit()
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(
            BusinessProfile(
                tenant_id=tenant_id,
                niche="Barbería",
                country=country,
                timezone="Europe/Madrid" if country == "ES" else "America/New_York",
            )
        )
    await db_session.commit()
    return Client(tenant_id=tenant_id, ref=ref, country=country)


async def money_world(
    db_session: AsyncSession,
    *,
    purchased: int = 100 * UNIT,
    pool: int = 10 * UNIT,
    roles: tuple[str, ...] = ("admin", "builder", "analyst", "billing"),
) -> MoneyWorld:
    partner_id = uuid.uuid4()
    slug = f"mw-{partner_id.hex[:6]}"
    user_id = f"user_mw_{partner_id.hex[:8]}"
    db_session.add(
        Partner(
            id=partner_id,
            name="Agencia del dinero",
            slug=slug,
            console_enabled=True,
            console_v2_enabled_at=datetime.now(UTC),
            max_clients=10,
            weekly_pool_tokens=500_000,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerSubscription(partner_id=partner_id, tier_code="business", state="current")
    )
    db_session.add(
        PartnerMembership(
            id=uuid.uuid4(),
            partner_id=partner_id,
            user_id=user_id,
            email="owner-mw@example.com",
            display_name="Owner",
            role="owner",
            status=MembershipStatus.ACTIVE.value,
        )
    )
    today = datetime.now(UTC).date()
    for day in (today, today - timedelta(days=40)):
        await db_session.execute(
            sa.text(
                "INSERT INTO fx_rates (date, base, quote, rate) VALUES (:d, 'EUR', 'USD', :r) "
                "ON CONFLICT (date, base, quote) DO UPDATE SET rate = EXCLUDED.rate"
            ),
            {"d": day, "r": EUR_USD},
        )
    await db_session.commit()
    # La cuenta la crea un disparador al dar de alta al partner.
    async with db_session.begin():
        await apply_partner_to_session(db_session, partner_id)
        await db_session.execute(
            sa.update(PartnerWallet)
            .where(PartnerWallet.partner_id == partner_id)
            .values(included_remaining=pool, purchased_remaining=purchased, currency="USD")
        )
    world = MoneyWorld(
        partner_id=partner_id,
        user_id=user_id,
        es=await _client(db_session, partner_id, slug, "ES"),
        us=await _client(db_session, partner_id, slug, "US"),
    )
    for role in roles:
        member = await add_console_member(db_session, partner_id=partner_id, role=role)
        world.others[role] = member["headers"]
    await db_session.commit()
    return world


async def bag_of(db_session: AsyncSession, world: MoneyWorld, tenant_id: uuid.UUID) -> ClientWallet:
    """La bolsa es del cliente: se lee con su contexto puesto (garantía 1)."""
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, tenant_id)
        bag = await db_session.scalar(
            sa.select(ClientWallet)
            .where(ClientWallet.tenant_id == tenant_id)
            .execution_options(populate_existing=True)
        )
    assert bag is not None
    return bag


async def account_of(db_session: AsyncSession, world: MoneyWorld) -> PartnerWallet:
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        account = await db_session.scalar(
            sa.select(PartnerWallet)
            .where(PartnerWallet.partner_id == world.partner_id)
            .execution_options(populate_existing=True)
        )
    assert account is not None
    return account


def money(amount: int, currency: str) -> dict[str, Any]:
    return {"amount_micros": amount, "currency": currency}


__all__ = [
    "EUR_USD",
    "UNIT",
    "Client",
    "FxRate",
    "MoneyWorld",
    "account_of",
    "as_client",
    "bag_of",
    "date",
    "money",
    "money_world",
]
