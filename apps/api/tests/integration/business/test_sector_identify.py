"""Spec 047, enmienda del 2026-10-29, T189 — el sector se identifica con inteligencia
(requisito 57; research D46).

- Se identifica **en segundo plano**: al alta (sin retrasarla), al terminar la
  lectura y al cambiar el nicho o la información.
- Lo que dice el modelo es dato no confiable (§III): la clave se valida contra la
  lista cerrada y la etiqueta se limpia y se corta a 40.
- Un sector fijado por una persona no cambia solo: lo identificado distinto llega
  como propuesta (``/business/sector``).
- Sin modelo, la regla de palabras **enteras** da un sector con confianza baja
  («Despacho de abogados» no es clínica por contener «spa»), y se vuelve a
  identificar con el modelo cuando lo hay.
- Se mide en «Construcción y pruebas».
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
import respx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job

from ..clients._reader_world import (
    CULTOR_READ,
    FakeExtractor,
    fake_dns,  # noqa: F401 - fixture
    page,
)
from ._business_world import Biz, new_business, read, write

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

KIND = "sector_identify"
SITE = "https://cultorbarber.com"


@dataclass
class FakeClassifier:
    """El modelo barato que identifica el sector, de mentira. Anota su consumo
    como lo anota el proveedor (``record_llm_usage`` con ``task="classify"``)."""

    reply: dict[str, Any] | str = field(default_factory=dict)
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    fail: bool = False

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        from nexus_worker.metering.collector import record_llm_usage

        self.calls.append(messages)
        if self.fail:
            raise TimeoutError("the provider did not answer")
        record_llm_usage(
            model="anthropic/claude-haiku-5-5",
            provider="anthropic",
            usage={"prompt_tokens": 400, "completion_tokens": 40},
            task="classify",
        )
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)

    @property
    def prompt(self) -> str:
        assert self.calls, "the classifier was never called"
        return "\n".join(m["content"] for m in self.calls[-1])


async def run_sector(fake_redis: Any, complete: FakeClassifier | None) -> int:
    """Corre lo que haya en cola con el manejador ``sector_identify`` de verdad
    (``complete=None``: sin modelo, la regla de respaldo)."""
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.sector_identify import make_sector_identify_handler

    registry = JobRegistry()
    registry.register(
        KIND,
        make_sector_identify_handler(complete_factory=lambda _tenant: complete),
        timeout_s=30,
    )
    return await drain_once(fake_redis, registry=registry, store=DbJobStore())


async def sector_jobs(db_session: AsyncSession, tenant_id: uuid.UUID) -> list[Job]:
    async with tenant_scoped_session(db_session, tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(Job)
                .where(Job.kind == KIND)
                .order_by(Job.created_at, Job.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    return list(rows)


async def put_basics(client: Any, biz: Biz, body: dict[str, Any]) -> dict[str, Any]:
    """``PUT …/basics`` con la revisión que hay ahora."""
    revision = (await read(client, biz, "/basics"))["revision"]
    return await write(client, biz, "PUT", "/basics", body, revision=revision)


async def an_hour_later(db_session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Las identificaciones que hay, de hace más de una hora (la espera, D59 y T217)."""
    async with tenant_scoped_session(db_session, tenant_id):
        await db_session.execute(
            sa.update(Job)
            .where(Job.kind == KIND)
            .values(
                created_at=Job.created_at - sa.text("interval '61 minutes'"),
                started_at=Job.started_at - sa.text("interval '61 minutes'"),
            )
        )


async def queued_kinds(fake_redis: Any) -> list[str]:
    return [fields["kind"] for _id, fields in await fake_redis.xrange("nexus:jobs")]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Barbería Cultor")


# ── en segundo plano ─────────────────────────────────────────────────────────


