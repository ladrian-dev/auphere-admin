"""Spec 065, T076 (requisitos 13.1 a 13.6): el modelo por defecto de Auphere.

``GET/PUT /admin/platform/agent-respond-default``:

- sin ``confirm``, ``409 confirm_required`` con los afectados: solo los agentes que siguen el
  modelo por defecto (sin elección propia ni ajuste de su versión);
- con ``confirm``, escribe el ajuste, audita con el motivo, invalida esos agentes y les
  devuelve la pasada de pruebas (``tests_pass_returned_at``); el agente con elección propia
  (como Jemma con Terra) no cambia;
- ``422 unknown_model`` con un modelo que no está habilitado para responder;
- volver a Sol lo deshace;
- no avisa a los partners (13.6): ninguna notificación de consola.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AuditLog
from nexus_api.services.business.writes import drain_after_commit
from tests.integration.models.test_agent_model_admin import _operator
from tests.integration.models.test_agent_model_console import (  # noqa: F401
    _catalog,
    agent_of,
    url,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
OPUS = "anthropic/claude-opus-5-5"
URL = "/admin/platform/agent-respond-default"


@pytest_asyncio.fixture(autouse=True)
async def _back_to_sol() -> AsyncIterator[None]:
    yield
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE platform_settings SET value = to_jsonb(CAST(:m AS text)) WHERE key = :k"
            ),
            {"m": SOL, "k": respond_catalog.AGENT_RESPOND_DEFAULT_KEY},
        )
    respond_catalog.reset()


async def _notifications(partner_id: uuid.UUID) -> int:
    async with get_sessionmaker()() as session:
        return int(
            await session.scalar(
                sa.text("SELECT count(*) FROM console_notifications WHERE partner_id = :p"),
                {"p": partner_id},
            )
            or 0
        )


async def _returned_at(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Any:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        return await session.scalar(
            sa.select(Agent.tests_pass_returned_at).where(Agent.id == agent_id)
        )


async def test_get_says_which_model_and_what_can_be_chosen(client, admin_headers) -> None:
    resp = await client.get(URL, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["model_id"], body["display_name"]) == (SOL, "Sol")
    options = {o["model_id"] for o in body["options"]}
    assert {SOL, TERRA, LUNA} <= options
    assert OPUS not in options, "solo los habilitados para responder"


async def test_changing_it_asks_first_then_moves_only_those_who_follow_it(
    client, console_world, admin_headers, db_session, fake_redis, monkeypatch
) -> None:
    a = console_world["a"]
    headers = await _operator(db_session, admin_headers)
    follows = await agent_of(a["tenant_id"], "Recepción")
    own = await agent_of(a["tenant_id"], "Ventas")
    chosen = await client.put(url(a["ref"], own), headers=a["headers"](), json={"model_id": TERRA})
    assert chosen.status_code == 200, chosen.text
    notifications_before = await _notifications(a["partner_id"])

    unconfirmed = await client.put(
        URL, headers=headers, json={"model_id": LUNA, "reason": "Más barato"}
    )
    assert unconfirmed.status_code == 409, unconfirmed.text
    detail = unconfirmed.json()["detail"]
    assert detail["code"] == "confirm_required"
    affected = {row["agent_id"]: row for row in detail["affected"]}
    assert str(follows) in affected and str(own) not in affected
    row = affected[str(follows)]
    assert row["tenant_id"] == str(a["tenant_id"])
    assert row["external_client_ref"] == a["ref"]
    assert row["agent_name"] == "Recepción"
    assert row["current_model"] == SOL
    assert respond_catalog.agent_respond_default() == SOL, "sin confirmar no cambia nada"

    published: list[str] = []
    real = fake_redis.publish

    async def spy(channel: str, message: str) -> Any:
        published.append(message)
        return await real(channel, message)

    monkeypatch.setattr(fake_redis, "publish", spy)
    done = await client.put(
        URL, headers=headers, json={"model_id": LUNA, "reason": "Más barato", "confirm": True}
    )
    assert done.status_code == 200, done.text
    await drain_after_commit()
    assert done.json()["model_id"] == LUNA
    assert respond_catalog.agent_respond_default() == LUNA
    assert f"{a['tenant_id']}:{follows}" in published
    assert f"{a['tenant_id']}:{own}" not in published
    assert await _returned_at(a["tenant_id"], follows) is not None, "se le devuelve la pasada"
    assert await _returned_at(a["tenant_id"], own) is None

    async with get_sessionmaker()() as session:
        audit = (
            await session.execute(
                sa.select(AuditLog)
                .where(AuditLog.action == "admin.platform.agent_respond_default")
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
    assert audit.tenant_id is None
    assert audit.before_json["model_id"] == SOL
    assert audit.after_json == {**audit.after_json, "model_id": LUNA, "reason": "Más barato"}
    assert audit.after_json["agents"] >= 1

    view = (await client.get(url(a["ref"], follows), headers=a["headers"]())).json()
    assert view["effective"]["model_id"] == LUNA
    assert (await client.get(url(a["ref"], own), headers=a["headers"]())).json()["effective"][
        "model_id"
    ] == TERRA
    assert await _notifications(a["partner_id"]) == notifications_before, "no se avisa (13.6)"

    back = await client.put(
        URL, headers=headers, json={"model_id": SOL, "reason": "Deshacer", "confirm": True}
    )
    assert back.status_code == 200, back.text
    assert respond_catalog.agent_respond_default() == SOL


async def test_a_model_not_enabled_to_respond_is_refused(client, admin_headers, db_session) -> None:
    headers = await _operator(db_session, admin_headers)
    resp = await client.put(
        URL, headers=headers, json={"model_id": OPUS, "reason": "probar", "confirm": True}
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "unknown_model"
    assert respond_catalog.agent_respond_default() == SOL


async def test_the_reason_is_required(client, admin_headers, db_session) -> None:
    headers = await _operator(db_session, admin_headers)
    resp = await client.put(URL, headers=headers, json={"model_id": LUNA, "confirm": True})
    assert resp.status_code == 422, resp.text
