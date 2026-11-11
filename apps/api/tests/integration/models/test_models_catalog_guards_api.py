"""Spec 059 (requisitos 1.1 a 1.8, 3.12 y 4.4; T015, T011 y T025) — el panel de
Modelos con las guardas (``contracts/admin-api.md`` §1 a §5).

- Cada fila dice si el modelo está en uso y por qué (``uses``) y si su retirada está
  detenida (``retirement_blocked_agents``).
- «Retirar» y «No disponible» responden ``409 model_in_use`` o
  ``409 defaults_unverified`` sin cambiar nada, aunque se llame a la API sin panel.
- «Cancelar retirada» y «Volver a disponible».
- Un precio de coste no devuelve avisos y no entra con fecha pasada.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.platform_models import default_models
from nexus_worker.runtime import model_resolver

from nexus_api.core import respond_catalog
from nexus_api.db.base import get_sessionmaker
from nexus_api.services import model_usage, operator_identity

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/admin/models/deployments"
SOL = "openai/gpt-5.6-sol"
FREE = "c59g-a/free"


@pytest_asyncio.fixture(autouse=True)
async def _world(fake_redis) -> AsyncIterator[None]:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO model_profiles (provider, model_id, display_name, route, status, "
                "capabilities, supports_tools, price_input_per_mtok, price_output_per_mtok, "
                "quota_weight_input, quota_weight_cache_read, quota_weight_output) VALUES "
                "('c59g', :k, 'Libre', :k, 'active', CAST(:c AS jsonb), true, 1, 5, 0.22, 0.022, 1.1)"
            ),
            {"k": FREE, "c": json.dumps({"tools": True, "tier": "basic"})},
        )
    model_resolver.invalidate_catalog()
    model_usage.invalidate()
    yield
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'c59g-%'"))
    model_resolver.invalidate_catalog()
    respond_catalog.reset()
    model_usage.invalidate()


@pytest_asyncio.fixture
async def beating(fake_redis) -> None:
    await fake_redis.set(
        "nexus:health:nexus-worker:host-1",
        json.dumps({"v": 1, "models": default_models()}),
        ex=60,
    )


@pytest_asyncio.fixture
async def ops(db_session, admin_headers) -> dict[str, Any]:
    email = f"ops-c59-{uuid.uuid4().hex[:8]}@auphere.test"
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session, email=email, password="operator-password-1", display_name="Ops"
        )
    return {"headers": {**admin_headers, "X-Operator-Id": str(op.id)}, "actor": f"operator:{email}"}


async def _row(client, ops, key: str) -> dict[str, Any]:
    r = await client.get(BASE, headers=ops["headers"])
    assert r.status_code == 200, r.text
    [row] = [d for d in r.json()["items"] if d["deployment"]["id"] == key]
    return row


async def test_each_row_says_whether_it_is_in_use(client, ops, beating) -> None:
    sol = await _row(client, ops, SOL)
    assert {"respond", "respond_fallback"} <= set(sol["uses"]["defaults"])
    assert sol["uses"]["verified"] is True and sol["uses"]["problem"] is None
    assert sol["retirement_blocked_agents"] is None
    free = await _row(client, ops, FREE)
    assert free["uses"] == {
        "defaults": [],
        "agents": 0,
        "clients": [],
        "verified": True,
        "problem": None,
    }


@pytest.mark.parametrize("action", ["unavailable", "retire"])
async def test_the_respond_model_is_refused_with_its_uses(client, ops, beating, action) -> None:
    sol = await _row(client, ops, SOL)
    body: dict[str, Any] = {"reason": "Prueba"}
    if action == "retire":
        body["retire_after"] = (datetime.now(UTC) + timedelta(days=40)).isoformat()
    r = await client.post(f"{BASE}/{sol['uuid']}/{action}", headers=ops["headers"], json=body)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "model_in_use"
    assert "respond" in detail["defaults"]
    assert set(detail) >= {"defaults", "agents", "clients"}
    assert (await _row(client, ops, SOL))["deployment"]["status"] == "active"


async def test_without_a_heartbeat_the_api_refuses(client, ops) -> None:
    free = await _row(client, ops, FREE)
    r = await client.post(
        f"{BASE}/{free['uuid']}/unavailable", headers=ops["headers"], json={"reason": "x"}
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {"code": "defaults_unverified", "problem": "no_heartbeat"}


async def test_unavailable_and_back(client, ops, beating) -> None:
    free = await _row(client, ops, FREE)
    url = f"{BASE}/{free['uuid']}"
    gone = await client.post(f"{url}/unavailable", headers=ops["headers"], json={"reason": "x"})
    assert gone.status_code == 200, gone.text
    back = await client.post(f"{url}/restore", headers=ops["headers"], json={"reason": "ya vale"})
    assert back.status_code == 200, back.text
    assert back.json()["deployment"]["status"] == "active"
    again = await client.post(f"{url}/restore", headers=ops["headers"], json={"reason": "x"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "not_unavailable"


async def test_retire_and_cancel(client, ops, beating) -> None:
    free = await _row(client, ops, FREE)
    url = f"{BASE}/{free['uuid']}"
    when = (datetime.now(UTC) + timedelta(days=40)).isoformat()
    retire = await client.post(
        f"{url}/retire", headers=ops["headers"], json={"retire_after": when, "reason": "x"}
    )
    assert retire.status_code == 200, retire.text
    cancel = await client.post(
        f"{url}/cancel-retirement", headers=ops["headers"], json={"reason": "me equivoqué"}
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["deployment"]["status"] == "active"
    again = await client.post(
        f"{url}/cancel-retirement", headers=ops["headers"], json={"reason": "x"}
    )
    assert again.status_code == 409 and again.json()["detail"]["code"] == "not_retiring"


async def test_the_new_routes_need_the_operator(client, admin_headers, beating) -> None:
    r = await client.get(BASE, headers=admin_headers)
    free = next(d for d in r.json()["items"] if d["deployment"]["id"] == FREE)
    for action in ("restore", "cancel-retirement"):
        anonymous = await client.post(
            f"{BASE}/{free['uuid']}/{action}", headers=admin_headers, json={"reason": "x"}
        )
        assert anonymous.status_code in (400, 401, 403, 422), action


async def test_a_cost_returns_no_alerts_and_refuses_the_past(client, ops, beating) -> None:
    free = await _row(client, ops, FREE)
    url = f"{BASE}/{free['uuid']}/prices"
    today = datetime.now(UTC).date()
    ok = await client.post(
        url,
        headers=ops["headers"],
        json={
            "valid_from": today.isoformat(),
            "input": 1.2,
            "output": 6,
            "source": "https://example.invalid/p",
        },
    )
    assert ok.status_code == 201, ok.text
    assert set(ok.json()) == {"deployment"}, "sin avisos"
    past = await client.post(
        url,
        headers=ops["headers"],
        json={
            "valid_from": (today - timedelta(days=1)).isoformat(),
            "input": 1,
            "source": "https://example.invalid/p",
        },
    )
    assert past.status_code == 422 and past.json()["detail"]["code"] == "in_the_past"