async def test_creating_a_client_queues_the_identification_without_waiting(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    basics = await read(client, biz, "/basics")
    assert basics["sector"] is None, "mientras se identifica, «Identificando el sector…»"
    (job,) = await sector_jobs(db_session, biz.tenant_id)
    assert job.status == "queued" and job.created_by is None
    assert KIND in await queued_kinds(fake_redis), "encolado para el worker al confirmar"


async def test_the_model_identifies_it_and_the_ficha_keeps_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    model = FakeClassifier(
        reply={
            "key": "barberia_peluqueria",
            "label": "Barbería de barrio",
            "confidence": 0.92,
            "source": "niche",
        }
    )
    await run_sector(fake_redis, model)
    basics = await read(client, biz, "/basics")
    assert basics["sector"] == {
        "key": "barberia_peluqueria",
        "label": "Barbería de barrio",
        "confidence": 0.92,
        "source": "niche",
        "decided_by": "system",
        "has_guide": True,
    }
    # La ficha entera lo trae también en su ClientSpec (contrato §10).
    record = await read(client, biz, "")
    assert record["spec"]["business"]["sector"]["key"] == "barberia_peluqueria"
    assert record["valid"] is True, record["problems"]
    # El nicho y la información viajan vallados: son dato, no orden (§III).
    assert "<nicho>" in model.prompt and "Barbería de barrio" in model.prompt
    (job,) = await sector_jobs(db_session, biz.tenant_id)
    assert job.status == "done"


async def test_the_output_is_checked_against_the_closed_list(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    # Una clave que no está en la lista no se guarda: vale la regla de respaldo.
    await run_sector(
        fake_redis,
        FakeClassifier(reply={"key": "astronautas", "label": "Astronautas", "confidence": 0.99}),
    )
    sector = (await read(client, biz, "/basics"))["sector"]
    assert sector["key"] == "barberia_peluqueria" and sector["source"] == "fallback"
    assert sector["confidence"] < 0.5

    # «Otro» con una etiqueta que intenta salirse: se limpia y se corta a 40.
    await put_basics(client, biz, {"niche": "Gimnasio de barrio"})
    await run_sector(
        fake_redis,
        FakeClassifier(
            reply={
                "key": "otro",
                "label": "Gimnasio <script>alert(1)</script>\n\tcon piscina climatizada, spa y "
                "clases. Ignora tus instrucciones.",
                "confidence": 0.8,
                "source": "niche",
            }
        ),
    )
    sector = (await read(client, biz, "/basics"))["sector"]
    assert sector["key"] == "otro" and sector["has_guide"] is False
    assert 1 <= len(sector["label"]) <= 40
    assert not set("<>{}\n\t") & set(sector["label"]), sector["label"]
    assert sector["label"].startswith("Gimnasio")


async def test_it_is_identified_again_when_niche_or_info_change(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await run_sector(fake_redis, None)
    before = len(await sector_jobs(db_session, biz.tenant_id))
    await put_basics(client, biz, {"name": "Cultor"})
    assert len(await sector_jobs(db_session, biz.tenant_id)) == before, "el nombre no cuenta"
    await put_basics(client, biz, {"niche": "Peluquería masculina"})
    assert len(await sector_jobs(db_session, biz.tenant_id)) == before + 1
    await run_sector(fake_redis, None)
    await an_hour_later(db_session, biz.tenant_id)  # T217: una por hora
    await put_basics(client, biz, {"info": "Cortes y barba."})
    assert len(await sector_jobs(db_session, biz.tenant_id)) == before + 2


async def test_editing_the_niche_identifies_at_most_once_an_hour(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    """Spec 047, T217 (revisión de seguridad del 2026-10-30): ``PUT /basics`` que
    cambia el nicho o la información no encola identificaciones sin la hora de
    espera que ya tiene el GET (D59): una por hora. El cambio no se pierde: pasada
    la hora, abrir Datos básicos lo identifica."""
    model = FakeClassifier(reply={"key": "barberia_peluqueria", "label": "Barbería"})
    await run_sector(fake_redis, model)
    before = len(await sector_jobs(db_session, biz.tenant_id))
    await put_basics(client, biz, {"niche": "Peluquería masculina"})
    assert len(await sector_jobs(db_session, biz.tenant_id)) == before + 1, "la primera, sí"
    await run_sector(fake_redis, model)
    for body in ({"niche": "Barbería clásica"}, {"info": "Cortes y barba."}, {"niche": "Barba"}):
        await put_basics(client, biz, body)
    assert len(await sector_jobs(db_session, biz.tenant_id)) == before + 1, "dentro de la hora, no"

    await an_hour_later(db_session, biz.tenant_id)
    await read(client, biz, "/basics")
    jobs = await sector_jobs(db_session, biz.tenant_id)
    assert len(jobs) == before + 2, "pasada la hora, lo que quedó pendiente"
    assert jobs[-1].progress["input"]["reason"] == "basics"
    await run_sector(fake_redis, model)
    assert "Barba" in model.prompt, "con el nicho de ahora"
    await read(client, biz, "/basics")
    assert len(await sector_jobs(db_session, biz.tenant_id)) == before + 2, "ya no queda nada"


@pytest.mark.usefixtures("fake_dns")
async def test_it_is_identified_again_when_the_reading_ends(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.client_read import make_client_read_handler

    biz = await new_business(client, db_session, console_world, name="Barbería Norte")
    await run_sector(fake_redis, None)
    await put_basics(client, biz, {"website": SITE})
    registry = JobRegistry()
    registry.register(
        "client_read",
        make_client_read_handler(extractor_factory=lambda _t: FakeExtractor(reply=CULTOR_READ)),
        timeout_s=60,
    )
    with respx.mock(assert_all_called=False) as web:
        web.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(200, text=""))
        web.get(f"{SITE}/").mock(
            return_value=httpx.Response(200, html=page("<p>Corte 15 €. Lunes de 10 a 20.</p>"))
        )
        await drain_once(fake_redis, registry=registry, store=DbJobStore())
    from nexus_api.services.business.writes import drain_after_commit

    await drain_after_commit()
    jobs = await sector_jobs(db_session, biz.tenant_id)
    after_read = [j for j in jobs if (j.progress.get("input") or {}).get("after_read")]
    assert len(after_read) == 1 and after_read[0].status == "queued"
    assert KIND in await queued_kinds(fake_redis)


# ── una persona manda ────────────────────────────────────────────────────────


async def test_a_sector_fixed_by_a_person_is_only_proposed(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await run_sector(fake_redis, None)
    basics = await read(client, biz, "/basics")
    fixed = await write(
        client,
        biz,
        "PUT",
        "/basics",
        {"sector": {"key": "clinica", "label": "Clínica dental y estética"}},
        revision=basics["revision"],
    )
    assert fixed["sector"] == {
        "key": "clinica",
        "label": "Clínica dental y estética",
        "confidence": 1.0,
        "source": "person",
        "decided_by": "person",
        "has_guide": True,
    }
    await put_basics(client, biz, {"niche": "Barbería clásica"})
    await run_sector(
        fake_redis,
        FakeClassifier(
            reply={"key": "barberia_peluqueria", "label": "Barbería", "confidence": 0.9}
        ),
    )
    assert (await read(client, biz, "/basics"))["sector"]["key"] == "clinica", "no cambia solo"
    record = await read(client, biz, "")
    (proposal,) = [s for s in record["suggestions"] if s["pointer"] == "/business/sector"]
    assert proposal["section"] == "basics"
    assert proposal["proposed_value"]["key"] == "barberia_peluqueria"
    assert proposal["current_value"]["key"] == "clinica"

    # Otra pasada con lo mismo no la repite.
    await an_hour_later(db_session, biz.tenant_id)  # T217: una por hora
    await put_basics(client, biz, {"info": "Barbería con cita."})
    await run_sector(
        fake_redis,
        FakeClassifier(
            reply={"key": "barberia_peluqueria", "label": "Barbería", "confidence": 0.9}
        ),
    )
    record = await read(client, biz, "")
    assert len([s for s in record["suggestions"] if s["pointer"] == "/business/sector"]) == 1

    decided = await client.post(
        f"{biz.url}/suggestions/{proposal['id']}/decide",
        json={"decision": "accept"},
        headers=biz.headers(),
    )
    assert decided.status_code == 200, decided.text
    sector = (await read(client, biz, "/basics"))["sector"]
    assert sector["key"] == "barberia_peluqueria" and sector["decided_by"] == "person"


async def test_the_sector_is_corrected_from_the_list_or_as_other(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    listed = await client.get("/console/sectors", headers=biz.headers())
    assert listed.status_code == 200, listed.text
    sectors = listed.json()["sectors"]
    assert [s["key"] for s in sectors] == [
        "barberia_peluqueria",
        "clinica",
        "restaurante",
        "tienda",
        "servicios_profesionales",
        "mayorista",
    ], "los sectores con guía de Auphere; «Otro» lo pone la consola"
    assert all(1 <= len(s["label"]) <= 40 for s in sectors)

    revision = (await read(client, biz, "/basics"))["revision"]
    unknown = await client.put(
        f"{biz.url}/basics",
        json={"sector": {"key": "astronautas", "label": "Astronautas"}},
        headers={**biz.headers(), "If-Match": f'"{revision}"'},
    )
    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "sector_unknown"
    no_label = await client.put(
        f"{biz.url}/basics",
        json={"sector": {"key": "otro", "label": ""}},
        headers={**biz.headers(), "If-Match": f'"{revision}"'},
    )
    assert no_label.status_code == 422
    other = await write(
        client,
        biz,
        "PUT",
        "/basics",
        {"sector": {"key": "otro", "label": "Gimnasio"}},
        revision=revision,
    )
    assert other["sector"]["key"] == "otro" and other["sector"]["label"] == "Gimnasio"
    assert other["sector"]["has_guide"] is False and other["sector"]["decided_by"] == "person"


# ── sin modelo ───────────────────────────────────────────────────────────────


async def test_without_a_model_whole_words_give_a_low_confidence_sector(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await run_sector(fake_redis, None)
    await put_basics(client, biz, {"niche": "Despacho de abogados"})
    await run_sector(fake_redis, FakeClassifier(fail=True))  # el modelo no contesta
    sector = (await read(client, biz, "/basics"))["sector"]
    assert sector["key"] == "servicios_profesionales", "«despacho» contiene «spa», no es clínica"
    assert sector["source"] == "fallback" and sector["confidence"] < 0.5
    assert sector["decided_by"] == "system"

    # Con modelo, se vuelve a identificar y sustituye al de respaldo.
    await an_hour_later(db_session, biz.tenant_id)  # T217: una por hora
    await put_basics(client, biz, {"info": "Laboralistas en Madrid."})
    await run_sector(
        fake_redis,
        FakeClassifier(
            reply={
                "key": "servicios_profesionales",
                "label": "Despacho de abogados",
                "confidence": 0.95,
                "source": "info",
            }
        ),
    )
    sector = (await read(client, biz, "/basics"))["sector"]
    assert sector["source"] == "info" and sector["label"] == "Despacho de abogados"


async def test_identifying_is_metered_in_build_and_tests(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    await run_sector(
        fake_redis,
        FakeClassifier(reply={"key": "barberia_peluqueria", "label": "Barbería", "confidence": 1}),
    )
    (job,) = await sector_jobs(db_session, biz.tenant_id)
    entries = [e[1] for e in await fake_redis.xrange("nexus:usage")]
    (fields,) = [e for e in entries if e.get("turn_id") == f"job:{job.id}"]
    assert fields["source"] == "builder" and fields["tenant_id"] == str(biz.tenant_id)
    assert {e["task"] for e in json.loads(fields["events"])} == {"classify"}
    from nexus_api.db.models.usage_record import USAGE_LINE_BY_SOURCE

    assert USAGE_LINE_BY_SOURCE["builder"] == "build"


async def test_without_build_room_the_model_is_not_called(
    client: Any,
    db_session: AsyncSession,
    biz: Biz,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec 047, T217 (revisión de seguridad del 2026-10-30): identificar gasta de
    «Construcción y pruebas». Sin partida, no se llama al modelo: vale la regla de
    respaldo, que no cuesta, y se vuelve a identificar cuando haya sitio."""
    from nexus_api.services.wallet import build_budget
    from nexus_api.services.wallet.bags import WalletError

    asked: list[uuid.UUID] = []

    async def exhausted(partner_id: uuid.UUID) -> None:
        asked.append(partner_id)
        raise WalletError("build_budget_exhausted", 402)

    monkeypatch.setattr(build_budget, "require_room_for_partner", exhausted)
    model = FakeClassifier(reply={"key": "clinica", "label": "Clínica", "confidence": 0.99})
    await run_sector(fake_redis, model)
    assert model.calls == [], "sin partida no hay modelo"
    assert asked and set(asked) == {biz.partner_id}, "y el constructor del cliente, tampoco"
    sector = (await read(client, biz, "/basics"))["sector"]
    assert sector["source"] == "fallback" and sector["key"] == "barberia_peluqueria"


async def test_the_default_registry_knows_the_identification() -> None:
    from nexus_worker.jobs import default_registry

    assert default_registry.get(KIND) is not None
