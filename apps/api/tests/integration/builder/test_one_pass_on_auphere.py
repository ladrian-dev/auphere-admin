"""Requisito 68: Auphere paga una pasada completa por agente; las demás, la bolsa.

Decisión de Luis del 2026-11-05. La primera pasada de todas las pruebas la paga
«Construcción y pruebas». Guardar ya no las repite, y quien pida otra entera la cobra
la bolsa del cliente, sabiéndolo antes. Repetir lo que no pasa sigue en la partida, y
cambiar el nombre o el tono no toca las pruebas.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig, AgentConfigStatus, AuditLog, Job, Tenant
from nexus_api.db.models.agent_spec import AgentTest, AgentTestRun, AgentTestSuite

from ..business._business_world import Biz, write
from ..wallet._wallet_world import EUR_USD, UNIT, MoneyWorld, money, money_world
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}
TEST = {
    "name": "Pregunta el horario",
    "persona": "Cliente habitual",
    "first_message": "¿A qué hora abrís?",
    "plan": "Pregunta y se despide.",
    "criteria": [],
}
#: El agente de prueba no pasa a nadie: la primera pasa y la segunda falla, y las dos dicen
#: algo del agente.
STATES = ({"escalated": False}, {"escalated": True})


@pytest.fixture
async def world(db_session: AsyncSession) -> MoneyWorld:
    return await money_world(db_session, pool=30 * UNIT, roles=())


@pytest.fixture
async def biz(db_session: AsyncSession, world: MoneyWorld) -> Biz:
    biz = Biz(
        ref=world.us.ref,
        tenant_id=world.us.tenant_id,
        partner_id=world.partner_id,
        headers=world.headers,
    )
    await turn_reservas_on(db_session, biz)
    return biz


def _router() -> LLMRouter:
    provider = InMemoryProvider()
    provider.responder = lambda call: "info" if call.role == "classify" else "Abrimos a las 10."
    return LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model=""
    )


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _agent(client: Any, biz: Biz, fake_redis: Any, db_session: AsyncSession) -> uuid.UUID:
    """Un agente con su borrador y dos pruebas nuestras: una pasa y la otra falla."""
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    agent_id = uuid.UUID(body["result"]["agent_id"])
    async with tenant_scoped_session(db_session, biz.tenant_id):
        suite_id = await db_session.scalar(
            sa.select(AgentTestSuite.id).where(AgentTestSuite.agent_id == agent_id)
        )
        await db_session.execute(
            sa.update(AgentTest)
            .where(AgentTest.suite_id == suite_id)
            .values(archived_at=sa.func.now())
        )
    for n in range(2):
        added = await client.post(
            f"{_url(biz, agent_id)}/tests",
            json={**TEST, "name": f"{TEST['name']} {n}", "expected_state": STATES[n]},
            headers=biz.headers(),
        )
        assert added.status_code == 201, added.text
    return agent_id


async def _decide_the_disclosure(client: Any, biz: Biz, agent_id: uuid.UUID) -> None:
    read = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    spec = copy.deepcopy(read["spec"])
    spec["ai_disclosure"] = {
        "decided": True,
        "mode": "first_message",
        "text": "Soy el asistente virtual.",
    }
    patch = await client.patch(
        f"{_url(biz, agent_id)}/draft",
        json={"spec": spec},
        headers={**biz.headers(), "If-Match": f'"{read["revision"]}"'},
    )
    assert patch.status_code == 200, patch.text


async def _first_pass(client: Any, biz: Biz, fake_redis: Any, agent_id: uuid.UUID) -> None:
    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, None, router=_router())


async def _estimate(client: Any, biz: Biz, agent_id: uuid.UUID, scope: str = "all") -> dict:
    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs",
        json={"scope": scope, "dry_run": True},
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def _runs(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> list[AgentTestRun]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = await db_session.scalars(
            sa.select(AgentTestRun)
            .where(AgentTestRun.agent_id == agent_id)
            .order_by(AgentTestRun.created_at)
            .execution_options(populate_existing=True)
        )
        return list(rows.all())


async def _assign(client: Any, world: MoneyWorld, amount: int = 10 * UNIT) -> None:
    resp = await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(amount, "USD")},
        headers=world.headers(),
    )
    assert resp.status_code == 200, resp.text


# ── quién paga ─────────────────────────────────────────────────────────────────


async def test_the_first_full_pass_is_on_auphere_and_asks_nothing(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)

    estimate = await _estimate(client, biz, agent_id)
    assert estimate["payer"] == "auphere"
    assert estimate["fits"] is True

    await _first_pass(client, biz, fake_redis, agent_id)
    (run,) = await _runs(db_session, biz, agent_id)
    assert run.paid_by == "partner", "«Construcción y pruebas», como siempre"
    assert run.status == "done"


async def test_another_full_pass_is_charged_to_the_bag_and_says_so_first(
    client: Any, db_session: AsyncSession, biz: Biz, world: MoneyWorld, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    await _assign(client, world)

    estimate = await _estimate(client, biz, agent_id)
    assert estimate["payer"] == "client_bag"
    assert estimate["fits"] is True
    assert estimate["left"] == money(10 * UNIT, "USD")
    assert estimate["charge"]["currency"] == "USD"
    assert 0 < estimate["charge"]["amount_micros"] < 10 * UNIT

    unconfirmed = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert unconfirmed.status_code == 409, unconfirmed.text
    assert unconfirmed.json()["detail"]["code"] == "charge_not_confirmed"
    assert len(await _runs(db_session, biz, agent_id)) == 1, "sin confirmar no arranca nada"

    confirmed = await client.post(
        f"{_url(biz, agent_id)}/test-runs",
        json={"scope": "all", "confirmed_tests": 2},
        headers=biz.headers(),
    )
    assert confirmed.status_code == 202, confirmed.text
    runs = await _runs(db_session, biz, agent_id)
    assert [r.paid_by for r in runs] == ["partner", "client_bag"]
    async with tenant_scoped_session(db_session, biz.tenant_id):
        audit = await db_session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "agent.tests.charged_to_bag")
        )
    assert audit is not None, "gastar lo de un cliente deja rastro"
    assert audit.after_json["estimate"] == estimate["charge"]


async def test_a_bag_that_does_not_cover_the_pass_refuses_and_nothing_starts(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)

    estimate = await _estimate(client, biz, agent_id)
    assert (estimate["payer"], estimate["fits"]) == ("client_bag", False)

    refused = await client.post(
        f"{_url(biz, agent_id)}/test-runs",
        json={"scope": "all", "confirmed_tests": 2},
        headers=biz.headers(),
    )
    assert refused.status_code == 402, refused.text
    assert refused.json()["detail"]["code"] == "client_bag_not_enough"
    assert len(await _runs(db_session, biz, agent_id)) == 1


async def test_repeating_what_does_not_pass_stays_on_auphere(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Es como se arregla un agente, y cuesta céntimos."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)

    estimate = await _estimate(client, biz, agent_id, scope="failed")
    assert estimate["payer"] == "auphere"
    assert estimate["tests"] == 1

    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "failed"}, headers=biz.headers()
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["tests"] == 1
    await run_jobs(fake_redis, None, router=_router())
    runs = await _runs(db_session, biz, agent_id)
    assert [(r.scope, r.paid_by, r.status) for r in runs][-1] == ("failed", "partner", "done")


async def test_all_the_stale_tests_are_a_full_pass_whatever_it_is_called(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Editar el borrador las marca todas: «las desactualizadas» no es un atajo."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(sa.update(AgentTest).values(stale=True))

    assert (await _estimate(client, biz, agent_id, scope="affected"))["payer"] == "client_bag"


async def test_a_pass_that_did_not_finish_does_not_spend_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            AgentTestRun(
                id=uuid.uuid4(),
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                scope="all",
                reason="manual",
                status="failed",
                paid_by="partner",
            )
        )
    assert (await _estimate(client, biz, agent_id))["payer"] == "auphere"


async def test_a_pass_that_only_says_not_sure_does_not_spend_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Sin estado que comprobar y sin juez, no ha dicho nada del agente (68.1)."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(sa.update(AgentTest).values(expected_state={}))
    await _first_pass(client, biz, fake_redis, agent_id)
    assert (await _runs(db_session, biz, agent_id))[0].status == "done"
    assert (await _estimate(client, biz, agent_id))["payer"] == "auphere"


async def test_a_confirmation_does_not_cover_more_tests_than_it_saw(
    client: Any, db_session: AsyncSession, biz: Biz, world: MoneyWorld, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    await _assign(client, world)
    added = await client.post(
        f"{_url(biz, agent_id)}/tests",
        json={**TEST, "name": "Una más", "expected_state": {"escalated": False}},
        headers=biz.headers(),
    )
    assert added.status_code == 201, added.text

    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs",
        json={"scope": "all", "confirmed_tests": 2},
        headers=biz.headers(),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "charge_changed"


async def test_a_bag_in_another_currency_is_priced_in_it(
    client: Any, db_session: AsyncSession, world: MoneyWorld, fake_redis: Any
) -> None:
    biz = Biz(
        ref=world.es.ref,
        tenant_id=world.es.tenant_id,
        partner_id=world.partner_id,
        headers=world.headers,
    )
    await turn_reservas_on(db_session, biz)
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    resp = await client.post(
        f"/console/clients/{world.es.ref}/bag/assign",
        json={"amount": money(10 * UNIT, "EUR")},
        headers=world.headers(),
    )
    assert resp.status_code == 200, resp.text

    estimate = await _estimate(client, biz, agent_id)
    assert estimate["payer"] == "client_bag"
    assert estimate["left"] == money(10 * UNIT, "EUR")
    assert estimate["charge"]["currency"] == "EUR"
    in_usd = estimate["estimate"]["amount_micros"] / 10
    assert estimate["charge"]["amount_micros"] == pytest.approx(in_usd / float(EUR_USD), abs=2)


async def test_a_client_with_unlimited_consumption_stays_on_auphere(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    async with db_session.begin():
        await db_session.execute(
            sa.update(Tenant).where(Tenant.id == biz.tenant_id).values(unlimited_consumption=True)
        )
    assert (await _estimate(client, biz, agent_id))["payer"] == "auphere"


async def test_the_suite_says_who_pays_the_next_full_pass(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    url = f"{_url(biz, agent_id)}/tests"
    assert (await client.get(url, headers=biz.headers())).json()["next_full_pass"] == "auphere"
    await _first_pass(client, biz, fake_redis, agent_id)
    assert (await client.get(url, headers=biz.headers())).json()["next_full_pass"] == "client_bag"


async def test_a_bag_pass_stops_before_leaving_the_bag_without_balance(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    world: MoneyWorld,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una prueba no deja sin saldo a un agente que atiende (68.6)."""
    from nexus_api.services.testing import billing

    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    await _assign(client, world)
    resp = await client.post(
        f"{_url(biz, agent_id)}/test-runs",
        json={"scope": "all", "confirmed_tests": 2},
        headers=biz.headers(),
    )
    assert resp.status_code == 202, resp.text

    async def no_room(*_: Any, **_kw: Any) -> bool:
        return False

    monkeypatch.setattr(billing, "bag_keeps_room", no_room)
    await run_jobs(fake_redis, None, router=_router())

    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    assert (job["status"], job["error_code"]) == ("failed", "client_bag_low"), job
    run = (await _runs(db_session, biz, agent_id))[-1]
    assert run.status == "failed"
    assert run.summary["not_started"] == 2


