"""Spec 047, T091 — guardar es publicar: la puerta (historia 9; requisito 23).

- **Las condiciones**: validador sin errores, críticas 3 de 3, regresión de 2
  puntos como mucho, aviso de IA decidido y revisión sin bloqueantes.
- **Una prueba normal en rojo** deja «Guardar igualmente», con confirmación.
- **Una crítica o un bloqueante**: solo owner o admin, con el motivo en la versión
  y en la auditoría. El aviso de IA y el validador no se saltan nunca.
- **Sin canales**: «Guardar y conectar un canal». **Con canales**: el diff en
  lenguaje llano.
- **Después**: el siguiente mensaje usa la versión nueva.
- **La misma puerta** en la consola, el admin y la API de partners.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.jobs.handlers import agent_tests as tests_handler
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
)
from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business, write
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on
from .test_agent_suite import BOOKING_TEST, Booker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}
DECIDED = {"decided": True, "mode": "first_message", "text": "Soy el asistente virtual."}


@pytest.fixture(autouse=True)
def one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tests_handler, "PARALLEL", 1)


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    # La barbería tiene Reservas encendido: sin él, la agenda cuenta como sin activar (D67).
    await turn_reservas_on(db_session, biz)
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _agent(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    *,
    tests: list[dict[str, Any]],
    disclosure: dict[str, Any] | None = None,
) -> uuid.UUID:
    """Un agente con su borrador, el aviso de IA decidido y solo ``tests`` en su
    suite (las del constructor se archivan para aislar lo que se prueba)."""
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
    for item in tests:
        added = await client.post(f"{_url(biz, agent_id)}/tests", json=item, headers=biz.headers())
        assert added.status_code == 201, added.text
    await _set_spec(client, biz, agent_id, ai_disclosure=disclosure or DECIDED)
    return agent_id


async def _set_spec(client: Any, biz: Biz, agent_id: uuid.UUID, **changes: Any) -> None:
    draft = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    spec = draft["spec"]
    spec.update(changes)
    resp = await client.patch(
        f"{_url(biz, agent_id)}/draft",
        json={"spec": spec},
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert resp.status_code == 200, resp.text


async def _save(
    client: Any,
    biz: Biz,
    agent_id: uuid.UUID,
    fake_redis: Any,
    router: Any,
    headers: Any = None,
    **body: Any,
) -> dict[str, Any]:
    resp = await client.post(
        f"{_url(biz, agent_id)}/publish", json=body, headers=(headers or biz.headers)()
    )
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, None, router=router)
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    return job


def _gate(job: dict[str, Any]) -> dict[str, Any]:
    return next(b for b in job["progress"]["blocks"] if b.get("key") == "gate")


NORMAL_TEST = {
    **BOOKING_TEST,
    "name": "Pide cita (normal)",
    "critical": False,
}


async def test_a_clean_draft_passes_the_gate_and_the_next_message_uses_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    preview = (
        await client.get(f"{_url(biz, agent_id)}/publish-preview", headers=biz.headers())
    ).json()
    # Sin canales, el botón dice «Guardar y conectar un canal» (23.4).
    assert preview["action"] == "save_and_connect" and preview["has_channels"] is False
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe("nexus:agent_config:promote")
    job = await _save(
        client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router, note="Primera versión"
    )
    assert job["status"] == "done", job
    result = job["result"]
    assert result["number"] == 1 and result["undo_until"]
    assert {c["condition"]: c["ok"] for c in result["gate"]["conditions"]} == {
        "validator": True,
        "critical_tests": True,
        "regression": True,
        "ai_disclosure": True,
        "review": True,
    }
    async with tenant_scoped_session(db_session, biz.tenant_id):
        active = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
    assert active is not None and active.note == "Primera versión" and active.gate is not None
    # 23.6: el cargador del agente se entera y el siguiente mensaje usa esta versión.
    message = None
    for _ in range(20):
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
        if message:
            break
    assert message is not None and message["data"] == f"{biz.tenant_id}:{agent_id}"


async def test_a_normal_test_in_red_lets_save_anyway_with_confirmation(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[NORMAL_TEST])
    blocked = await _save(client, biz, agent_id, fake_redis, Booker(set()).router)
    assert blocked["status"] == "failed" and blocked["error_code"] == "gate_blocked"
    gate = _gate(blocked)
    assert (
        gate["normal_failures"] == ["Pide cita (normal)"]
        and gate["hard"] == []
        and gate["overridable"] == []
    )
    # Una persona sin poder de saltar críticas sí puede «Guardar igualmente».
    builder = await add_console_member(db_session, partner_id=biz.partner_id, role="builder")
    anyway = await _save(
        client,
        biz,
        agent_id,
        fake_redis,
        Booker(set()).router,
        headers=builder["headers"],
        accept_normal_failures=True,
    )
    assert anyway["status"] == "done", anyway


async def test_a_critical_test_in_red_only_owner_or_admin_with_a_reason(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    blocked = await _save(
        client, biz, agent_id, fake_redis, Booker({1, 3}).router, accept_normal_failures=True
    )
    assert blocked["error_code"] == "gate_blocked"
    assert [i["code"] for i in _gate(blocked)["overridable"]] == ["critical_test_failing"]
    builder = await add_console_member(db_session, partner_id=biz.partner_id, role="builder")
    forbidden = await client.post(
        f"{_url(biz, agent_id)}/publish",
        json={"override_reason": "Lo arreglo luego"},
        headers=builder["headers"](),
    )
    assert (
        forbidden.status_code == 403 and forbidden.json()["detail"]["code"] == "override_forbidden"
    )
    owner = await _save(
        client,
        biz,
        agent_id,
        fake_redis,
        Booker({1, 3}).router,
        override_reason="La agenda de mentira falla a veces",
    )
    assert owner["status"] == "done", owner
    async with tenant_scoped_session(db_session, biz.tenant_id):
        active = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
        audit = await db_session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "agent.publish")
        )
    assert active is not None and active.override_reason == "La agenda de mentira falla a veces"
    assert (
        audit is not None
        and audit.after_json["override_reason"] == "La agenda de mentira falla a veces"
    )


async def test_the_ai_disclosure_and_the_validator_are_never_skipped(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(
        client, db_session, biz, fake_redis, tests=[BOOKING_TEST], disclosure={"decided": False}
    )
    blocked = await _save(
        client,
        biz,
        agent_id,
        fake_redis,
        Booker({1, 2, 3}).router,
        override_reason="Quiero publicar ya",
    )
    assert blocked["error_code"] == "gate_blocked"
    assert [i["code"] for i in _gate(blocked)["hard"]] == ["ai_disclosure_undecided"]


async def test_a_regression_of_more_than_two_points_is_a_blocker(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST, NORMAL_TEST])
    first = await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3, 4, 5, 6}).router)
    assert first["status"] == "done", first
    await _set_spec(
        client, biz, agent_id, rules=["No ofrezcas descuentos.", "Saluda por el nombre."]
    )
    # La crítica pasa 3/3; la normal, 1 de 3: la tasa baja de 100 a 66,67.
    second = await _save(
        client, biz, agent_id, fake_redis, Booker({1, 2, 3, 4}).router, accept_normal_failures=True
    )
    assert second["error_code"] == "gate_blocked"
    gate = _gate(second)
    assert [i["code"] for i in gate["overridable"]] == ["regression"]
    assert gate["reference_rate"] == 100.0 and gate["rate"] < 98


async def test_with_channels_the_preview_shows_the_diff_in_plain_words(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    assert (await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router))[
        "status"
    ] == "done"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            Channel(
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                type=ChannelType.WHATSAPP,
                provider="whatsapp_meta",
                provider_identifier="34600111222",
                config={},
                status=ChannelStatus.ACTIVE,
            )
        )
    await _set_spec(
        client, biz, agent_id, rules=["No ofrezcas descuentos.", "Saluda por el nombre."]
    )
    preview = (
        await client.get(f"{_url(biz, agent_id)}/publish-preview", headers=biz.headers())
    ).json()
    assert preview["action"] == "save_changes" and preview["has_channels"] is True
    assert {(d["part"], d["label"]) for d in preview["diff"]} >= {("rules", "Reglas")}


async def test_the_same_gate_in_the_old_console_and_the_operator_panel(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, admin_headers: dict[str, str]
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    # Una pasada en rojo de la crítica, con esta versión.
    run = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert run.status_code == 202
    await run_jobs(fake_redis, None, router=Booker(set()).router)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        draft = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
    assert draft is not None
    old = await client.post(
        f"/console/clients/{biz.ref}/agent/versions/{draft.version}/publish?agent={agent_id}",
        json={},
        headers=biz.headers(),
    )
    assert old.status_code == 409, old.text
    assert old.json()["detail"]["code"] == "gate_blocked"
    admin = await client.post(
        f"/admin/tenants/{biz.tenant_id}/agent-config/{draft.version}/promote",
        json={},
        headers=admin_headers,
    )
    # Spec 047 (requisito 23): the operator's promote is an audited jump: no
    # reason, no promote.
    assert admin.status_code == 422 and admin.json()["detail"]["code"] == "reason_required"
    forced = await client.post(
        f"/admin/tenants/{biz.tenant_id}/agent-config/{draft.version}/promote",
        json={"override": True, "reason": "Incidencia: se publica a mano"},
        headers=admin_headers,
    )
    assert forced.status_code == 200, forced.text
