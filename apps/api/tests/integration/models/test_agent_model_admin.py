"""Spec 065, T070 (requisitos 7.1, 7.2 y 7.3; y el caso del panel de T010, 10.1): el modelo
de cada agente desde el panel de operador.

- ``GET /admin/tenants/{tenant_id}/agents/models``: cada agente activo con su elección (o
  ninguna) y con qué responde y por qué;
- ``PUT …/agents/{agent_id}/model`` acepta cualquier modelo habilitado para responder en el
  entorno, esté o no en la lista del partner; el motivo es obligatorio; escribe
  ``set_by = 'operator'``, audita ``admin.agent.model.update`` con el motivo e invalida ese
  agente;
- la consola enseña ese modelo en ``choice`` (``outside_offer = "operator"``) sin incluirlo en
  ``options``;
- un agente de otro cliente por la ruta de este es el mismo 404 que uno que no existe, y no
  se escribe nada (garantía 1).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog
from nexus_api.services.business.writes import drain_after_commit
from tests.integration.models.test_agent_model_console import (  # noqa: F401
    _catalog,
    agent_of,
    choice_of,
    url,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
OPUS = "anthropic/claude-opus-5-5"


async def _operator(db_session: Any, admin_headers: dict[str, str]) -> dict[str, str]:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session,
        email=f"op-{uuid.uuid4().hex[:8]}@auphere.test",
        password="operator-password-1",
        role="admin",
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id)}


def _admin_url(tenant_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> str:
    base = f"/admin/tenants/{tenant_id}/agents"
    return f"{base}/models" if agent_id is None else f"{base}/{agent_id}/model"


async def _partner_list(client: Any, admin_headers: dict[str, str], a: dict, models: list[str]):  # type: ignore[no-untyped-def,type-arg]
    resp = await client.put(
        f"/admin/partners/{a['partner_id']}/models",
        headers=admin_headers,
        json={"model_ids": models},
    )
    assert resp.status_code == 200, resp.text


async def test_the_panel_lists_each_agent_with_what_it_answers_with(
    client, console_world, admin_headers
) -> None:
    a = console_world["a"]
    first = await agent_of(a["tenant_id"], "Recepción")
    second = await agent_of(a["tenant_id"], "Ventas")
    await client.put(url(a["ref"], second), headers=a["headers"](), json={"model_id": LUNA})

    resp = await client.get(_admin_url(a["tenant_id"]), headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = {r["agent_id"]: r for r in resp.json()}
    assert rows[str(first)]["choice"] is None
    assert rows[str(first)]["effective"]["model_id"] == SOL
    assert rows[str(first)]["effective"]["source"] == "platform"
    assert rows[str(second)]["name"] == "Ventas"
    assert rows[str(second)]["lifecycle"] == "active"
    assert rows[str(second)]["choice"]["model_id"] == LUNA
    assert rows[str(second)]["choice"]["set_by"] == "partner"
    assert rows[str(second)]["effective"]["display_name"] == "Luna"


async def test_auphere_sets_any_enabled_model_with_a_reason(
    client, console_world, admin_headers, db_session, fake_redis, monkeypatch
) -> None:
    a = console_world["a"]
    headers = await _operator(db_session, admin_headers)
    agent = await agent_of(a["tenant_id"])
    await _partner_list(client, admin_headers, a, [LUNA])
    published: list[str] = []
    real = fake_redis.publish

    async def spy(channel: str, message: str) -> Any:
        published.append(message)
        return await real(channel, message)

    monkeypatch.setattr(fake_redis, "publish", spy)

    no_reason = await client.put(
        _admin_url(a["tenant_id"], agent), headers=headers, json={"model_id": TERRA}
    )
    assert no_reason.status_code == 422, no_reason.text
    blank = await client.put(
        _admin_url(a["tenant_id"], agent), headers=headers, json={"model_id": TERRA, "reason": " "}
    )
    assert blank.status_code == 422, blank.text

    resp = await client.put(
        _admin_url(a["tenant_id"], agent),
        headers=headers,
        json={"model_id": TERRA, "reason": "Jemma pidió más calidad"},
    )
    assert resp.status_code == 200, resp.text
    await drain_after_commit()
    assert resp.json()["choice"]["set_by"] == "operator"
    assert (await choice_of(a["tenant_id"], agent))[:2] == (TERRA, "operator")
    assert f"{a['tenant_id']}:{agent}" in published

    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        audit = (
            await session.execute(
                sa.select(AuditLog).where(AuditLog.action == "admin.agent.model.update")
            )
        ).scalar_one()
    assert audit.actor.startswith("operator:")
    assert audit.target == f"agent:{agent}"
    assert audit.after_json["model_id"] == TERRA
    assert audit.after_json["reason"] == "Jemma pidió más calidad"

    # La consola del partner lo enseña elegido por Auphere, fuera de su lista.
    view = (await client.get(url(a["ref"], agent), headers=a["headers"]())).json()
    assert view["choice"]["model_id"] == TERRA
    assert view["effective"]["outside_offer"] == "operator"
    assert TERRA not in {o["model_id"] for o in view["options"]}


async def test_a_model_not_enabled_to_respond_is_refused(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    headers = await _operator(db_session, admin_headers)
    agent = await agent_of(a["tenant_id"])
    resp = await client.put(
        _admin_url(a["tenant_id"], agent),
        headers=headers,
        json={"model_id": OPUS, "reason": "probar"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "unknown_model"
    assert (await choice_of(a["tenant_id"], agent))[0] is None


async def test_another_clients_agent_is_a_404_and_nothing_is_written(
    client, console_world, admin_headers, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    headers = await _operator(db_session, admin_headers)
    foreign = await agent_of(b["tenant_id"])
    body = {"model_id": TERRA, "reason": "probar"}
    through_a = await client.put(_admin_url(a["tenant_id"], foreign), headers=headers, json=body)
    missing = await client.put(_admin_url(a["tenant_id"], uuid.uuid4()), headers=headers, json=body)
    assert through_a.status_code == missing.status_code == 404
    assert through_a.json() == missing.json()
    assert (await choice_of(b["tenant_id"], foreign))[0] is None


async def test_the_panel_needs_the_admin_token(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.get(_admin_url(a["tenant_id"]))
    assert resp.status_code in {401, 403}


# ── T082 (requisitos 8.2, 8.3 y 10.1): la lista del partner se queda sin un modelo ─────────


async def _set_by_operator(tenant_id: uuid.UUID, agent_id: uuid.UUID, model_id: str) -> None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.text(
                "UPDATE agents SET respond_model_profile_id = "
                "(SELECT id FROM model_profiles WHERE model_id = :m), "
                "respond_model_set_by = 'operator', respond_model_set_at = now() WHERE id = :a"
            ),
            {"m": model_id, "a": agent_id},
        )
        await session.commit()


async def _resets(partner_id: uuid.UUID) -> list[dict[str, Any]]:
    """Los avisos ``agent.model_reset`` de un partner (tabla de partner, sin RLS de cliente)."""
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            sa.text(
                "SELECT payload FROM console_notifications "
                "WHERE partner_id = :p AND kind = 'agent.model_reset' ORDER BY created_at"
            ),
            {"p": partner_id},
        )
        return [dict(r[0]) for r in rows]


async def test_shrinking_the_list_moves_the_partners_choices_to_the_default(
    client, console_world, admin_headers, fake_redis, monkeypatch
) -> None:
    a, b = console_world["a"], console_world["b"]
    await _partner_list(client, admin_headers, a, [SOL, TERRA, LUNA])
    await _partner_list(client, admin_headers, b, [SOL, TERRA, LUNA])
    first = await agent_of(a["tenant_id"], "Recepción")
    second = await agent_of(a["tenant_id"], "Ventas")
    by_auphere = await agent_of(a["tenant_id"], "Soporte")
    keeps = await agent_of(a["tenant_id"], "Reservas")
    other_partner = await agent_of(b["tenant_id"], "Recepción B")
    for agent in (first, second):
        resp = await client.put(
            url(a["ref"], agent), headers=a["headers"](), json={"model_id": LUNA}
        )
        assert resp.status_code == 200, resp.text
    await client.put(url(a["ref"], keeps), headers=a["headers"](), json={"model_id": TERRA})
    await client.put(url(b["ref"], other_partner), headers=b["headers"](), json={"model_id": LUNA})
    await _set_by_operator(a["tenant_id"], by_auphere, LUNA)
    published: list[str] = []
    real = fake_redis.publish

    async def spy(channel: str, message: str) -> Any:
        published.append(message)
        return await real(channel, message)

    monkeypatch.setattr(fake_redis, "publish", spy)

    await _partner_list(client, admin_headers, a, [SOL, TERRA])
    await drain_after_commit()

    assert (await choice_of(a["tenant_id"], first))[:2] == (None, None)
    assert (await choice_of(a["tenant_id"], second))[:2] == (None, None)
    assert (await choice_of(a["tenant_id"], keeps))[:2] == (TERRA, "partner")
    assert (await choice_of(a["tenant_id"], by_auphere))[:2] == (LUNA, "operator"), "8.3"
    assert (await choice_of(b["tenant_id"], other_partner))[:2] == (LUNA, "partner"), "10.1"
    assert {f"{a['tenant_id']}:{first}", f"{a['tenant_id']}:{second}"} <= set(published)
    assert f"{a['tenant_id']}:{keeps}" not in published

    resets = await _resets(a["partner_id"])
    assert sorted(r["agent"] for r in resets) == ["Recepción", "Ventas"], "uno por agente"
    for reset in resets:
        assert reset["external_client_ref"] == a["ref"]
        assert (reset["from_model"], reset["to_model"]) == ("Luna", "Sol")
        assert "tenant_id" not in reset
        assert str(a["tenant_id"]) not in repr(reset)
    assert await _resets(b["partner_id"]) == []

    view = (await client.get(url(a["ref"], first), headers=a["headers"]())).json()
    assert view["choice"] is None and view["effective"]["model_id"] == SOL

    # Reescribir la misma lista no avisa otra vez.
    await _partner_list(client, admin_headers, a, [SOL, TERRA])
    assert len(await _resets(a["partner_id"])) == 2
