"""Spec 047, enmienda del 2026-10-29, T191 — guía del sector, papel y ficha
(requisitos 58.1 a 58.4 y 58.6; research D47, D66 y D67).

- El constructor recibe la guía del sector **guardado** (no la del nicho), los
  patrones de papel que encajan con la descripción (ejemplos, no papeles fijos) y la
  ficha vallada.
- Dos clientes del mismo sector con fichas distintas dan entradas distintas, con la
  misma guía.
- Sin guía, se genera una **para ese cliente** con sus 12 pruebas «Generada»; su
  entrada es la etiqueta y la guía genérica, y un barrido comprueba que no lleva nada
  de ningún cliente. El segundo borrador la reutiliza.
- Con una guía convertida por Auphere para esa etiqueta, no se genera nada.
- «Desde una plantilla» crea un AgentSpec estructurado con pruebas del caso y del
  sector, como el constructor.
- ``reservas.*`` solo si Reservas está encendido para el cliente: apagado, cuentan
  como sin activar (D67).
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.db.models.agent_spec import AgentTest, GeneratedGuide, SectorTestCatalog
from nexus_api.db.models.business import BusinessProfile

from ..business._business_world import Biz, new_business, read
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _guide_reply() -> dict[str, Any]:
    return {
        "guide": {
            "ask": ["¿Hay cuota de inscripción?"],
            "procedures": [
                {"title": "Clase de prueba", "when": "Quiere probar", "steps": "Ofrece la clase."}
            ],
            "risks": ["Una lesión en clase"],
            "tools": ["escalate.escalate_to_human", "invented.tool"],
        },
        "tests": [
            {
                "key": f"gym_{n}",
                "name": f"Gimnasio {n}",
                "persona": "Socio",
                "first_message": f"Hola, duda {n}",
                "plan": "Pregunta.",
                "expected_state": {},
                "criteria": [{"key": "ok", "text": "Responde bien."}],
                "critical": n == 1,
            }
            for n in range(1, 13)
        ],
    }


class RoutingBuilder(FakeBuilder):
    """El modelo de la tarea ``build``: la guía cuando se la piden, y el borrador."""

    guide_calls: list[list[dict[str, str]]]

    def __init__(self, reply: dict[str, Any], guide: dict[str, Any] | str | None = None) -> None:
        super().__init__(reply=reply)
        self.guide = guide if guide is not None else _guide_reply()
        self.guide_calls = []

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        from nexus_api.services.builder.guides.generated import SYSTEM

        if messages[0]["content"] == SYSTEM:
            self.guide_calls.append(messages)
            return self.guide if isinstance(self.guide, str) else json.dumps(self.guide)
        return await super().__call__(messages)


async def _set_sector(db_session: AsyncSession, biz: Biz, key: str, label: str) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        profile = await db_session.get(BusinessProfile, biz.tenant_id)
        assert profile is not None
        profile.sector = {
            "key": key,
            "label": label,
            "confidence": 0.9,
            "source": "niche",
            "decided_by": "system",
        }


async def _draft_job(
    client: Any, biz: Biz, fake_redis: Any, builder: FakeBuilder | None, **body: Any
) -> dict[str, Any]:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), **body)
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, builder)
    got = await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    out: dict[str, Any] = got.json()
    assert out["status"] == "done", out
    return out


async def _staged(db_session: AsyncSession, biz: Biz, agent_id: str) -> AgentConfig:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig)
            .where(
                AgentConfig.agent_id == uuid.UUID(agent_id),
                AgentConfig.status == AgentConfigStatus.STAGED,
            )
            .execution_options(populate_existing=True)
        )
    assert cfg is not None
    return cfg


async def _tests(db_session: AsyncSession, biz: Biz, kind: str) -> list[AgentTest]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        return list(
            (
                await db_session.scalars(
                    sa.select(AgentTest)
                    .where(AgentTest.kind == kind, AgentTest.archived_at.is_(None))
                    .execution_options(populate_existing=True)
                )
            ).all()
        )


def _tool_line(prompt: str, name: str) -> str:
    return next(line for line in prompt.splitlines() if line.startswith(f"- {name} ("))


async def _business(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], name: str
) -> Biz:
    return await new_business(client, db_session, console_world, name=name)


async def test_the_builder_gets_the_stored_sectors_guide_the_role_and_the_fenced_profile(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    biz = await _business(client, db_session, console_world, "Barbería Cultor")
    # El nicho dice barbería; el sector guardado, restaurante: manda el guardado.
    await _set_sector(db_session, biz, "restaurante", "Restaurante")
    builder = FakeBuilder(reply=RECEPTION)
    await _draft_job(client, biz, fake_redis, builder)
    prompt = builder.prompt
    assert "Reservar mesa" in prompt, "la guía del sector guardado"
    assert "Llegar sin cita" not in prompt, "no la del nicho"
    assert "Recepción:" in prompt, "el patrón del papel que pide la descripción"
    assert "<ficha" in prompt and "Barbería Cultor" in prompt, "la ficha, vallada"
    system = builder.calls[-1][0]["content"]
    assert "<guia_del_sector>" in system or "guia_del_sector" in system


async def test_two_clients_of_the_same_sector_get_different_inputs(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    a = await _business(client, db_session, console_world, "Barbería Cultor")
    b = await _business(client, db_session, console_world, "Peluquería Norte")
    one, two = FakeBuilder(reply=RECEPTION), FakeBuilder(reply=RECEPTION)
    await _draft_job(client, a, fake_redis, one)
    await _draft_job(client, b, fake_redis, two)
    assert one.prompt != two.prompt
    assert "Barbería Cultor" in one.prompt and "Barbería Cultor" not in two.prompt
    assert "Peluquería Norte" in two.prompt and "Peluquería Norte" not in one.prompt
    for builder in (one, two):
        assert "Llegar sin cita" in builder.prompt, "la misma guía del sector"


async def test_without_a_guide_one_is_generated_for_the_client_from_the_label_alone(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    gym = await _business(client, db_session, console_world, "Gimnasio Titán")
    other = await _business(client, db_session, console_world, "Clínica Vecina")
    await _set_sector(db_session, gym, "otro", "Gimnasio")
    # Datos que no pueden aparecer en la entrada de la generación, ni del cliente
    # ni de otro.
    async with tenant_scoped_session(db_session, gym.tenant_id):
        profile = await db_session.get(BusinessProfile, gym.tenant_id)
        assert profile is not None
        profile.info = "Abrimos 24 horas. Llama al 611 222 333."
    async with tenant_scoped_session(db_session, other.tenant_id):
        profile = await db_session.get(BusinessProfile, other.tenant_id)
        assert profile is not None
        profile.info = "Clínica con aparcamiento en calle Secreta 9."
        profile.website = "https://clinicavecina.es"

    builder = RoutingBuilder(reply=RECEPTION)
    body = await _draft_job(
        client,
        gym,
        fake_redis,
        builder,
        description="Responde dudas de cuotas y horarios del gimnasio.",
    )
    assert len(builder.guide_calls) == 1
    generation = "\n".join(m["content"] for m in builder.guide_calls[0])
    assert "Gimnasio" in generation
    for leaked in (
        "Gimnasio Titán",
        "611 222 333",
        "24 horas",
        "Clínica Vecina",
        "calle Secreta",
        "clinicavecina",
        str(gym.tenant_id),
        str(other.tenant_id),
    ):
        assert leaked not in generation, leaked

    async with tenant_scoped_session(db_session, gym.tenant_id):
        guides = (await db_session.scalars(sa.select(GeneratedGuide))).all()
    assert len(guides) == 1
    guide = guides[0]
    assert guide.status == "generated" and guide.label_key == "gimnasio"
    assert len(guide.tests) == 12 and guide.job_id is not None
    assert "invented.tool" not in guide.guide["tools"]
    assert "Clase de prueba" in builder.prompt, "el borrador recibe la guía generada"

    sector_tests = await _tests(db_session, gym, "sector")
    assert len(sector_tests) == 12
    assert {t.generated_guide_id for t in sector_tests} == {guide.id}
    listed = await client.get(
        f"/console/clients/{gym.ref}/agents/{body['result']['agent_id']}/tests",
        headers=gym.headers(),
    )
    origins = {t["origin"] for t in listed.json()["tests"] if t["kind"] == "sector"}
    assert origins == {"generated"}
    assert {t["origin"] for t in listed.json()["tests"] if t["kind"] == "case"} == {"case"}

    # La guía es del cliente: otro cliente no la ve.
    async with tenant_scoped_session(db_session, other.tenant_id):
        assert not (await db_session.scalars(sa.select(GeneratedGuide))).all()

    again = RoutingBuilder(reply=RECEPTION)
    await _draft_job(client, gym, fake_redis, again, name="Segundo")
    assert again.guide_calls == [], "la guía del cliente se reutiliza"


async def test_a_guide_that_does_not_validate_is_retried_once_then_the_generic_one(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    optica = await _business(client, db_session, console_world, "Óptica Luz")
    await _set_sector(db_session, optica, "otro", "Óptica")
    builder = RoutingBuilder(reply=RECEPTION, guide='{"guide": {"ask": []}, "tests": []}')
    await _draft_job(
        client, optica, fake_redis, builder, description="Responde las dudas de la óptica."
    )
    assert len(builder.guide_calls) == 2
    assert "no valía" in builder.guide_calls[1][1]["content"]
    async with tenant_scoped_session(db_session, optica.tenant_id):
        (guide,) = (await db_session.scalars(sa.select(GeneratedGuide))).all()
    assert len(guide.tests) == 12 and guide.status == "generated"


async def test_a_converted_guide_is_used_instead_of_generating(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    gym = await _business(client, db_session, console_world, "Gimnasio Titán")
    await _set_sector(db_session, gym, "otro", "Gimnásio")
    tests = _guide_reply()["tests"]
    async with db_session.begin():
        await db_session.execute(
            sa.text(
                "INSERT INTO sector_guides (key, label, label_key, guide, published_by) "
                "VALUES ('gimnasio', 'Gimnasio', 'gimnasio', CAST(:g AS jsonb), 'operator:t')"
            ),
            {
                "g": json.dumps(
                    {"ask": ["¿Tenéis piscina?"], "procedures": [], "risks": [], "tools": []}
                )
            },
        )
        db_session.add(
            SectorTestCatalog(sector_key="gimnasio", version=1, tests=tests, published_by="t")
        )
    builder = RoutingBuilder(reply=RECEPTION)
    await _draft_job(client, gym, fake_redis, builder, description="Responde dudas del gimnasio.")
    assert builder.guide_calls == []
    assert "¿Tenéis piscina?" in builder.prompt
    sector_tests = await _tests(db_session, gym, "sector")
    assert len(sector_tests) == 12
    assert all(
        t.sector_test_ref and t.sector_test_ref.startswith("gimnasio@1#") for t in sector_tests
    )
    assert all(t.generated_guide_id is None for t in sector_tests)
    async with tenant_scoped_session(db_session, gym.tenant_id):
        assert not (await db_session.scalars(sa.select(GeneratedGuide))).all()
    # La consola dice «Con guía», no «Generada»: la etiqueta ya tiene guía de Auphere.
    basics = await read(client, gym, "/basics")
    assert basics["sector"]["key"] == "otro" and basics["sector"]["has_guide"] is True


async def test_from_a_template_is_a_structured_agent_with_case_and_sector_tests(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    biz = await _business(client, db_session, console_world, "Barbería Cultor")
    await turn_reservas_on(db_session, biz)
    resp = await start_draft(
        client,
        f"/console/clients/{biz.ref}",
        biz.headers(),
        name="Desde plantilla",
        start="template",
        template_id="barbershop_v1",
    )
    assert resp.status_code == 202, resp.text
    agent_id = resp.json()["agent_id"]
    cfg = await _staged(db_session, biz, agent_id)
    assert cfg.spec is not None and cfg.spec["mode"] == "structured"
    assert cfg.spec["ai_disclosure"] == {"decided": False}
    tools = cfg.spec.get("tools") or []
    assert any(t.startswith("reservas.") for t in tools)
    assert not [t for t in tools if t.startswith("booking.")]
    assert len(await _tests(db_session, biz, "case")) >= 6
    assert len(await _tests(db_session, biz, "sector")) == 12


async def test_the_agenda_only_when_reservas_is_on_for_the_client(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    """D67: con Reservas apagado, ``reservas.*`` cuentan como sin activar: el
    constructor las ve «SIN ACTIVAR», ``sanitize`` las quita y la puerta da
    ``tool_not_connected``. Encendido, son de la casa. Ningún papel las decide."""
    from nexus_api.services.agent_spec.validator import load_context, validate_spec

    biz = await _business(client, db_session, console_world, "Barbería Cultor")
    reply = copy.deepcopy(RECEPTION)
    reply["tools"] = ["reservas.find_slots", "reservas.create", "escalate.escalate_to_human"]

    off_builder = FakeBuilder(reply=reply)
    off = await _draft_job(client, biz, fake_redis, off_builder, name="Citas")
    assert "SIN ACTIVAR" in _tool_line(off_builder.prompt, "reservas.create")
    dropped = {d["tool"]: d["why"] for d in off["result"]["dropped_tools"]}
    assert dropped == {
        "reservas.find_slots": "tool_not_connected",
        "reservas.create": "tool_not_connected",
    }
    cfg = await _staged(db_session, biz, off["result"]["agent_id"])
    assert not [t for t in cfg.spec.get("tools") or [] if t.startswith("reservas.")]
    procedure_tools = [t for p in cfg.spec.get("procedures") or [] for t in p.get("tools") or []]
    assert not [t for t in procedure_tools if t.startswith("reservas.")]
    async with tenant_scoped_session(db_session, biz.tenant_id):
        ctx = await load_context(db_session, partner_id=None)
    doc = {**cfg.spec, "tools": [*(cfg.spec.get("tools") or []), "reservas.create"]}
    _spec, problems = validate_spec(doc, ctx)
    assert {p.code for p in problems if p.pointer.startswith("/tools/")} == {"tool_not_connected"}

    await turn_reservas_on(db_session, biz)
    on_builder = FakeBuilder(reply=reply)
    booking = await _draft_job(client, biz, fake_redis, on_builder, name="Agenda")
    assert "SIN ACTIVAR" not in _tool_line(on_builder.prompt, "reservas.create")
    cfg = await _staged(db_session, biz, booking["result"]["agent_id"])
    assert {"reservas.find_slots", "reservas.create"} <= set(cfg.spec["tools"])
    assert not [d for d in booking["result"]["dropped_tools"] if d["tool"].startswith("reservas.")]
