"""Spec 047, enmienda del 2026-10-29, T197 — los modelos los gestiona Auphere hasta
tener su panel (requisito 64.3; research D55).

Desde la consola no se cambia la política de modelo de un agente: ni escribiendo
otra en el AgentSpec del borrador ni pidiendo comprobar otra en «Calidad». La API
responde ``409 model_policy_managed``. Lo demás del borrador se sigue editando.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from .builder._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft
from .business._business_world import Biz, new_business, write

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


async def _agent(client: Any, biz: Biz, fake_redis: Any) -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers())
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    job = await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    assert job.json()["status"] == "done", job.text
    return uuid.UUID(job.json()["result"]["agent_id"])


async def test_the_console_cannot_change_the_model_policy(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    url = f"/console/clients/{biz.ref}/agents/{agent_id}/draft"
    draft = (await client.get(url, headers=biz.headers())).json()
    spec = dict(draft["spec"])
    current = spec["model_policy"]
    other = (
        {"kind": "profile", "profile": "max"}
        if current != {"kind": "profile", "profile": "max"}
        else {"kind": "profile", "profile": "economy"}
    )
    refused = await client.patch(
        url,
        json={"spec": {**spec, "model_policy": other}},
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "model_policy_managed"
    after = (await client.get(url, headers=biz.headers())).json()
    assert after["revision"] == draft["revision"], "no se escribió nada"
    assert after["spec"]["model_policy"] == current

    # Lo demás se sigue editando, con la política de siempre.
    edited = await client.patch(
        url,
        json={"spec": {**spec, "rules": ["Pide siempre el nombre."]}},
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["spec"]["model_policy"] == current


async def test_quality_cannot_check_another_policy_from_the_console(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    resp = await client.post(
        f"/console/clients/{biz.ref}/agents/{agent_id}/quality/check",
        json={"model_policy": {"kind": "profile", "profile": "max"}},
        headers=biz.headers(),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "model_policy_managed"
