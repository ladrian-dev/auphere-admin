"""Spec 063, requisitos 1.6 y 1.7 — «Cómo habla» es el único sitio de los idiomas.

Al guardar el AgentSpec en el borrador, ``voice`` se copia a
``policies.console.languages`` (lo que lee el turno), igual que el aviso de IA. Los
ajustes antiguos (``settings`` del borrador, la página de ajustes y el Companion)
ya no cambian los idiomas: los conservan.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from .builder._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft
from .business._business_world import Biz, new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Salón Rita")


async def _agent(client: Any, biz: Biz, fake_redis: Any) -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers())
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    job = await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    assert job.json()["status"] == "done", job.text
    return uuid.UUID(job.json()["result"]["agent_id"])


async def _patch(client: Any, url: str, biz: Biz, body: dict[str, Any]) -> dict[str, Any]:
    draft = (await client.get(url, headers=biz.headers())).json()
    resp = await client.patch(
        url, json=body, headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'}
    )
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def test_the_voice_is_copied_to_what_the_turn_reads(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    url = f"/console/clients/{biz.ref}/agents/{agent_id}/draft"
    spec = dict((await client.get(url, headers=biz.headers())).json()["spec"])
    disclosure = spec["ai_disclosure"]

    voice = {**(spec.get("voice") or {}), "languages": ["en", "es"], "languages_limited": True}
    out = await _patch(client, url, biz, {"spec": {**spec, "voice": voice}})
    assert out["settings"]["languages"] == {
        "primary": "en",
        "allowed": ["en", "es"],
        "limited": True,
    }
    assert out["spec"]["ai_disclosure"] == disclosure

    # Sin límite: la copia lo dice, y el principal sigue siendo el primero.
    voice = {"languages": ["es", "en"]}
    out = await _patch(client, url, biz, {"spec": {**out["spec"], "voice": voice}})
    assert out["settings"]["languages"] == {
        "primary": "es",
        "allowed": ["es", "en"],
        "limited": False,
    }


async def test_the_old_settings_do_not_change_the_languages(
    client: Any, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis)
    url = f"/console/clients/{biz.ref}/agents/{agent_id}/draft"
    spec = dict((await client.get(url, headers=biz.headers())).json()["spec"])
    out = await _patch(client, url, biz, {"spec": {**spec, "voice": {"languages": ["es", "en"]}}})
    kept = out["settings"]["languages"]

    settings = {**out["settings"], "languages": {"primary": "fr", "allowed": ["fr"]}}
    after = await _patch(client, url, biz, {"settings": settings})
    assert after["settings"]["languages"] == kept
