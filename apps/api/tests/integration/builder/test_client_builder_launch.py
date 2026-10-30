"""Spec 047, enmienda del 2026-10-29, T194 — el constructor del cliente, en marcha
(requisito 60; research D51).

- Se lanza solo en segundo plano: al terminar la lectura (tras identificar el
  sector) y al cambiar el sector.
- Es idempotente: para la misma ficha (la misma huella) no genera dos veces.
- Si el modelo no responde, reintenta 3 veces con espera creciente y queda
  fallido con su motivo.
- Sus propuestas son sugerencias de sección («Sugerido · confirma»); los agentes
  sugeridos se guardan aparte y la consola los lee; lo descartado no vuelve.
- Nada entra en el prompt hasta que una persona lo acepta.
- Se mide en «Construcción y pruebas».
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, Job
from nexus_api.db.models.business import BusinessFaq, BusinessProfile, BusinessSuggestion
from nexus_api.services.business.writes import drain_after_commit

from ..business._business_world import Biz, new_business, read, write
from ._builder_world import FakeBuilder

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

REPLY: dict[str, Any] = {
    "policies": {"cancellation": "Avisa con 24 horas para liberar el hueco."},
    "faqs": [{"q": "¿Hay aparcamiento?", "a": "Sí, detrás del local."}],
    "agents": [
        {
            "name": "Recepción",
            "description": "Atiende las citas por WhatsApp y recuerda la política de cancelación.",
            "role": "reception",
        },
        {
            "name": "Ventas",
            "description": "Vende bonos y productos de la barbería por WhatsApp.",
            "role": "sales",
        },
        {"name": "Raro", "description": "Una descripción que sirve para algo.", "role": "boss"},
    ],
}


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


class Flaky(FakeBuilder):
    """Falla las ``failures`` primeras veces; después contesta ``reply``."""

    def __init__(self, failures: int, reply: dict[str, Any]) -> None:
        super().__init__(reply=reply)
        self.failures = failures

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        if len(self.calls) < self.failures:
            self.calls.append(messages)
            raise TimeoutError("the provider did not answer")
        return await super().__call__(messages)


async def run(fake_redis: Any, builder: FakeBuilder | None, sleep: Sleeps | None = None) -> int:
    """Corre lo que haya en cola: la identificación del sector (sin modelo) y el
    constructor del cliente con el modelo que se le dé."""
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.client_builder import make_client_builder_handler
    from nexus_worker.jobs.handlers.sector_identify import make_sector_identify_handler

    registry = JobRegistry()
    registry.register(
        "sector_identify",
        make_sector_identify_handler(complete_factory=lambda _t: None),
        timeout_s=30,
    )
    registry.register(
        "client_builder",
        make_client_builder_handler(complete_factory=lambda _t: builder, sleep=sleep or Sleeps()),
        timeout_s=60,
    )
    ran = await drain_once(fake_redis, registry=registry, store=DbJobStore())
    await drain_after_commit()
    return ran


async def jobs_of(db_session: AsyncSession, tenant_id: uuid.UUID, kind: str) -> list[Job]:
    async with tenant_scoped_session(db_session, tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(Job)
                .where(Job.kind == kind)
                .order_by(Job.created_at, Job.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    return list(rows)


async def suggested(client: Any, biz: Biz) -> list[dict[str, Any]]:
    resp = await client.get(f"/console/clients/{biz.ref}/suggested-agents", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    agents: list[dict[str, Any]] = resp.json()["agents"]
    return agents


async def put_basics(client: Any, biz: Biz, body: dict[str, Any]) -> dict[str, Any]:
    revision = (await read(client, biz, "/basics"))["revision"]
    return await write(client, biz, "PUT", "/basics", body, revision=revision)


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Barbería Cultor")


async def test_it_starts_when_the_sector_changes_and_once_per_ficha(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    from nexus_api.services.builder.client_profile import launch_client_builder

    assert await jobs_of(db_session, biz.tenant_id, "client_builder") == []
    await run(fake_redis, None)  # el sector del alta: de nada a «Barbería»
    (first,) = await jobs_of(db_session, biz.tenant_id, "client_builder")
    assert first.created_by is None, "lo lanza el sistema, no una persona"
    fingerprint = first.progress["input"]["fingerprint"]
    assert len(fingerprint) == 64

    # La misma ficha: no se genera dos veces.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        assert await launch_client_builder(db_session, reason="sector") is None
    assert len(await jobs_of(db_session, biz.tenant_id, "client_builder")) == 1

    # Una persona cambia el sector: otra ficha, otra pasada.
    await run(fake_redis, None)
    await put_basics(client, biz, {"sector": {"key": "clinica", "label": "Clínica dental"}})
    await drain_after_commit()
    jobs = await jobs_of(db_session, biz.tenant_id, "client_builder")
    assert len(jobs) == 2 and jobs[1].progress["input"]["fingerprint"] != fingerprint


async def test_after_the_reading_it_starts_through_the_sector(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    from nexus_api.services.business import sector as sector_service

    await run(fake_redis, None)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(Job)
            .where(Job.kind == "client_builder")
            .values(status="failed", error_code="timeout", finished_at=sa.func.now())
        )
        profile = await db_session.get(BusinessProfile, biz.tenant_id)
        assert profile is not None
        profile.info = "Barbería de barrio con cita previa."  # la ficha cambió al leerla
        await sector_service.request_identification(db_session, reason="read", after_read=True)
    await drain_after_commit()
    await run(fake_redis, None)  # el sector no cambia, pero terminó una lectura
    builders = await jobs_of(db_session, biz.tenant_id, "client_builder")
    assert builders[-1].status == "queued" and builders[-1].progress["input"]["reason"] == "read"


async def test_it_retries_three_times_and_then_fails_with_its_reason(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await run(fake_redis, None)  # el sector y, con él, el constructor en cola
    sleeps = Sleeps()
    flaky = Flaky(failures=2, reply=REPLY)
    await run(fake_redis, flaky, sleeps)
    (job,) = await jobs_of(db_session, biz.tenant_id, "client_builder")
    assert job.status == "done", job.error_code
    assert len(flaky.calls) == 3 and sleeps.waits == [2.0, 4.0], "espera creciente"

    await put_basics(client, biz, {"sector": {"key": "clinica", "label": "Clínica dental"}})
    await drain_after_commit()
    sleeps = Sleeps()
    dead = Flaky(failures=99, reply=REPLY)
    await run(fake_redis, dead, sleeps)
    job = (await jobs_of(db_session, biz.tenant_id, "client_builder"))[-1]
    assert job.status == "failed" and job.error_code == "builder_unavailable"
    assert len(dead.calls) == 4 and sleeps.waits == [2.0, 4.0, 8.0], "tres reintentos y para"
    # No bloquea nada del cliente: la ficha se sigue editando.
    await put_basics(client, biz, {"name": "Cultor"})


async def test_proposals_wait_in_their_section_and_agents_are_only_suggested(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await run(fake_redis, None)
    model = FakeBuilder(reply=REPLY)
    await run(fake_redis, model)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = (await db_session.scalars(sa.select(BusinessSuggestion))).all()
        profile = await db_session.get(BusinessProfile, biz.tenant_id, populate_existing=True)
        faqs = (await db_session.scalars(sa.select(BusinessFaq))).all()
        agents = await db_session.scalar(sa.select(sa.func.count()).select_from(Agent))
    builder_rows = [r for r in rows if r.source == "builder"]
    assert {r.pointer for r in builder_rows} == {"/policies/cancellation", "/faqs/-"}
    # 60.7: nada entra en el prompt sin aceptarse.
    assert not (profile.policies or {}).get("cancellation") and faqs == []
    assert agents == 0, "60.6: los agentes no se crean solos"

    listed = await suggested(client, biz)
    assert [(a["name"], a["role"]) for a in listed] == [
        ("Recepción", "reception"),
        ("Ventas", "sales"),
        ("Raro", None),
    ]
    assert all(set(a) == {"id", "name", "description", "role"} for a in listed)

    # El constructor mide en «Construcción y pruebas».
    (job,) = [j for j in await jobs_of(db_session, biz.tenant_id, "client_builder")]
    entries = [e[1] for e in await fake_redis.xrange("nexus:usage")]
    (fields,) = [e for e in entries if e.get("turn_id") == f"job:{job.id}"]
    assert fields["source"] == "builder"
    assert {e["task"] for e in json.loads(fields["events"])} == {"build"}


async def test_what_is_discarded_does_not_come_back(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    from nexus_api.services.builder.client_profile import launch_client_builder

    await run(fake_redis, None)
    await run(fake_redis, FakeBuilder(reply=REPLY))
    listed = await suggested(client, biz)
    ventas = next(a for a in listed if a["name"] == "Ventas")
    dismissed = await client.post(
        f"/console/clients/{biz.ref}/suggested-agents/{ventas['id']}/dismiss",
        headers=biz.headers(),
    )
    assert dismissed.status_code == 204, dismissed.text
    assert "Ventas" not in [a["name"] for a in await suggested(client, biz)]
    unknown = await client.post(
        f"/console/clients/{biz.ref}/suggested-agents/{uuid.uuid4()}/dismiss",
        headers=biz.headers(),
    )
    assert unknown.status_code == 404
    record = await read(client, biz, "")
    policy = next(s for s in record["suggestions"] if s["pointer"] == "/policies/cancellation")
    dropped = await client.post(
        f"{biz.url}/suggestions/{policy['id']}/decide",
        json={"decision": "discard"},
        headers=biz.headers(),
    )
    assert dropped.status_code == 200

    # Otra ficha (el horario cambió) y otra pasada con lo mismo.
    week = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue")}
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": week}, revision=0)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        assert await launch_client_builder(db_session, reason="sector") is not None
    await drain_after_commit()
    await run(fake_redis, FakeBuilder(reply=REPLY))
    record = await read(client, biz, "")
    assert not [s for s in record["suggestions"] if s["pointer"] == "/policies/cancellation"]
    assert "Ventas" not in [a["name"] for a in await suggested(client, biz)]
    # Lo pendiente igual no se duplica.
    assert len([s for s in record["suggestions"] if s["pointer"] == "/faqs/-"]) == 1


async def test_a_suggested_agent_that_already_exists_is_not_offered(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await run(fake_redis, None)
    await run(fake_redis, FakeBuilder(reply=REPLY))
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(Agent(id=uuid.uuid4(), tenant_id=biz.tenant_id, name="recepción"))
    assert "Recepción" not in [a["name"] for a in await suggested(client, biz)]
