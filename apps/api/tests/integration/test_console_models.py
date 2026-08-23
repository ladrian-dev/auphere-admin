"""Consola: catálogo cerrado de modelos y binding respond. B es 404 opaco."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.core.respond_catalog import RESPOND_MODEL_IDS, RESPOND_ROLE

pytestmark = pytest.mark.asyncio

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"


async def test_list_models_is_the_closed_catalog(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.get("/console/models", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [row["model_id"] for row in body]
    assert ids == list(RESPOND_MODEL_IDS)
    for row in body:
        assert "partner_id" not in row
        assert "tenant_id" not in row
        assert "price_input_per_mtok" not in row


async def test_get_and_put_model_isolation_is_opaque_404(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    missing = await client.get("/console/clients/no-such-client/model", headers=a["headers"]())
    other = await client.get("/console/clients/{}/model".format(b["ref"]), headers=a["headers"]())
    own = await client.get("/console/clients/{}/model".format(a["ref"]), headers=a["headers"]())
    assert missing.status_code == 404
    assert other.status_code == 404
    assert missing.json() == other.json() == {"detail": "Unknown client reference"}
    assert own.status_code == 200, own.text
    assert own.json()["is_bound"] is False
    assert "partner_id" not in own.json()

    put_missing = await client.put(
        "/console/clients/no-such-client/model",
        headers=a["headers"](),
        json={"model_id": SOL},
    )
    put_other = await client.put(
        "/console/clients/{}/model".format(b["ref"]),
        headers=a["headers"](),
        json={"model_id": SOL},
    )
    assert put_missing.status_code == 404
    assert put_other.status_code == 404
    assert put_missing.json() == put_other.json() == {"detail": "Unknown client reference"}
    still = await client.get("/console/clients/{}/model".format(b["ref"]), headers=b["headers"]())
    assert still.status_code == 200
    assert still.json()["is_bound"] is False


async def test_put_model_rejects_partner_id_in_body(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.put(
        "/console/clients/{}/model".format(a["ref"]),
        headers=a["headers"](),
        json={"model_id": SOL, "partner_id": str(a["partner_id"])},
    )
    assert resp.status_code == 422, resp.text


async def test_put_model_rejects_loose_gpt56(client, console_world) -> None:
    a = console_world["a"]
    for bad in ("gpt-5.6", "openai/gpt-4o", "openai/whisper-1", "x" * 80):
        resp = await client.put(
            "/console/clients/{}/model".format(a["ref"]),
            headers=a["headers"](),
            json={"model_id": bad},
        )
        assert resp.status_code == 422, (bad, resp.text)


async def test_put_model_upserts_respond_binding(client, console_world, db_session) -> None:
    a = console_world["a"]
    first = await client.put(
        "/console/clients/{}/model".format(a["ref"]),
        headers=a["headers"](),
        json={"model_id": SOL},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["model_id"] == SOL
    assert body["role"] == RESPOND_ROLE
    assert body["is_bound"] is True
    assert "partner_id" not in body

    got = await client.get("/console/clients/{}/model".format(a["ref"]), headers=a["headers"]())
    assert got.status_code == 200
    assert got.json()["model_id"] == SOL

    second = await client.put(
        "/console/clients/{}/model".format(a["ref"]),
        headers=a["headers"](),
        json={"model_id": TERRA},
    )
    assert second.status_code == 200, second.text
    assert second.json()["model_id"] == TERRA

    third = await client.put(
        "/console/clients/{}/model".format(a["ref"]),
        headers=a["headers"](),
        json={"model_id": LUNA},
    )
    assert third.status_code == 200, third.text
    assert third.json()["model_id"] == LUNA

    row = (
        await db_session.execute(
            sa.text(
                """
                SELECT p.model_id, b.role
                  FROM tenant_model_bindings b
                  JOIN model_profiles p ON p.id = b.model_profile_id
                 WHERE b.tenant_id = :t AND b.role = :r
                """
            ),
            {"t": str(a["tenant_id"]), "r": RESPOND_ROLE},
        )
    ).first()
    assert row is not None
    assert row[0] == LUNA
    assert row[1] == RESPOND_ROLE


async def test_put_model_forbidden_without_agents_write(client, console_world, db_session) -> None:
    from tests.conftest import add_console_member

    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    resp = await client.put(
        "/console/clients/{}/model".format(a["ref"]),
        headers=analyst["headers"](),
        json={"model_id": SOL},
    )
    assert resp.status_code == 403, resp.text
    readable = await client.get(
        "/console/clients/{}/model".format(a["ref"]), headers=analyst["headers"]()
    )
    assert readable.status_code == 200, readable.text
