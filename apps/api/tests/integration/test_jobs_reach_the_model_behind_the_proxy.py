"""Fallo ``el-constructor-no-llega-al-modelo-en-staging`` — el barrido de los trabajos.

En staging el proxy LiteLLM es obligatorio (``NEXUS_LLM_PROXY_REQUIRED=true``) y
cada llamada a un modelo sale con la clave virtual de **un** partner. Un trabajo
sin partner atado no llega al modelo: «Generar borrador», la lectura de la web,
el constructor del cliente, las pruebas y la puerta de publicar fallaban
siempre allí, y en las pruebas (sin proxy) nada lo veía.

Esta prueba **barre** el registro de ``jobs-consumer`` (``default_registry``): cada
tipo registrado se corre con su manejador de verdad —y sus modelos por defecto,
no los de mentira de las demás pruebas— con el proxy obligatorio y un transporte
de mentira en el lugar de ``litellm.acompletion``. Cada tipo tiene que llegar al
modelo, y **cada** intento de llamada tiene que salir con la clave del partner
del cliente. Un tipo nuevo sin su mundo aquí pone la prueba en rojo: no se
enumeran los sitios conocidos, se recorre lo que hay.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import litellm
import pytest
import respx
from nexus_worker.config import get_worker_settings
from nexus_worker.jobs import DbJobStore, default_registry, drain_once
from nexus_worker.jobs.handlers import agent_tests as tests_handler
from nexus_worker.runtime import llm as runtime_llm
from nexus_worker.simulation import runner as sim_runner
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.llm_proxy import current_llm_proxy_partner

from .builder._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft
from .business._business_world import Biz, new_business, write
from .clients._reader_world import (
    CULTOR_READ,
    create_client,
    fake_dns,  # noqa: F401 - fixture
    page,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.usefixtures("fake_dns")]

BASE = "http://litellm.staging.test"
KEY = "sk-vk-sweep-partner-a"
SITE = "https://cultorbarber.com"
WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}
BOOKING_TEST = {
    "name": "Pide cita el lunes",
    "persona": "Cliente habitual",
    "first_message": "¿Me das cita el lunes a las 10?",
    "plan": "Acepta la hora que le ofrecen.",
    "expected_state": {},
    "criteria": [{"key": "confirms", "text": "Confirma la cita con día y hora."}],
    "critical": False,
}


@dataclass
class Transport:
    """``litellm.acompletion`` de mentira: contesta según el papel de la llamada
    y anota con qué clave salió cada una."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role = (kwargs.get("metadata") or {}).get("role")
        if role == "build":
            content = json.dumps(RECEPTION)
        elif role == "read_source":
            content = json.dumps(CULTOR_READ)
        elif role == "judge":
            content = json.dumps({"dimensions": []})
        else:
            content = "Claro, te doy cita el lunes a las 10:00."
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }


@dataclass
class Sweep:
    client: Any
    db_session: AsyncSession
    world: dict[str, Any]
    fake_redis: Any
    biz: Biz


async def _agent(s: Sweep) -> uuid.UUID:
    """Un agente con su borrador (el constructor de mentira, sin proxy: no es lo
    que se barre) y una prueba con criterio, para que el juez tenga trabajo."""
    resp = await start_draft(s.client, f"/console/clients/{s.biz.ref}", s.biz.headers())
    assert resp.status_code == 202, resp.text
    await run_jobs(s.fake_redis, FakeBuilder(reply=RECEPTION))
    job = await s.client.get(f"/console/jobs/{resp.json()['job_id']}", headers=s.biz.headers())
    agent_id = uuid.UUID(job.json()["result"]["agent_id"])
    added = await s.client.post(
        f"/console/clients/{s.biz.ref}/agents/{agent_id}/tests",
        json=BOOKING_TEST,
        headers=s.biz.headers(),
    )
    assert added.status_code == 201, added.text
    return agent_id


async def _agent_draft(s: Sweep) -> None:
    resp = await start_draft(s.client, f"/console/clients/{s.biz.ref}", s.biz.headers())
    assert resp.status_code == 202, resp.text


