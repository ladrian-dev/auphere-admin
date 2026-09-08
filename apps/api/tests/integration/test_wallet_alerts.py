"""D7 y D8: el saldo avisa antes de callar, y «activado» no miente.

El corte del 31-ago fue silencioso: los agentes dejaron de responder y no
hubo error, ni alarma, ni aviso. Estas dos piezas son lo que convierte ese
silencio en algo que alguien ve.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    ConsoleNotification,
    NotificationSeverity,
    Partner,
    PartnerAllocation,
    PartnerTenant,
    PartnerWallet,
    Tenant,
    TenantStatus,
)
from nexus_api.services.wallet_alerts import (
    clients_without_quota,
    evaluate_partner_wallet_alerts,
)

pytestmark = pytest.mark.asyncio

CAP = 500_000


async def _partner(db_session, *, available: int) -> Partner:
    """Partner con el wallet en el saldo pedido, vigente este mes."""
    partner = Partner(
        id=uuid.uuid4(),
        name="Avisos Test",
        slug=f"avisos-{uuid.uuid4().hex[:6]}",
        companion_monthly_token_cap=CAP,
        console_enabled=True,
        usage_alerts_enabled=True,
        usage_alert_recipients=[],
    )
    db_session.add(partner)
    await db_session.flush()
    wallet = await db_session.get(PartnerWallet, partner.id)
    expires = datetime.now(UTC) + timedelta(days=20)
    if wallet is None:
        wallet = PartnerWallet(
            partner_id=partner.id,
            included_remaining=available,
            purchased_remaining=0,
            included_expires_at=expires,
        )
        db_session.add(wallet)
    else:
        wallet.included_remaining = available
        wallet.purchased_remaining = 0
        wallet.included_expires_at = expires
    await db_session.commit()
    return partner


async def _kinds(db_session, partner_id: uuid.UUID) -> dict[str, str]:
    rows = await db_session.execute(
        sa.select(ConsoleNotification.kind, ConsoleNotification.severity).where(
            ConsoleNotification.partner_id == partner_id
        )
    )
    return {r[0]: r[1] for r in rows.all()}


async def test_full_wallet_says_nothing(db_session) -> None:
    partner = await _partner(db_session, available=CAP)
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.percent_used == 0.0
    assert ev.created == []
    assert await _kinds(db_session, partner.id) == {}


async def test_eighty_percent_warns_before_the_silence(db_session) -> None:
    partner = await _partner(db_session, available=int(CAP * 0.2))  # 80 % gastado
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.percent_used == 80.0
    assert ev.created == [80]
    kinds = await _kinds(db_session, partner.id)
    assert kinds["wallet.low"] == NotificationSeverity.WARNING.value
    assert "wallet.empty" not in kinds


async def test_empty_wallet_is_critical_not_a_warning(db_session) -> None:
    """A cero no es «te acercas al tope»: es que ya no se contesta."""
    partner = await _partner(db_session, available=0)
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.percent_used == 100.0
    assert ev.created == [80, 100]
    kinds = await _kinds(db_session, partner.id)
    assert kinds["wallet.empty"] == NotificationSeverity.CRITICAL.value


async def test_alerts_do_not_repeat_within_the_month(db_session) -> None:
    partner = await _partner(db_session, available=0)
    first = await evaluate_partner_wallet_alerts(db_session, partner)
    second = await evaluate_partner_wallet_alerts(db_session, partner)
    assert first.created == [80, 100]
    assert second.created == [], "un tick repetido no puede volver a avisar"
    total = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(ConsoleNotification.partner_id == partner.id)
    )
    assert int(total) == 2


async def test_a_client_out_of_quota_is_reported_even_with_partner_balance(db_session) -> None:
    """El caso más difícil de ver desde fuera: el partner tiene saldo y un
    cliente concreto ya no contesta porque agotó su asignación."""
    partner = await _partner(db_session, available=CAP)
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Cliente Sin Cuota",
            slug=f"sin-cuota-{tenant_id.hex[:8]}",
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerAllocation(partner_id=partner.id, tenant_id=tenant_id, cap=50_000, remaining=0)
    )
    # Un cap de 0 es una decisión del partner, no una incidencia.
    otro = uuid.uuid4()
    db_session.add(
        Tenant(
            id=otro,
            name="Cliente Apagado",
            slug=f"apagado-{otro.hex[:8]}",
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
        )
    )
    await db_session.flush()
    db_session.add(PartnerAllocation(partner_id=partner.id, tenant_id=otro, cap=0, remaining=0))
    await db_session.commit()

    out = await clients_without_quota(db_session, partner.id)
    assert out == [str(tenant_id)]


async def test_activation_says_when_the_client_cannot_serve(db_session) -> None:
    """D8 — «activado» con la cuota a cero avisa, no felicita."""
    from nexus_api.services.console_notifications import record_client_activation

    partner = await _partner(db_session, available=CAP)
    tenant_id = uuid.uuid4()
    ref = f"cliente-{uuid.uuid4().hex[:8]}"
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Recién Activado",
            slug=f"activado-{tenant_id.hex[:8]}",
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(partner_id=partner.id, external_client_ref=ref, tenant_id=tenant_id)
    )
    await db_session.commit()

    # Sin fila en partner_allocations: la puerta del canal está cerrada.
    async with db_session.begin():
        await record_client_activation(db_session, partner_id=partner.id, external_client_ref=ref)

    row = await db_session.scalar(
        sa.select(ConsoleNotification).where(
            ConsoleNotification.partner_id == partner.id,
            ConsoleNotification.kind == "client.activated",
        )
    )
    assert row is not None
    assert row.payload["can_serve"] is False
    assert row.severity == NotificationSeverity.WARNING.value


async def test_works_when_the_caller_already_has_a_transaction(db_session) -> None:
    """El fallo que apareció verificando en staging, no en los tests.

    Basta que quien llama haya hecho un ``execute`` antes —o que lea un
    atributo de un objeto ORM expirado, que dispara un refresh— para que la
    sesión tenga ya una transacción implícita. La evaluación no puede exigir
    una sesión recién abierta: es un contrato que nadie ve hasta que
    revienta en producción, y el cron lo habría tragado con su ``except``.
    """
    partner = await _partner(db_session, available=0)
    # Deja la sesión con transacción implícita abierta, como el llamador real.
    await db_session.execute(sa.select(sa.literal(1)))
    assert db_session.in_transaction()

    ev = await evaluate_partner_wallet_alerts(db_session, partner)

    assert ev.created == [80, 100]
    kinds = await _kinds(db_session, partner.id)
    assert kinds["wallet.empty"] == NotificationSeverity.CRITICAL.value
