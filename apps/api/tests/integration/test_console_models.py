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


# ── spec 016 · el modelo se elige sabiendo lo que cuesta (R5.1, R5.2) ──────────


async def test_list_models_explains_the_cost_in_credits(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.get("/console/models", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [row["model_id"] for row in body] == list(RESPOND_MODEL_IDS)
    for row in body:
        assert set(row) >= {"model_id", "display_name", "relative_cost", "weights"}
        assert isinstance(row["relative_cost"], int) and row["relative_cost"] >= 1
        assert set(row["weights"]) == {"input", "cache_read", "output"}
        assert row["display_name"]
    # El más económico es x1; el resto, su salida relativa a ese, redondeada.
    assert min(row["relative_cost"] for row in body) == 1
    cheapest = min(body, key=lambda r: r["weights"]["output"])
    for row in body:
        assert row["relative_cost"] == max(
            1, round(row["weights"]["output"] / cheapest["weights"]["output"])
        )


async def test_relative_costs_are_rounded_to_the_cheapest() -> None:
    from nexus_api.api.console.models import relative_costs
    from nexus_api.api.console.schemas_models import ModelWeightsOut

    w = lambda out: ModelWeightsOut(input=1, cache_read=0.1, output=out)  # noqa: E731
    assert relative_costs({"a": w(5), "b": w(20), "c": w(11)}) == {"a": 1, "b": 4, "c": 2}
    assert relative_costs({"a": w(0), "b": w(3)}) == {"a": 1, "b": 1}
    assert relative_costs({}) == {}


async def test_client_model_says_allowed_and_the_change_is_audited(
    client, console_world, db_session, admin_headers
) -> None:
    from nexus_api.db.models import AuditLog

    a = console_world["a"]
    unbound = (
        await client.get(f"/console/clients/{a['ref']}/model", headers=a["headers"]())
    ).json()
    assert unbound["is_bound"] is False
    assert unbound["allowed"] is True
    assert unbound["fallback_model_id"] == SOL
    assert unbound["fallback_display_name"] == "Sol"

    first = await client.put(
        f"/console/clients/{a['ref']}/model", headers=a["headers"](), json={"model_id": SOL}
    )
    assert first.status_code == 200, first.text
    assert first.json()["allowed"] is True
    second = await client.put(
        f"/console/clients/{a['ref']}/model", headers=a["headers"](), json={"model_id": TERRA}
    )
    assert second.status_code == 200, second.text

    rows = (
        await db_session.execute(
            sa.select(AuditLog.after_json, AuditLog.actor, AuditLog.target)
            .where(AuditLog.action == "console.model.update", AuditLog.tenant_id == a["tenant_id"])
            .order_by(AuditLog.created_at)
        )
    ).all()
    assert [r.after_json for r in rows] == [
        {"model_id": SOL, "previous": None},
        {"model_id": TERRA, "previous": SOL},
    ]
    assert all(r.actor.startswith("console:") for r in rows)
    assert all(r.target == f"tenant:{a['tenant_id']}" for r in rows)

    # R5.3 desde el lado del cliente: un binding que el plan ya no incluye
    # (escrito por fuera de la reconciliación) se lee como ``allowed=False``.
    shrink = await client.put(
        f"/admin/partners/{a['partner_id']}/models",
        headers=admin_headers,
        json={"model_ids": [SOL, LUNA]},
    )
    assert shrink.status_code == 200, shrink.text
    await db_session.execute(
        sa.text(
            """
            INSERT INTO tenant_model_bindings (tenant_id, role, model_profile_id, fallback_chain)
            SELECT :t, :r, id, '[]'::jsonb FROM model_profiles WHERE model_id = :m
            ON CONFLICT (tenant_id, role) DO UPDATE SET model_profile_id = EXCLUDED.model_profile_id
            """
        ),
        {"t": str(a["tenant_id"]), "r": RESPOND_ROLE, "m": TERRA},
    )
    await db_session.commit()
    stale = (await client.get(f"/console/clients/{a['ref']}/model", headers=a["headers"]())).json()
    assert stale["model_id"] == TERRA
    assert stale["allowed"] is False
    assert stale["fallback_display_name"] == "Sol"