async def _client_builder(s: Sweep) -> None:
    resp = await s.client.post(f"{s.biz.url}/builder", headers=s.biz.headers())
    assert resp.status_code == 202, resp.text


async def _client_read(s: Sweep) -> None:
    created = await create_client(
        s.client,
        s.world["a"]["headers"](),
        name="Barbería Norte",
        niche="Barbería de barrio",
        info="cultorbarber.com",
    )
    assert created["read_job_id"]


async def _sector_identify(s: Sweep) -> None:
    """Spec 047, enmienda del 2026-10-29 (T200): el alta del cliente ya la dejó en
    cola (``new_business``); el sector se identifica con el modelo barato (``classify``)."""
    assert s.biz.ref


async def _tests(s: Sweep) -> None:
    agent_id = await _agent(s)
    resp = await s.client.post(
        f"/console/clients/{s.biz.ref}/agents/{agent_id}/test-runs",
        json={"scope": "all"},
        headers=s.biz.headers(),
    )
    assert resp.status_code == 202, resp.text


async def _publish(s: Sweep) -> None:
    agent_id = await _agent(s)
    resp = await s.client.post(
        f"/console/clients/{s.biz.ref}/agents/{agent_id}/publish",
        json={},
        headers=s.biz.headers(),
    )
    assert resp.status_code == 202, resp.text


#: Lo mínimo para que cada tipo llegue a su modelo. Un tipo registrado sin mundo
#: aquí es un trabajo que nadie ha visto salir por el proxy.
WORLDS: dict[str, Callable[[Sweep], Awaitable[None]]] = {
    "agent_draft": _agent_draft,
    "client_builder": _client_builder,
    "client_read": _client_read,
    "tests": _tests,
    "publish": _publish,
    "sector_identify": _sector_identify,
}


@pytest.fixture(autouse=True)
def _one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tests_handler, "PARALLEL", 1)
    monkeypatch.setattr(sim_runner, "_router_override", None)


@pytest.mark.parametrize("kind", sorted(default_registry.kinds()))
async def test_every_job_kind_reaches_the_model_with_its_partners_key(
    kind: str,
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = WORLDS.get(kind)
    assert world is not None, (
        f"job kind {kind!r} has no sweep world: show it reaching the model behind "
        "the mandatory proxy before registering it"
    )
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    await world(Sweep(client, db_session, console_world, fake_redis, biz))

    # Staging: el proxy es obligatorio y solo conoce la clave de este partner.
    monkeypatch.setenv("NEXUS_LLM_PROXY_REQUIRED", "true")
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", BASE)
    monkeypatch.setenv("LITELLM_PROXY_VIRTUAL_KEYS", json.dumps({str(biz.partner_id): KEY}))
    monkeypatch.setattr(get_worker_settings(), "llm_use_inmemory", False)
    transport = Transport()
    monkeypatch.setattr(litellm, "acompletion", transport)
    attempts: list[uuid.UUID | None] = []
    real_proxy_kwargs = runtime_llm._proxy_kwargs

    def spy(kwargs: dict[str, Any]) -> dict[str, Any]:
        attempts.append(current_llm_proxy_partner())
        return real_proxy_kwargs(kwargs)

    monkeypatch.setattr(runtime_llm, "_proxy_kwargs", spy)

    with respx.mock(assert_all_called=False) as web:
        web.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(200, text=""))
        web.get(f"{SITE}/").mock(
            return_value=httpx.Response(
                200, html=page("<p>Corte de pelo 15 €. Lunes de 10 a 20.</p>")
            )
        )
        ran = await drain_once(fake_redis, registry=default_registry, store=DbJobStore())

    assert ran >= 1, f"{kind}: nothing was queued"
    assert attempts, f"{kind}: the job never tried to reach a model"
    assert set(attempts) == {biz.partner_id}, (
        f"{kind}: every model call must carry the client's partner (saw {attempts})"
    )
    assert transport.calls, f"{kind}: no call left the process"
    assert {(c.get("api_base"), c.get("api_key")) for c in transport.calls} == {(BASE, KEY)}
