"""Presupuesto: degradación y corte, en los cuatro casos (WP-20).

Los cuatro que exige el plan —blando y duro, por tenant y por partner—
más la propiedad que hace aceptable cortar y que es la que de verdad se
viene a proteger aquí:

    **el cliente final recibe un traspaso a una persona, no silencio.**

Un agente mudo delante de los clientes de un tercero es el peor fallo
posible de este producto: quien escribe no sabe que existe un
presupuesto, solo ve que el negocio no le contesta. Por eso hay un test
que afirma explícitamente que se escribió un saliente, y no solo que no
se abrió el turno.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from nexus_worker.metering.budget import (
    add_spend,
    evaluate,
    invalidate_policies,
)
from nexus_worker.runtime.budget_gate import (
    ESCALATION_ACTION,
    HANDOFF_MESSAGE,
    apply_hard_cutoff,
)

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Tenant,
    TenantPlan,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _fresh_policy_cache():
    invalidate_policies()
    yield
    invalidate_policies()


async def _seed_tenant(tenant_id: uuid.UUID) -> uuid.UUID:
    """Tenant + conversación abierta. Devuelve el id de la conversación."""
    sm = get_sessionmaker()
    async with sm() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name="Presupuesto",
                slug=f"presu-{tenant_id.hex[:8]}",
                plan=TenantPlan.PRO,
            )
        )
        await session.commit()

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        suffix = tenant_id.hex[:8]
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3462{suffix}",
            status=ChannelStatus.ACTIVE,
        )
        session.add(channel)
        await session.flush()
        customer = Customer(tenant_id=tenant_id, identifier=f"+3463{suffix}", name="cliente")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            tenant_id=tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        session.add(conv)
        await session.flush()
        conv_id = conv.id
        await session.commit()
    return conv_id


async def _policy(
    scope: str,
    scope_id: uuid.UUID,
    *,
    soft: str,
    hard: str,
    action: str = "both",
    period: str = "day",
) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text(
                "INSERT INTO budget_policies "
                "(scope, scope_id, meter, period, soft_limit, hard_limit, soft_action) "
                "VALUES (:s, :sid, 'cost_usd', :p, :soft, :hard, :act)"
            ),
            {
                "s": scope,
                "sid": str(scope_id),
                "p": period,
                "soft": soft,
                "hard": hard,
                "act": action,
            },
        )
        await session.commit()
    invalidate_policies()


async def _outbound(tenant_id: uuid.UUID, conv_id: uuid.UUID) -> list[str]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return list(
            (
                await session.execute(
                    sa.text(
                        "SELECT content FROM messages "
                        "WHERE conversation_id = :c AND direction = 'outbound' "
                        "ORDER BY created_at"
                    ),
                    {"c": str(conv_id)},
                )
            )
            .scalars()
            .all()
        )


# ── los cuatro casos ──────────────────────────────────────────────────


async def test_tenant_soft_limit_degrades_but_keeps_running(fake_redis) -> None:
    tenant_id = uuid.uuid4()
    await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="10.0000", hard="50.0000")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("12.5"))

    verdict = await evaluate(fake_redis, tenant_id=tenant_id)
    assert verdict.level == "soft"
    assert verdict.degrade_model and verdict.disable_grader
    # Lo importante del blando: NO corta. El turno sigue abriéndose.
    assert not verdict.is_hard


async def test_tenant_hard_limit_stops_opening_turns(fake_redis) -> None:
    tenant_id = uuid.uuid4()
    await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="10.0000", hard="50.0000")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("50.0"))

    verdict = await evaluate(fake_redis, tenant_id=tenant_id)
    assert verdict.is_hard
    assert verdict.scope == "tenant"


async def test_partner_soft_limit_degrades_a_tenant_that_is_within_its_own(fake_redis) -> None:
    """El motivo de que el nivel de partner exista.

    El tenant no ha gastado nada y su propio presupuesto está intacto;
    lo que se agotó es la bolsa del partner, que es quien paga. Sin este
    nivel, veinte clientes por debajo de su límite individual hunden el
    margen del partner sin activar nada.
    """
    tenant_id, partner_id = uuid.uuid4(), uuid.uuid4()
    await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="100.0000", hard="200.0000")
    await _policy("partner", partner_id, soft="30.0000", hard="60.0000", action="downgrade")
    await add_spend(fake_redis, scope="partner", scope_id=partner_id, amount=Decimal("35.0"))

    verdict = await evaluate(fake_redis, tenant_id=tenant_id, partner_id=partner_id)
    assert verdict.level == "soft"
    assert verdict.scope == "partner"
    # ``downgrade`` no apaga el grader: cada acción hace solo lo suyo.
    assert verdict.degrade_model and not verdict.disable_grader


async def test_partner_hard_limit_cuts_a_tenant_that_is_within_its_own(fake_redis) -> None:
    tenant_id, partner_id = uuid.uuid4(), uuid.uuid4()
    await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="100.0000", hard="200.0000")
    await _policy("partner", partner_id, soft="30.0000", hard="60.0000")
    await add_spend(fake_redis, scope="partner", scope_id=partner_id, amount=Decimal("61.0"))

    verdict = await evaluate(fake_redis, tenant_id=tenant_id, partner_id=partner_id)
    assert verdict.is_hard
    assert verdict.scope == "partner", "ganó el ámbito del tenant sobre el del partner"


# ── la propiedad que hace aceptable cortar ────────────────────────────


async def test_the_customer_gets_a_handoff_not_silence(fake_redis) -> None:
    tenant_id = uuid.uuid4()
    conv_id = await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="10.0000", hard="50.0000")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("50.0"))
    verdict = await evaluate(fake_redis, tenant_id=tenant_id)

    assert await apply_hard_cutoff(tenant_id=tenant_id, conversation_id=conv_id, verdict=verdict)

    outbound = await _outbound(tenant_id, conv_id)
    assert outbound == [HANDOFF_MESSAGE], "el cliente final se quedó sin respuesta"
    # Y el texto no le cuenta al cliente nada de nuestra contabilidad.
    for palabra in ("presupuesto", "límite", "coste", "budget"):
        assert palabra not in HANDOFF_MESSAGE.lower()


async def test_the_owner_is_told(fake_redis) -> None:
    """Si nadie se entera, el corte solo consigue que el negocio pierda
    clientes en silencio."""
    tenant_id = uuid.uuid4()
    conv_id = await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="10.0000", hard="50.0000")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("50.0"))
    verdict = await evaluate(fake_redis, tenant_id=tenant_id)
    await apply_hard_cutoff(tenant_id=tenant_id, conversation_id=conv_id, verdict=verdict)

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        actions = list(
            (
                await session.execute(
                    sa.text("SELECT action FROM audit_log WHERE tenant_id = :t"),
                    {"t": str(tenant_id)},
                )
            )
            .scalars()
            .all()
        )
    assert ESCALATION_ACTION in actions

    # El alerter tiene que saber traducir esa acción a una plantilla; si
    # no, la fila se escribe y no la lee nadie.
    from nexus_worker.streams.operator_alerts import _ACTION_TO_TEMPLATE

    assert ESCALATION_ACTION in _ACTION_TO_TEMPLATE


async def test_the_handoff_is_not_repeated_on_every_message(fake_redis) -> None:
    """Repetir el aviso en cada mensaje convierte el corte en spam hacia
    el cliente final."""
    tenant_id = uuid.uuid4()
    conv_id = await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="10.0000", hard="50.0000")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("50.0"))
    verdict = await evaluate(fake_redis, tenant_id=tenant_id)

    assert await apply_hard_cutoff(tenant_id=tenant_id, conversation_id=conv_id, verdict=verdict)
    assert not await apply_hard_cutoff(
        tenant_id=tenant_id, conversation_id=conv_id, verdict=verdict
    )
    assert len(await _outbound(tenant_id, conv_id)) == 1


# ── fail-open ─────────────────────────────────────────────────────────


async def test_a_tenant_without_a_policy_is_never_cut(fake_redis) -> None:
    """Lo contrario —cortar por defecto— convertiría cualquier despiste de
    configuración en una caída de servicio."""
    tenant_id = uuid.uuid4()
    await _seed_tenant(tenant_id)
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("9999"))

    verdict = await evaluate(fake_redis, tenant_id=tenant_id)
    assert verdict.level == "ok"


async def test_spending_is_counted_per_period(fake_redis) -> None:
    """El contador del día y el del mes son independientes: gastar hoy no
    puede consumir el presupuesto de mañana."""
    tenant_id = uuid.uuid4()
    await _seed_tenant(tenant_id)
    await _policy("tenant", tenant_id, soft="10.0000", hard="50.0000", period="day")
    await add_spend(fake_redis, scope="tenant", scope_id=tenant_id, amount=Decimal("60"))
    assert (await evaluate(fake_redis, tenant_id=tenant_id)).is_hard

    from datetime import UTC, datetime, timedelta

    manana = datetime.now(UTC) + timedelta(days=1)
    assert (await evaluate(fake_redis, tenant_id=tenant_id, now=manana)).level == "ok"
