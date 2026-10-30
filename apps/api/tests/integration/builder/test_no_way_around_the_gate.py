"""Fallo ``restaurar-un-borrador-publica-sin-puerta`` — ningún camino se salta la puerta
(spec 047, requisito 23).

Una versión solo llega a los clientes finales si pasó la puerta o si una persona
con permiso la saltó con motivo, auditado:

- **el rollback** (consola de antes y panel de operador) solo vuelve a una versión
  que estuvo activa; un borrador que nunca se publicó responde 409
  ``rollback_target_never_published`` y no cambia nada;
- **la puerta no da por buena una versión sin probar**: con pruebas y sin pasada
  propia, ``tests_not_run``, que solo salta un owner o un admin con motivo. Así la
  ruta de publicar de la consola de antes, que publica en la petición, no puede
  saltarse las pruebas;
- **el promote del panel de operador** es un salto auditado: sin ``reason``, 422;
  con él, el motivo queda en la versión y en la auditoría.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.jobs.handlers import agent_tests as tests_handler
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig, AgentConfigStatus, AuditLog

from ..business._business_world import Biz, new_business, write
from ._builder_world import turn_reservas_on
from .test_agent_suite import BOOKING_TEST, Booker
from .test_publish_gate import WEEK, _agent, _save, _set_spec

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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


async def _versions(
    db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID
) -> dict[AgentConfigStatus, list[AgentConfig]]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(AgentConfig)
                .where(AgentConfig.agent_id == agent_id)
                .order_by(AgentConfig.version)
                .execution_options(populate_existing=True)
            )
        ).all()
    out: dict[AgentConfigStatus, list[AgentConfig]] = {s: [] for s in AgentConfigStatus}
    for row in rows:
        out[row.status].append(row)
    return out


async def _published_twice_and_a_draft(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> uuid.UUID:
    """v1 y v2 publicadas por «Guardar» (con sus pruebas) y un borrador encima."""
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    first = await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router)
    assert first["status"] == "done", first
    await _set_spec(client, biz, agent_id, rules=["No ofrezcas descuentos."])
    second = await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router)
    assert second["status"] == "done", second
    await _set_spec(client, biz, agent_id, rules=["No ofrezcas descuentos.", "Saluda."])
    return agent_id


async def test_a_rollback_never_puts_a_draft_live(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    admin_headers: dict[str, str],
) -> None:
    agent_id = await _published_twice_and_a_draft(client, db_session, biz, fake_redis)
    before = await _versions(db_session, biz, agent_id)
    (draft,) = before[AgentConfigStatus.STAGED]
    (active,) = before[AgentConfigStatus.ACTIVE]

    console = await client.post(
        f"/console/clients/{biz.ref}/agent/versions/{draft.version}/rollback?agent={agent_id}",
        headers=biz.headers(),
    )
    assert console.status_code == 409, console.text
    assert console.json()["detail"]["code"] == "rollback_target_never_published"
    assert f"/agents/{agent_id}/publish" in console.json()["detail"]["publish"]
    admin = await client.post(
        f"/admin/tenants/{biz.tenant_id}/agent-config/{draft.version}/rollback",
        headers=admin_headers,
    )
    assert admin.status_code == 409, admin.text
    assert admin.json()["detail"]["code"] == "rollback_target_never_published"

    after = await _versions(db_session, biz, agent_id)
    assert [v.id for v in after[AgentConfigStatus.ACTIVE]] == [active.id], "nothing changed"
    assert [v.id for v in after[AgentConfigStatus.STAGED]] == [draft.id]


async def test_a_rollback_to_a_version_that_was_live_still_works(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _published_twice_and_a_draft(client, db_session, biz, fake_redis)
    before = await _versions(db_session, biz, agent_id)
    (was_live,) = [v for v in before[AgentConfigStatus.ARCHIVED] if v.promoted_at is not None]

    back = await client.post(
        f"/console/clients/{biz.ref}/agent/versions/{was_live.version}/rollback?agent={agent_id}",
        headers=biz.headers(),
    )

    assert back.status_code == 200, back.text
    after = await _versions(db_session, biz, agent_id)
    assert [v.id for v in after[AgentConfigStatus.ACTIVE]] == [was_live.id]


async def test_a_version_with_tests_and_no_run_of_its_own_does_not_pass(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """La ruta de publicar de la consola de antes publica en la petición, sin
    encolar las pruebas: con ellas sin pasar, la puerta no deja."""
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    (draft,) = (await _versions(db_session, biz, agent_id))[AgentConfigStatus.STAGED]
    url = f"/console/clients/{biz.ref}/agent/versions/{draft.version}/publish?agent={agent_id}"

    blocked = await client.post(url, json={}, headers=biz.headers())

    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] == "gate_blocked"
    assert [i["code"] for i in detail["gate"]["overridable"]] == ["tests_not_run"]
    assert not (await _versions(db_session, biz, agent_id))[AgentConfigStatus.ACTIVE]

    # Un owner puede saltarla, con su motivo, que queda en la versión.
    forced = await client.post(
        url, json={"override_reason": "Lo pruebo en vivo con el dueño"}, headers=biz.headers()
    )
    assert forced.status_code == 200, forced.text
    (live,) = (await _versions(db_session, biz, agent_id))[AgentConfigStatus.ACTIVE]
    assert live.id == draft.id and live.override_reason == "Lo pruebo en vivo con el dueño"


async def test_the_operator_promote_is_an_audited_jump(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    admin_headers: dict[str, str],
) -> None:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    (draft,) = (await _versions(db_session, biz, agent_id))[AgentConfigStatus.STAGED]
    url = f"/admin/tenants/{biz.tenant_id}/agent-config/{draft.version}/promote"

    for body in (None, {}, {"reason": "   "}):
        missing = await client.post(url, json=body, headers=admin_headers)
        assert missing.status_code == 422, (body, missing.text)
        assert missing.json()["detail"]["code"] == "reason_required"
    assert not (await _versions(db_session, biz, agent_id))[AgentConfigStatus.ACTIVE]

    done = await client.post(
        url, json={"reason": "Incidencia: el cliente no puede esperar"}, headers=admin_headers
    )

    assert done.status_code == 200, done.text
    (live,) = (await _versions(db_session, biz, agent_id))[AgentConfigStatus.ACTIVE]
    assert live.id == draft.id
    assert live.override_reason == "Incidencia: el cliente no puede esperar"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        audit = await db_session.scalar(
            sa.select(AuditLog).where(
                AuditLog.action == "agent.publish", AuditLog.target == f"agent:{agent_id}"
            )
        )
    assert audit is not None
    assert audit.after_json["override_reason"] == "Incidencia: el cliente no puede esperar"
    assert audit.after_json["origin"] == "admin"
