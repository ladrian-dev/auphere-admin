"""Spec 063, requisitos 3.2 y 3.5 — un borrador fallido dice por qué y no cobra.

El trabajo falla con ``builder_unavailable``, como siempre. El registro dice por qué
(``bad_json``, con su tipo y su posición), sin una palabra de lo que escribió el
modelo. Y el gasto va a «Construcción y pruebas» del partner, nunca a la bolsa del
cliente.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from ..business._business_world import Biz, new_business
from ._builder_world import FakeBuilder, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SECRET = "Atiende a cada clienta por su nombre"


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Spa Brisa")


async def test_a_broken_draft_is_named_and_not_charged_to_the_client(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers())
    assert resp.status_code == 202, resp.text
    broken = '{"rules": ["' + SECRET + '" "otra"]}'
    with capture_logs() as logs:
        await run_jobs(fake_redis, FakeBuilder(reply=broken))
    job = await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    assert job.json()["status"] == "failed"
    assert job.json()["error_code"] == "builder_unavailable"

    (failed,) = [e for e in logs if e["event"] == "jobs.agent_draft.unavailable"]
    assert failed["why"] == "bad_json"
    assert failed["detail"]["pos"] > 0 and failed["detail"]["error"].startswith("Expecting")
    assert SECRET not in json.dumps(logs, default=str)

    entries = await fake_redis.xrange("nexus:usage")
    sources = {e[1].get("source") for e in entries}
    assert "builder" in sources
    assert sources <= {"builder"}, "nada sale de la bolsa del cliente"
