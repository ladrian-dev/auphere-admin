"""Spec 063, requisito 4 — «Desde una plantilla» no se cae por un nombre, ni sin él.

En prod (2026-11-18, partner ``auphere-acme``) devolvió 500 tres veces: la guarda de
nombres de otros clientes encontraba en el texto de la plantilla el nombre de otro
cliente del partner, el saneado no sabía quitarlo y ``BuilderUnavailable`` salía sin
capturar. Ahora el texto de la guía no cuenta como ajeno (4.1) y, si algo impide de
verdad el borrador, la API responde ``422 draft_invalid`` (4.4).
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent

from ..business._business_world import Biz, new_business
from ._builder_world import start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _agents(db: AsyncSession, biz: Biz) -> int:
    async with tenant_scoped_session(db, biz.tenant_id):
        return len((await db.scalars(sa.select(Agent.id))).all())


async def test_a_client_named_like_a_word_of_the_template_does_not_break_it(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    # Otro cliente del mismo partner se llama como una palabra de la guía de barbería.
    await new_business(client, db_session, console_world, name="Peluquería")
    biz = await new_business(client, db_session, console_world, name="Salón Rita")
    resp = await start_draft(
        client,
        f"/console/clients/{biz.ref}",
        biz.headers(),
        name="Recepción",
        start="template",
        template_id="barbershop_v1",
    )
    assert resp.status_code == 202, resp.text
    assert await _agents(db_session, biz) == 1


async def test_a_draft_that_cannot_be_made_is_a_named_error(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus_api.services.builder import agent_draft

    def stuck(*args: Any, **kwargs: Any) -> Any:
        raise agent_draft.BuilderUnavailable("invalid_draft")

    monkeypatch.setattr(agent_draft, "sanitize", stuck)
    biz = await new_business(client, db_session, console_world, name="Salón Rita")
    resp = await start_draft(
        client,
        f"/console/clients/{biz.ref}",
        biz.headers(),
        name="Recepción",
        start="template",
        template_id="generic_v1",
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "draft_invalid"
    assert await _agents(db_session, biz) == 0
