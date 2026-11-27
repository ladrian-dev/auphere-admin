"""Bug «aceptar una FAQ la deja sugerida» (``.specify/bugs/aceptar-una-faq-la-deja-sugerida``).

Una pregunta frecuente que propone el constructor llega a ``business_suggestions`` con
``{"q", "a", "suggested": true}``. Aceptarla es la decisión de una persona: la pregunta
queda **confirmada**, sale entre las confirmadas, ninguna sugerencia queda pendiente y entra
en el prompt de los agentes activos del cliente (requisitos 18.2 y 18.3).

Las que el fallo ya dejó guardadas como sugeridas siguen en «Por confirmar», y su
«Aceptar» (``PATCH …/faqs/{id}`` con ``suggested: false``) las confirma y las lleva al
prompt.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models.business import BusinessFaq, BusinessSuggestion
from nexus_api.services.business import faqs as faq_service
from nexus_api.services.business.sections import Actor

from ..business._business_world import Biz, active_prompt, new_business, seed_agent, write

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WEEK = {d: [{"open": "10:00", "close": "20:00"}] for d in ("mon", "tue", "wed", "thu", "fri")}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": WEEK}, revision=0)
    return biz


async def _client_builder(client: Any, biz: Biz, fake_redis: Any) -> None:
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.client_builder import make_client_builder_handler

    resp = await client.post(f"{biz.url}/builder", headers=biz.headers())
    assert resp.status_code == 202, resp.text
    registry = JobRegistry()
    registry.register(
        "client_builder",
        make_client_builder_handler(complete_factory=lambda _t: None),
        timeout_s=60,
    )
    await drain_once(fake_redis, registry=registry, store=DbJobStore())


async def _faq_suggestions(db_session: AsyncSession, biz: Biz) -> list[BusinessSuggestion]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = await db_session.scalars(
            sa.select(BusinessSuggestion)
            .where(BusinessSuggestion.pointer == "/faqs/-")
            .order_by(BusinessSuggestion.created_at, BusinessSuggestion.id)
            .execution_options(populate_existing=True)
        )
        return list(rows)


async def _faq_rows(db_session: AsyncSession, biz: Biz) -> list[BusinessFaq]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = await db_session.scalars(
            sa.select(BusinessFaq)
            .where(BusinessFaq.archived_at.is_(None))
            .execution_options(populate_existing=True)
        )
        return list(rows)


async def _decide(client: Any, biz: Biz, suggestion_id: Any, body: dict[str, Any]) -> None:
    resp = await client.post(
        f"{biz.url}/suggestions/{suggestion_id}/decide", json=body, headers=biz.headers()
    )
    assert resp.status_code == 200, resp.text


async def test_accepting_a_faq_of_the_builder_confirms_it_and_it_reaches_the_prompt(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    _agent_id, cfg_id = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres la recepción."
    )
    await _client_builder(client, biz, fake_redis)
    first, second, *_rest = await _faq_suggestions(db_session, biz)
    # La forma que guarda el constructor (y que hay en prod, pendiente de decidir).
    assert first.proposed_value["suggested"] is True

    await _decide(client, biz, first.id, {"decision": "accept"})
    await _decide(
        client,
        biz,
        second.id,
        {"decision": "edit", "value": {"q": second.proposed_value["q"], "a": "Sí, siempre."}},
    )

    rows = {row.q: row for row in await _faq_rows(db_session, biz)}
    assert rows[first.proposed_value["q"]].suggested is False
    assert rows[second.proposed_value["q"]].suggested is False
    listed = (await client.get(f"{biz.url}/faqs", headers=biz.headers())).json()["items"]
    by_q = {item["q"]: item for item in listed}
    assert by_q[first.proposed_value["q"]]["suggested"] is False
    assert by_q[second.proposed_value["q"]]["suggested"] is False
    decided = {s.id: s.decision for s in await _faq_suggestions(db_session, biz)}
    assert decided[first.id] == "accepted" and decided[second.id] == "edited"

    prompt = await active_prompt(db_session, biz.tenant_id, cfg_id)
    assert f"P: {first.proposed_value['q']}" in prompt
    assert f"P: {second.proposed_value['q']}" in prompt


async def test_a_faq_the_bug_left_suggested_is_confirmed_by_accepting_it_again(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Lo que dejó el fallo: una fila ``suggested = true`` que una persona ya aceptó. Su
    tarjeta de «Por confirmar» la confirma con ``PATCH {"suggested": false}``."""
    _agent_id, cfg_id = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres la recepción."
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        faq_id, _written = await faq_service.create_faq(
            db_session,
            q="¿Hay que pedir cita?",
            a="Sí, mejor con cita.",
            suggested=True,
            actor=Actor(kind="partner_member", id="owner-a", origin="console"),
        )
        await db_session.commit()
    assert "¿Hay que pedir cita?" not in await active_prompt(db_session, biz.tenant_id, cfg_id)

    revision = (await client.get(f"{biz.url}/faqs", headers=biz.headers())).json()["revision"]
    out = await write(
        client, biz, "PATCH", f"/faqs/{faq_id}", {"suggested": False}, revision=revision
    )

    assert [item["suggested"] for item in out["items"] if item["id"] == str(faq_id)] == [False]
    assert "P: ¿Hay que pedir cita?" in await active_prompt(db_session, biz.tenant_id, cfg_id)