# ── guardar ────────────────────────────────────────────────────────────────────


async def test_saving_runs_the_first_pass_and_never_again(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    await _decide_the_disclosure(client, biz, agent_id)
    preview = await client.get(f"{_url(biz, agent_id)}/publish-preview", headers=biz.headers())
    assert preview.json()["tests_on_save"] is True

    first = await client.post(f"{_url(biz, agent_id)}/publish", json={}, headers=biz.headers())
    assert first.status_code == 202, first.text
    await run_jobs(fake_redis, None, router=_router())
    assert [r.reason for r in await _runs(db_session, biz, agent_id)] == ["publish"]
    job = (
        await client.get(f"/console/jobs/{first.json()['job_id']}", headers=biz.headers())
    ).json()
    assert job["status"] == "failed" and job["error_code"] == "gate_blocked", (
        "una prueba en rojo: decidió la puerta, con la pasada ya hecha"
    )

    # Con el borrador que haya, y marcadas como desactualizadas: otra vez a guardar.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(sa.update(AgentTest).values(stale=True))
    preview = await client.get(f"{_url(biz, agent_id)}/publish-preview", headers=biz.headers())
    assert preview.json()["tests_on_save"] is False

    again = await client.post(f"{_url(biz, agent_id)}/publish", json={}, headers=biz.headers())
    assert again.status_code == 202, again.text
    await run_jobs(fake_redis, None, router=_router())
    assert len(await _runs(db_session, biz, agent_id)) == 1, "guardar no repite las pruebas"


async def test_a_version_never_tested_does_not_stop_at_the_gate_after_the_first_pass(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """La pasada se hizo con otra versión: se avisa, y no bloquea."""
    from nexus_api.db.models import Agent
    from nexus_api.services import publishing

    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(AgentTestRun)
            .where(AgentTestRun.agent_id == agent_id)
            .values(agent_config_id=None)
        )
        agent = await db_session.get(Agent, agent_id)
        draft = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        assert agent is not None and draft is not None
        gate = await publishing.evaluate_gate(
            db_session, agent=agent, version=draft, active=None, partner_id=biz.partner_id
        )
    codes = {i["code"] for i in gate.overridable}
    assert "tests_not_run" not in codes
    assert "version_not_tested" in {i["code"] for i in gate.warnings}


async def test_a_critical_in_red_survives_a_discarded_draft_or_a_restored_version(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Sin esto, descartar el borrador bastaba para publicar lo que nunca pasó."""
    from nexus_api.db.models import Agent
    from nexus_api.services import publishing

    agent_id = await _agent(client, biz, fake_redis, db_session)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(AgentTest)
            .where(AgentTest.expected_state == {"escalated": True})
            .values(critical=True)
        )
    await _first_pass(client, biz, fake_redis, agent_id)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        # Lo que queda tras descartarlo: la pasada no es de esta versión.
        await db_session.execute(
            sa.update(AgentTestRun)
            .where(AgentTestRun.agent_id == agent_id)
            .values(agent_config_id=None)
        )
        agent = await db_session.get(Agent, agent_id)
        draft = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        assert agent is not None and draft is not None
        gate = await publishing.evaluate_gate(
            db_session, agent=agent, version=draft, active=None, partner_id=biz.partner_id
        )
    assert "critical_test_failing" in {i["code"] for i in gate.overridable}


async def test_a_draft_no_test_can_fix_does_not_spend_the_pass(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """68.13: sin decidir el aviso de IA no se publica, pasen o no las pruebas. Corrían antes
    de decidir, y la única pasada de Auphere se iba en un borrador que no podía salir."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    read = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    spec = copy.deepcopy(read["spec"])
    spec["ai_disclosure"] = {"decided": False}
    patch = await client.patch(
        f"{_url(biz, agent_id)}/draft",
        json={"spec": spec},
        headers={**biz.headers(), "If-Match": f'"{read["revision"]}"'},
    )
    assert patch.status_code == 200, patch.text

    saved = await client.post(f"{_url(biz, agent_id)}/publish", json={}, headers=biz.headers())
    assert saved.status_code == 202, saved.text
    await run_jobs(fake_redis, None, router=_router())

    job = (
        await client.get(f"/console/jobs/{saved.json()['job_id']}", headers=biz.headers())
    ).json()
    assert job["status"] == "failed" and job["error_code"] == "gate_blocked"
    gate = next(b for b in job["progress"]["blocks"] if b.get("key") == "gate")
    assert [i["code"] for i in gate["hard"]] == ["ai_disclosure_undecided"]
    assert await _runs(db_session, biz, agent_id) == [], "nada que probar todavía"
    assert (await _estimate(client, biz, agent_id))["payer"] == "auphere"


async def test_a_review_blocker_stops_first_unless_someone_decides_to_skip_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Reserva y no tiene horario: se dice antes de pagar nada. Quien lo salta con un motivo
    sigue, y entonces sí hacen falta las pruebas."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _decide_the_disclosure(client, biz, agent_id)

    stopped = await client.post(f"{_url(biz, agent_id)}/publish", json={}, headers=biz.headers())
    assert stopped.status_code == 202, stopped.text
    await run_jobs(fake_redis, None, router=_router())
    job = (
        await client.get(f"/console/jobs/{stopped.json()['job_id']}", headers=biz.headers())
    ).json()
    assert job["error_code"] == "gate_blocked"
    gate = next(b for b in job["progress"]["blocks"] if b.get("key") == "gate")
    assert "no_hours" in {i["code"] for i in gate["overridable"]}
    assert await _runs(db_session, biz, agent_id) == []

    skipped = await client.post(
        f"{_url(biz, agent_id)}/publish",
        json={"override_reason": "Aún no tenemos el horario cerrado"},
        headers=biz.headers(),
    )
    assert skipped.status_code == 202, skipped.text
    await run_jobs(fake_redis, None, router=_router())
    assert [r.reason for r in await _runs(db_session, biz, agent_id)] == ["publish"]


# ── un cambio de Auphere ───────────────────────────────────────────────────────


async def _make_active(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        config = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        assert config is not None
        config.status = AgentConfigStatus.ACTIVE


@pytest.mark.parametrize("how", ["published", "draft"])
async def test_a_change_auphere_makes_gives_the_pass_back(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, how: str
) -> None:
    """68.14: Auphere le cambia las herramientas al agente, sus pruebas dejan de valer, y
    volver a probarlas no se le cobra a un cliente que no pidió nada."""
    from nexus_api.services.reservations import passing

    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    assert (await _estimate(client, biz, agent_id))["payer"] == "client_bag"

    if how == "published":
        await _make_active(db_session, biz, agent_id)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        if how == "published":
            changed = await passing.publish_without_reservas(db_session, actor="reservas:prueba")
        else:
            changed = await passing.prepare_agent_versions(
                db_session, enable=False, actor="reservas:prueba"
            )
    assert [c.agent_id for c in changed] == [agent_id]

    assert (await _estimate(client, biz, agent_id))["payer"] == "auphere"

    # Esa pasada también se paga una vez.
    await _first_pass(client, biz, fake_redis, agent_id)
    assert (await _estimate(client, biz, agent_id))["payer"] == "client_bag"


async def test_a_change_the_client_makes_does_not_give_the_pass_back(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Las pruebas se quedan desactualizadas igual, y aquí sí lo decidió él (68.4)."""
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)
    read = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    spec = copy.deepcopy(read["spec"])
    spec["tools"] = [t for t in spec["tools"] if not t.startswith("reservas.")]
    spec["procedures"] = []
    patch = await client.patch(
        f"{_url(biz, agent_id)}/draft",
        json={"spec": spec},
        headers={**biz.headers(), "If-Match": f'"{read["revision"]}"'},
    )
    assert patch.status_code == 200, patch.text
    assert (await _estimate(client, biz, agent_id))["payer"] == "client_bag"


# ── lo que marca y lo que no ───────────────────────────────────────────────────


async def test_a_change_of_the_ficha_marks_the_tests_and_runs_nothing(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        config = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        assert config is not None
        config.status = AgentConfigStatus.ACTIVE
        # El horario afecta a lo que depende de una cita.
        await db_session.execute(
            sa.update(AgentTest).values(stale=False, expected_state={"booking": {"created": False}})
        )

    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)

    async with tenant_scoped_session(db_session, biz.tenant_id):
        jobs = (await db_session.scalars(sa.select(Job).where(Job.kind == "tests"))).all()
        stale = (await db_session.scalars(sa.select(AgentTest.stale))).all()
    assert not jobs, "ninguna pasada por su cuenta"
    assert any(stale), "las afectadas quedan desactualizadas"


async def test_a_new_name_or_tone_keeps_the_tests_and_an_instruction_does_not(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, db_session)
    await _first_pass(client, biz, fake_redis, agent_id)

    async def edit(change: Any) -> None:
        read = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
        spec = copy.deepcopy(read["spec"])
        change(spec)
        patch = await client.patch(
            f"{_url(biz, agent_id)}/draft",
            json={"spec": spec},
            headers={**biz.headers(), "If-Match": f'"{read["revision"]}"'},
        )
        assert patch.status_code == 200, patch.text

    async def any_stale() -> bool:
        async with tenant_scoped_session(db_session, biz.tenant_id):
            rows = await db_session.scalars(
                sa.select(AgentTest.stale)
                .where(AgentTest.archived_at.is_(None))
                .execution_options(populate_existing=True)
            )
            return any(rows.all())

    assert await any_stale() is False

    def rename(spec: dict[str, Any]) -> None:
        spec["identity"]["name"] = "Recepción nueva"
        spec.setdefault("voice", {})
        spec["voice"].update({"tone": "cercano", "greeting": "¡Buenas!", "register": "usted"})

    await edit(rename)
    assert await any_stale() is False, "el nombre y el tono no repiten nada"

    def instruct(spec: dict[str, Any]) -> None:
        spec["identity"]["description"] = spec["identity"]["description"] + " Y confirma siempre."

    await edit(instruct)
    assert await any_stale() is True, "lo que cambia cómo atiende, sí"
