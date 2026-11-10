"""Fallo ``el-constructor-no-llega-al-modelo-en-staging`` — lo que llama a un modelo
fuera de los trabajos.

Con el proxy obligatorio (staging), cada llamada sale con la clave virtual de
quien la paga: la del partner del cliente, o la de Auphere (``platform``) cuando
no hay partner. Aquí, con el modelo de verdad de cada sitio —no el de mentira de
las demás pruebas— y un transporte falso en el lugar de ``litellm.acompletion``:

- el **copiloto** de la consola, con la del partner de quien pregunta;
- la **evaluación del constructor** y la **calibración del juez** del panel de
  operador, con la de Auphere, nunca la de un partner.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import litellm
import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.config import get_worker_settings
from nexus_worker.runtime import llm as runtime_llm
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.sector_tests import set_calibration_judge, set_eval_model
from nexus_api.api.console.agent_copilot import set_copilot_model
from nexus_api.core.llm_proxy import current_llm_proxy_partner, in_llm_proxy_platform_scope
from nexus_api.services import operator_identity

from ..business._business_world import Biz, new_business
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BASE = "http://litellm.staging.test"
PARTNER_KEY = "sk-vk-partner-a"
OTHER_KEY = "sk-vk-partner-b"
PLATFORM_KEY = "sk-vk-auphere-platform"


@dataclass
class Proxy:
    """El proxy de staging, de mentira: anota quién paga cada intento y con qué
    clave salió cada llamada."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    payers: list[str] = field(default_factory=list)

    async def acompletion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role = (kwargs.get("metadata") or {}).get("role")
        content = json.dumps(RECEPTION) if role == "build" else json.dumps({"dimensions": []})
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    @property
    def keys(self) -> set[tuple[Any, Any]]:
        return {(c.get("api_base"), c.get("api_key")) for c in self.calls}


@pytest.fixture
def staging_proxy(
    monkeypatch: pytest.MonkeyPatch, console_world: dict[str, Any]
) -> Iterator[Proxy]:
    proxy = Proxy()
    monkeypatch.setenv("NEXUS_LLM_PROXY_REQUIRED", "true")
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", BASE)
    monkeypatch.setenv(
        "LITELLM_PROXY_VIRTUAL_KEYS",
        json.dumps(
            {
                str(console_world["a"]["partner_id"]): PARTNER_KEY,
                str(console_world["b"]["partner_id"]): OTHER_KEY,
                "platform": PLATFORM_KEY,
            }
        ),
    )
    monkeypatch.setattr(get_worker_settings(), "llm_use_inmemory", False)
    monkeypatch.setattr(litellm, "acompletion", proxy.acompletion)
    real = runtime_llm._proxy_kwargs

    def spy(kwargs: dict[str, Any]) -> dict[str, Any]:
        partner = current_llm_proxy_partner()
        proxy.payers.append(
            str(partner) if partner else ("platform" if in_llm_proxy_platform_scope() else "none")
        )
        return real(kwargs)

    monkeypatch.setattr(runtime_llm, "_proxy_kwargs", spy)
    yield proxy


@pytest_asyncio.fixture
async def ops(db_session: AsyncSession, admin_headers: dict[str, str]) -> dict[str, str]:
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-proxy-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def test_the_copilot_goes_out_with_the_partners_key(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    fake_redis: Any,
    staging_proxy: Proxy,
) -> None:
    biz: Biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers())
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    agent_id = job["result"]["agent_id"]

    set_copilot_model(None)  # el modelo de verdad del copiloto
    asked = await client.post(
        f"/console/clients/{biz.ref}/agents/{agent_id}/copilot",
        json={"message": "¿Por qué dice que hay aparcamiento?"},
        headers=biz.headers(),
    )

    assert asked.status_code == 200, asked.text
    assert staging_proxy.payers, "the copilot never tried to reach its model"
    assert set(staging_proxy.payers) == {str(biz.partner_id)}
    assert staging_proxy.keys == {(BASE, PARTNER_KEY)}


async def test_the_builder_eval_goes_out_with_auphere_s_key(
    client: Any, ops: dict[str, str], staging_proxy: Proxy
) -> None:
    """La evaluación del constructor la paga Auphere: no hay partner, y nunca
    sale con la clave de uno."""
    set_eval_model(None)
    resp = await client.post("/admin/builder/eval", json={"limit": 1}, headers=ops)

    assert resp.status_code == 201, resp.text
    assert staging_proxy.payers and set(staging_proxy.payers) == {"platform"}
    assert staging_proxy.keys == {(BASE, PLATFORM_KEY)}


async def test_the_judge_calibration_goes_out_with_auphere_s_key(
    client: Any, db_session: AsyncSession, ops: dict[str, str], staging_proxy: Proxy
) -> None:
    set_calibration_judge(None)
    async with db_session.begin():
        deployment = await db_session.scalar(sa.text("SELECT id FROM model_profiles LIMIT 1"))
    try:
        resp = await client.post(
            "/admin/builder/judge-calibration",
            json={"deployment_id": str(deployment)},
            headers=ops,
        )
        assert resp.status_code == 201, resp.text
        assert staging_proxy.payers and set(staging_proxy.payers) == {"platform"}
        assert staging_proxy.keys == {(BASE, PLATFORM_KEY)}
    finally:
        async with db_session.begin():
            await db_session.execute(
                sa.text("DELETE FROM model_task_certifications WHERE task = 'judge'")
            )
