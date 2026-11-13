"""La regla de disponibilidad de un conector por partner — spec 060, T002.

Requisitos 1.1 a 1.5: sin filas todo está disponible; la decisión propia de un
partner manda sobre el valor por defecto del conector; un cliente sin partner
sigue el valor por defecto; los canales y los conectores de sistema no entran.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    ConnectorAccessDefault,
    ConnectorPartnerAccess,
    Partner,
    Tenant,
    TenantPlan,
)
from nexus_api.services.connectors.availability import (
    ConnectorUnavailable,
    ensure_connector_available,
    unavailable_slugs_for_tenant,
)

pytestmark = pytest.mark.asyncio


async def _partner(session: AsyncSession, label: str) -> uuid.UUID:
    pid = uuid.uuid4()
    session.add(Partner(id=pid, name=f"Partner {label}", slug=f"p-{label}-{pid.hex[:6]}"))
    await session.flush()
    return pid


async def _tenant(session: AsyncSession, partner_id: uuid.UUID | None) -> uuid.UUID:
    tid = uuid.uuid4()
    session.add(
        Tenant(
            id=tid,
            name="Cliente",
            slug=f"t-{tid.hex[:8]}",
            plan=TenantPlan.PRO,
            partner_id=partner_id,
        )
    )
    await session.flush()
    return tid


def _default(slug: str, *, enabled: bool) -> ConnectorAccessDefault:
    return ConnectorAccessDefault(
        connector_slug=slug, enabled=enabled, reason="prueba", updated_by="test"
    )


def _decision(slug: str, partner_id: uuid.UUID, *, enabled: bool) -> ConnectorPartnerAccess:
    return ConnectorPartnerAccess(
        connector_slug=slug, partner_id=partner_id, enabled=enabled, reason="prueba", set_by="test"
    )


async def test_without_rows_everything_is_available(db_session: AsyncSession) -> None:
    """1.1: al desplegar, ningún partner ni cliente pierde nada."""
    a = await _partner(db_session, "a")
    t = await _tenant(db_session, a)
    assert await unavailable_slugs_for_tenant(db_session, t) == frozenset()
    await ensure_connector_available(db_session, t, "woocommerce")


async def test_disabled_by_default_hides_it_from_partners_without_a_decision(
    db_session: AsyncSession,
) -> None:
    a = await _partner(db_session, "a")
    t = await _tenant(db_session, a)
    db_session.add(_default("quedate", enabled=False))
    await db_session.flush()
    assert await unavailable_slugs_for_tenant(db_session, t) == frozenset({"quedate"})
    with pytest.raises(ConnectorUnavailable):
        await ensure_connector_available(db_session, t, "quedate")


async def test_a_partner_decision_wins_over_the_default(db_session: AsyncSession) -> None:
    """1.3: decisión propia `true` sobre un valor por defecto `false`, y al revés."""
    amacrux = await _partner(db_session, "amacrux")
    other = await _partner(db_session, "other")
    t_amacrux = await _tenant(db_session, amacrux)
    t_other = await _tenant(db_session, other)
    db_session.add_all(
        [
            _default("quedate", enabled=False),
            _decision("quedate", amacrux, enabled=True),
            _decision("woocommerce", other, enabled=False),
        ]
    )
    await db_session.flush()
    assert await unavailable_slugs_for_tenant(db_session, t_amacrux) == frozenset()
    assert await unavailable_slugs_for_tenant(db_session, t_other) == frozenset(
        {"quedate", "woocommerce"}
    )


async def test_a_client_without_partner_follows_the_default(db_session: AsyncSession) -> None:
    """1.4: aunque otro partner tenga decisión propia, el cliente sin partner no la hereda."""
    amacrux = await _partner(db_session, "amacrux")
    alone = await _tenant(db_session, None)
    db_session.add_all(
        [
            _default("quedate", enabled=False),
            _decision("quedate", amacrux, enabled=True),
            _decision("hubspot", amacrux, enabled=False),
        ]
    )
    await db_session.flush()
    assert await unavailable_slugs_for_tenant(db_session, alone) == frozenset({"quedate"})


async def test_channels_and_system_connectors_are_never_withheld(
    db_session: AsyncSession,
) -> None:
    """1.5: los canales y Google Calendar (de Reservas) no entran, aunque haya filas."""
    a = await _partner(db_session, "a")
    t = await _tenant(db_session, a)
    db_session.add_all(
        [
            _default("googlecalendar", enabled=False),
            _default("whatsapp_meta", enabled=False),
            _decision("tiktok_bm", a, enabled=False),
        ]
    )
    await db_session.flush()
    assert await unavailable_slugs_for_tenant(db_session, t) == frozenset()


async def test_the_slug_is_matched_in_lowercase(db_session: AsyncSession) -> None:
    a = await _partner(db_session, "a")
    t = await _tenant(db_session, a)
    db_session.add(_default("hubspot", enabled=False))
    await db_session.flush()
    with pytest.raises(ConnectorUnavailable):
        await ensure_connector_available(db_session, t, "HubSpot")


async def test_a_client_linked_only_through_partner_tenants_follows_that_partner(
    db_session: AsyncSession,
) -> None:
    """Research D4: un cliente creado desde el panel y vinculado después a un
    partner tiene ``tenants.partner_id`` vacío y solo el vínculo."""
    from nexus_api.db.models import PartnerTenant

    amacrux = await _partner(db_session, "amacrux")
    other = await _partner(db_session, "other")
    linked = await _tenant(db_session, None)
    db_session.add(PartnerTenant(partner_id=amacrux, external_client_ref="q-1", tenant_id=linked))
    db_session.add_all(
        [_default("quedate", enabled=False), _decision("quedate", amacrux, enabled=True)]
    )
    await db_session.flush()
    assert await unavailable_slugs_for_tenant(db_session, linked) == frozenset()

    # Vinculado a dos partners: lo más restrictivo.
    db_session.add(PartnerTenant(partner_id=other, external_client_ref="q-2", tenant_id=linked))
    await db_session.flush()
    assert await unavailable_slugs_for_tenant(db_session, linked) == frozenset({"quedate"})
