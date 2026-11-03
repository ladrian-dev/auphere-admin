"""Un partner recién nacido llega al modelo, nazca como nazca.

Staging exigía una clave del proxy por partner que ninguna de las dos vías de alta
creaba, y su IA fallaba hasta que alguien la añadía a mano (INC-38). Desde la
enmienda de ADR-036 staging va directo al proveedor, como producción: esta prueba
recorre ese camino de punta a punta, sin clave ni proxy, por las dos vías. Nacer,
crear un cliente, generar un borrador en el worker y hablar con él en el playground.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import litellm
import pytest
import sqlalchemy as sa
from nexus_worker.config import get_worker_settings
from nexus_worker.jobs import DbJobStore, default_registry, drain_once
from nexus_worker.runtime.pipeline import _EMPTY_RESPONSE_FALLBACK
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import Partner, PartnerMembership
from nexus_api.repositories.signup import SignupRequestRepository
from tests.conftest import add_console_member, console_headers, mint_console_token

from .builder._builder_world import start_draft
from .test_jobs_reach_the_model_behind_the_proxy import Transport

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _born_from_panel(
    client: Any, db_session: AsyncSession, admin_headers: dict[str, str], _: Any
) -> Callable[[], dict[str, str]]:
    resp = await client.post(
        "/admin/partners",
        headers=admin_headers,
        json={"name": "Agencia del Panel", "slug": f"panel-{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 201, resp.text
    partner_id = uuid.UUID(resp.json()["id"])
    # Lo que hace hoy el operador a mano tras crearlo (la spec 052 lo trae de serie).
    partner = await db_session.get(Partner, partner_id)
    assert partner is not None
    partner.console_enabled = True
    await db_session.commit()
    member = await add_console_member(db_session, partner_id=partner_id, role="owner")
    return member["headers"]


async def _born_from_signup(
    client: Any, db_session: AsyncSession, _: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> Callable[[], dict[str, str]]:
    monkeypatch.setattr(get_settings(), "signup_enabled", True, raising=False)
    email = f"alta-{uuid.uuid4().hex[:8]}@example.com"
    _row, token = await SignupRequestRepository(db_session).create(email=email, ttl_hours=24)
    await db_session.commit()
    service = mint_console_token(user_id="bff", partner_id=None, service=True)
    done = await client.post(
        f"/console/signup/{token}/complete",
        json={"company_name": "Agencia Abierta", "password": "una-contrasena-larga"},
        headers={"Authorization": f"Bearer {service}", "X-Forwarded-For": "203.0.113.50"},
    )
    assert done.status_code == 201, done.text
    partner = (
        await db_session.execute(
            sa.select(Partner).where(Partner.slug == done.json()["partner_slug"])
        )
    ).scalar_one()
    membership = (
        await db_session.execute(
            sa.select(PartnerMembership).where(PartnerMembership.partner_id == partner.id)
        )
    ).scalar_one()
    user_id, partner_id = membership.user_id, partner.id
    return lambda: console_headers(user_id=user_id, partner_id=partner_id)


@pytest.mark.parametrize("born", [_born_from_panel, _born_from_signup], ids=["panel", "alta"])
async def test_new_partner_reaches_the_model_without_a_proxy_key(
    client: Any,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
    born: Any,
) -> None:
    headers = await born(client, db_session, admin_headers, monkeypatch)

    created = await client.post(
        "/console/clients",
        json={
            "name": "Barbería Cultor",
            "niche": "Barbería de barrio",
            "country": "ES",
            "timezone": "Europe/Madrid",
            "price_currency": "EUR",
        },
        headers=headers(),
    )
    assert created.status_code == 201, created.text
    ref = created.json()["ref"]

    monkeypatch.setattr(get_worker_settings(), "llm_use_inmemory", False)
    transport = Transport()
    monkeypatch.setattr(litellm, "acompletion", transport)

    draft = await start_draft(client, f"/console/clients/{ref}", headers())
    assert draft.status_code == 202, draft.text
    await drain_once(fake_redis, registry=default_registry, store=DbJobStore())
    job = await client.get(f"/console/jobs/{draft.json()['job_id']}", headers=headers())
    assert job.json()["status"] == "done", job.text
    agent_id = job.json()["result"]["agent_id"]

    playground = f"/console/clients/{ref}/agents/{agent_id}/playground/sessions"
    session = await client.post(playground, json={}, headers=headers())
    assert session.status_code == 201, session.text
    sent = await client.post(
        f"{playground}/{session.json()['session_id']}/messages",
        json={"text": "Hola, ¿tenéis cita el lunes?"},
        headers=headers(),
    )
    assert sent.status_code == 200, sent.text
    bubbles = sent.json()["turn"]["bubbles"]
    assert bubbles
    assert _EMPTY_RESPONSE_FALLBACK not in bubbles

    assert transport.calls, "ninguna llamada salió hacia el modelo"
    assert {(c.get("api_base"), c.get("api_key")) for c in transport.calls} == {(None, None)}
