"""Spec 047, T092 — versiones, deshacer, historial y restaurar (historia 9; requisito 24).

- «Deshacer» durante 10 minutos vuelve a la versión anterior; después, no.
- El historial: número, autor, fecha, nota, lo que cambió y sus pruebas.
- «Restaurar» crea un borrador con esa versión, que pasa la puerta.
- La política de modelo va con la versión.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.jobs.handlers import agent_tests as tests_handler
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig, AgentConfigStatus

from ..business._business_world import Biz, new_business, write
from ._builder_world import turn_reservas_on
from .test_agent_suite import BOOKING_TEST, Booker
from .test_publish_gate import WEEK, _agent, _save, _set_spec, _url

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


async def _active(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> AgentConfig:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE)
            .execution_options(populate_existing=True)
        )
    assert cfg is not None
    return cfg


async def _two_versions(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> uuid.UUID:
    agent_id = await _agent(client, db_session, biz, fake_redis, tests=[BOOKING_TEST])
    assert (await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router, note="v1"))[
        "status"
    ] == "done"
    await _set_spec(
        client, biz, agent_id, rules=["No ofrezcas descuentos.", "Saluda por el nombre."]
    )
    assert (await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router, note="v2"))[
        "status"
    ] == "done"
    return agent_id


async def test_undo_within_ten_minutes_and_not_after(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _two_versions(client, db_session, biz, fake_redis)
    assert (await _active(db_session, biz, agent_id)).note == "v2"
    undone = await client.post(f"{_url(biz, agent_id)}/publish/undo", headers=biz.headers())
    assert undone.status_code == 200, undone.text
    assert (await _active(db_session, biz, agent_id)).note == "v1"
    # La que se deshizo ya no se puede deshacer otra vez.
    again = await client.post(f"{_url(biz, agent_id)}/publish/undo", headers=biz.headers())
    assert again.status_code == 409 and again.json()["detail"]["code"] == "undo_window_closed"

    # Pasados los 10 minutos, tampoco.
    await _set_spec(client, biz, agent_id, rules=["Otra regla."])
    assert (await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router))[
        "status"
    ] == "done"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE)
            .values(undo_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    late = await client.post(f"{_url(biz, agent_id)}/publish/undo", headers=biz.headers())
    assert late.status_code == 409 and late.json()["detail"]["code"] == "undo_window_closed"


async def test_the_history_says_who_when_what_and_the_tests(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _two_versions(client, db_session, biz, fake_redis)
    history = (await client.get(f"{_url(biz, agent_id)}/history", headers=biz.headers())).json()
    assert [h["number"] for h in history] == [2, 1]
    newest = history[0]
    assert newest["note"] == "v2" and newest["status"] == "active"
    assert newest["published_at"] and newest["published_by"]
    assert "rules" in newest["changed"]
    assert newest["tests"]["rate"] == 100.0
    assert history[1]["status"] == "archived"


async def test_restore_makes_a_draft_that_passes_the_gate_with_its_model_policy(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _two_versions(client, db_session, biz, fake_redis)
    restored = await client.post(f"{_url(biz, agent_id)}/versions/1/restore", headers=biz.headers())
    assert restored.status_code == 200, restored.text
    draft = (await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())).json()
    assert draft["exists"] is True and draft["spec"]["rules"] == ["No ofrezcas descuentos."]
    assert draft["tests"]["stale"] >= 1
    # No se publica sola: pasa la puerta.
    assert (await _active(db_session, biz, agent_id)).note == "v2"
    blocked = await _save(client, biz, agent_id, fake_redis, Booker(set()).router)
    assert blocked["error_code"] == "gate_blocked"
    # Guardar otra vez sin cambiar nada no repite las pruebas: se pasan a mano.
    rerun = await client.post(
        f"{_url(biz, agent_id)}/test-runs", json={"scope": "all"}, headers=biz.headers()
    )
    assert rerun.status_code == 202
    from ._builder_world import run_jobs

    await run_jobs(fake_redis, None, router=Booker({1, 2, 3}).router)
    done = await _save(client, biz, agent_id, fake_redis, Booker({1, 2, 3}).router)
    assert done["status"] == "done", done
    assert (await _active(db_session, biz, agent_id)).spec["rules"] == ["No ofrezcas descuentos."]

    # La política de modelo va con la versión (24.4): restaurar la trae.
    economy = {"kind": "profile", "profile": "economy"}
    async with tenant_scoped_session(db_session, biz.tenant_id):
        v2 = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.agent_version_number == 2
            )
        )
        assert v2 is not None
        v2.policies = {**dict(v2.policies or {}), "model_policy": economy}
    back = await client.post(f"{_url(biz, agent_id)}/versions/2/restore", headers=biz.headers())
    assert back.status_code == 200, back.text
    async with tenant_scoped_session(db_session, biz.tenant_id):
        staged = await db_session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED)
            .execution_options(populate_existing=True)
        )
    assert staged is not None and staged.policies["model_policy"] == economy
    missing = await client.post(f"{_url(biz, agent_id)}/versions/99/restore", headers=biz.headers())
    assert missing.status_code == 404
