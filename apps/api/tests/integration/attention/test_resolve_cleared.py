"""Spec 071, T003 — los avisos que se resuelven solos (requisitos 2.1 a 2.5).

Cuando la regla deja de listar algo, los avisos guardados de esa condición quedan
resueltos (``handled_at``) y su clave se libera, para que una vuelta del problema vuelva
a avisar. Se hace donde hoy se rearma —asignar saldo, subir el tope del agente, subir la
partida, el canal reconectado— y en el repaso de cada hora del worker (el cambio de mes,
la cuenta que vuelve a tener saldo, el cobro que se arregla). Resolver no avisa de nada
(D3). Lo que sigue en la lista, sigue pendiente, y un «queda poco» no se resuelve
mientras esté «agotado» (research.md §R4).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signature import sign_meta_request

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Agent,
    Channel,
    ChannelStatus,
    ChannelType,
    ConsoleNotification,
    Partner,
)
from nexus_api.services.attention_live import resolve_cleared, resolve_cleared_detached
from nexus_api.services.business.writes import drain_after_commit
from nexus_api.services.wallet.turns import charge_turn
from tests.integration.clients._client_world import add_agent

from ._attention_world import (
    UNIT,
    MoneyWorld,
    assign,
    billing_state,
    build_spent,
    money,
    money_world,
    notice,
    notice_state,
    notices_of,
    set_purchased,
)

pytestmark = [pytest.mark.integration]


async def _count(db_session: Any, partner_id: uuid.UUID) -> int:
    async with db_session.begin():
        return int(
            await db_session.scalar(
                sa.select(sa.func.count())
                .select_from(ConsoleNotification)
                .where(ConsoleNotification.partner_id == partner_id)
            )
            or 0
        )


# ── la bolsa ────────────────────────────────────────────────────────────────


async def test_assigning_balance_resolves_the_empty_bag_and_frees_its_key(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=())
    empty = await notice(
        db_session, world.partner_id, "client.wallet.empty", ref=world.es.ref, severity="critical"
    )
    other = await notice(
        db_session, world.partner_id, "client.wallet.empty", ref=world.us.ref, severity="critical"
    )
    informative = await notice(db_session, world.partner_id, "client.activated", ref=world.es.ref)

    await assign(client, world, world.es.ref, 10 * UNIT)

    done = await notice_state(db_session, empty)
    assert done.resolved and done.dedupe_key is None
    assert not (await notice_state(db_session, other)).resolved, "su bolsa sigue sin saldo"
    info = await notice_state(db_session, informative)
    assert not info.resolved and info.dedupe_key is not None, "los informativos se leen"


async def test_low_is_not_resolved_while_the_bag_is_empty(client: Any, db_session: Any) -> None:
    world = await money_world(db_session, roles=())
    low = await notice(db_session, world.partner_id, "client.wallet.low", ref=world.es.ref)
    empty = await notice(
        db_session, world.partner_id, "client.wallet.empty", ref=world.es.ref, severity="critical"
    )
    await resolve_cleared_detached(world.partner_id)
    assert not (await notice_state(db_session, low)).resolved, "queda poco, y nada"
    assert not (await notice_state(db_session, empty)).resolved


async def test_resolving_says_nothing(client: Any, db_session: Any) -> None:
    """D3: ni correo, ni push, ni aviso. Solo cambia el estado de los que había."""
    world = await money_world(db_session, roles=())
    await assign(client, world, world.us.ref, 10 * UNIT)
    gone = await notice(
        db_session, world.partner_id, "client.wallet.empty", ref=world.us.ref, severity="critical"
    )
    before = await _count(db_session, world.partner_id)
    async with db_session.begin():
        resolved = await resolve_cleared(db_session, world.partner_id)
    assert resolved == 1
    assert await _count(db_session, world.partner_id) == before
    assert (await notice_state(db_session, gone)).resolved


# ── el tope del agente ──────────────────────────────────────────────────────


async def test_raising_the_agent_cap_resolves_its_notice(client: Any, db_session: Any) -> None:
    world = await money_world(db_session, roles=())
    await assign(client, world, world.us.ref, 10 * UNIT)
    agent = (await add_agent(db_session, world.us.tenant_id, "Ventas"))["agent_id"]
    await db_session.commit()
    assert agent is not None
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        await db_session.execute(
            sa.update(Agent).where(Agent.id == agent).values(lifecycle="published")
        )
    await db_session.commit()
    url = f"/console/clients/{world.us.ref}/agents/{agent}/cap"
    await client.put(url, json={"monthly_cap": money(UNIT, "USD")}, headers=world.headers())
    await charge_turn(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=agent,
        amount_usd=UNIT,
        usage_ref=f"channel:{uuid.uuid4().hex}",
    )
    (reached,) = await notices_of(db_session, world.partner_id, "agent.cap.reached")
    assert not reached.resolved and reached.dedupe_key is not None

    raised = await client.put(
        url, json={"monthly_cap": money(2 * UNIT, "USD")}, headers=world.headers()
    )
    assert raised.status_code == 200, raised.text
    await drain_after_commit()
    (reached,) = await notices_of(db_session, world.partner_id, "agent.cap.reached")
    assert reached.resolved and reached.dedupe_key is None


# ── la partida de construcción ──────────────────────────────────────────────


async def test_raising_the_build_cap_resolves_its_notices(
    client: Any, db_session: Any, admin_headers: dict[str, str]
) -> None:
    world = await money_world(db_session, roles=())
    await build_spent(db_session, world, 42 * UNIT)
    warning = await notice(db_session, world.partner_id, "build.budget.warning")
    # Antes de la 071 se colgaba de un cliente cualquiera: también se resuelve.
    legacy = await notice(db_session, world.partner_id, "build.budget.warning", ref=world.us.ref)
    await resolve_cleared_detached(world.partner_id)
    assert not (await notice_state(db_session, warning)).resolved, "al 84 %, sigue"

    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    resp = await client.put(
        f"/admin/partners/{world.partner_id}/build-budget",
        json={"cap": money(100 * UNIT, "USD"), "reason": "spec 071"},
        headers={**admin_headers, "X-Operator-Id": str(account.id)},
    )
    assert resp.status_code == 200, resp.text
    for notice_id in (warning, legacy):
        state = await notice_state(db_session, notice_id)
        assert state.resolved and state.dedupe_key is None


async def test_the_new_month_resolves_last_months_cap_in_the_hourly_pass(
    client: Any, db_session: Any
) -> None:
    """El aviso del mes pasado y la partida de este mes sin gastar: el repaso de cada
    hora lo resuelve."""
    from nexus_worker.streams.wallet_crons import attention_resolve_tick

    world = await money_world(db_session, roles=())
    exhausted = await notice(
        db_session, world.partner_id, "build.budget.exhausted", severity="critical"
    )
    await attention_resolve_tick()
    state = await notice_state(db_session, exhausted)
    assert state.resolved and state.dedupe_key is None


# ── la cuenta y el cobro ────────────────────────────────────────────────────


async def test_the_account_notices_resolve_when_the_balance_comes_back(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=())
    await assign(client, world, world.us.ref, 10 * UNIT)
    low = await notice(db_session, world.partner_id, "wallet.low")
    empty = await notice(db_session, world.partner_id, "wallet.empty", severity="critical")

    await set_purchased(db_session, world, 0)
    await resolve_cleared_detached(world.partner_id)
    assert not (await notice_state(db_session, empty)).resolved
    assert not (await notice_state(db_session, low)).resolved, "vacía también es baja"

    await set_purchased(db_session, world, UNIT)
    await resolve_cleared_detached(world.partner_id)
    assert (await notice_state(db_session, empty)).resolved, "ya no está vacía"
    assert not (await notice_state(db_session, low)).resolved, "1 de 11: sigue baja"

    await set_purchased(db_session, world, 100 * UNIT)
    await resolve_cleared_detached(world.partner_id)
    assert (await notice_state(db_session, low)).resolved


async def test_a_failed_payment_resolves_when_billing_is_current_and_can_warn_again(
    client: Any, db_session: Any
) -> None:
    from nexus_api.billing.ladder import move_to

    world = await money_world(db_session, roles=())
    async with db_session.begin():
        await move_to(db_session, partner_id=world.partner_id, state="payment_failed", notify=True)
    (failed,) = await notices_of(db_session, world.partner_id, "billing.payment_failed")
    await resolve_cleared_detached(world.partner_id)
    (failed,) = await notices_of(db_session, world.partner_id, "billing.payment_failed")
    assert not failed.resolved

    await billing_state(db_session, world.partner_id, "current")
    await resolve_cleared_detached(world.partner_id)
    (failed,) = await notices_of(db_session, world.partner_id, "billing.payment_failed")
    assert failed.resolved and failed.dedupe_key is None

    async with db_session.begin():
        await move_to(db_session, partner_id=world.partner_id, state="payment_failed", notify=True)
    again = await notices_of(db_session, world.partner_id, "billing.payment_failed")
    assert [n.resolved for n in again] == [True, False], "el segundo fallo vuelve a avisar"


# ── el canal ────────────────────────────────────────────────────────────────

META_APP_SECRET = "dev-meta-app-secret-change-me"
FIXTURES = Path(__file__).resolve().parents[4] / "channels" / "tests" / "fixtures" / "meta_webhooks"
WABA = "102290129340398"
NUMBER = "+34600000001"
PNID = "106540352242922"


async def _meta(client: Any, name: str) -> None:
    body = json.dumps(json.loads((FIXTURES / f"{name}.json").read_text())).encode()
    resp = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
    )
    assert resp.status_code == 200, resp.text


async def _meta_line(db_session: Any, world: MoneyWorld) -> None:
    """El número de las cargas de Meta, en el agente del cliente de EE. UU."""
    agent = (await add_agent(db_session, world.us.tenant_id, "Recepción", channel=None))["agent_id"]
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        db_session.add(
            Channel(
                tenant_id=world.us.tenant_id,
                agent_id=agent,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=NUMBER,
                config={"phone_number_id": PNID, "waba_id": WABA, "mode": "cloud_api"},
                status=ChannelStatus.ACTIVE,
                audience_mode="everyone",
            )
        )
    await db_session.commit()


async def test_a_reconnected_channel_resolves_its_problem_and_a_new_one_warns_again(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=())
    await _meta_line(db_session, world)

    await _meta(client, "account_update_partner_removed")
    (problem,) = await notices_of(db_session, world.partner_id, "channel.problem")
    assert problem.ref == world.us.ref and not problem.resolved

    await _meta(client, "account_update_reconnected")
    (problem,) = await notices_of(db_session, world.partner_id, "channel.problem")
    assert problem.resolved and problem.dedupe_key is None

    await _meta(client, "account_update_partner_removed")
    again = await notices_of(db_session, world.partner_id, "channel.problem")
    assert [n.resolved for n in again] == [True, False], "un segundo problema vuelve a avisar"


# ── fuera de la consola nueva ───────────────────────────────────────────────


async def test_the_old_console_keeps_its_notices(client: Any, db_session: Any) -> None:
    world = await money_world(db_session, roles=())
    async with db_session.begin():
        await db_session.execute(
            sa.update(Partner)
            .where(Partner.id == world.partner_id)
            .values(console_v2_enabled_at=None)
        )
    gone = await notice(db_session, world.partner_id, "build.budget.warning")
    assert await resolve_cleared_detached(world.partner_id) == 0
    assert not (await notice_state(db_session, gone)).resolved
