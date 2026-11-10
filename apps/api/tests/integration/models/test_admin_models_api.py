"""El panel de operador del catálogo, el router y las certificaciones (spec 047,
T150 · requisitos 40.13, 41.1, 41.2, 41.7 a 41.9, 42.7, 54.1 a 54.3 y 54.9;
``contracts/admin-api.md`` §1 a §3).

Cada escritura lleva la persona de Auphere (``X-Operator-Id``) y su motivo en la
auditoría, y se aplica desde el siguiente turno. Es la única superficie que
enseña costes (54.11). Ninguna prueba llama a un modelo: la vista previa del
router decide sin llamar a nadie.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.runtime import model_resolver

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog
from nexus_api.services import operator_identity
from nexus_api.services.router_catalog import record_anomaly

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

KEY = "c3a-eu/new-model"
BASE = "/admin/models/deployments"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup() -> AsyncIterator[None]:
    yield
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'c3a-%'"))
        await session.execute(
            sa.text("DELETE FROM router_profiles WHERE published_by LIKE 'operator:ops-c3a%'")
        )
    model_resolver.invalidate_catalog()
    respond_catalog.reset()


@pytest_asyncio.fixture
async def ops(db_session, admin_headers) -> dict[str, Any]:
    email = f"ops-c3a-{uuid.uuid4().hex[:8]}@auphere.test"
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session, email=email, password="operator-password-1", display_name="Ops"
        )
    return {"headers": {**admin_headers, "X-Operator-Id": str(op.id)}, "actor": f"operator:{email}"}


def _new(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": KEY,
        "display_name": "Modelo nuevo",
        "model": "new-model",
        "family": "acme",
        "provider": "acme_eu",
        "route": "eu.acme.new-model",
        "region": "eu-west-3",
        "residency": "eu",
        "retention": {"zero": False, "how": None},
        "license": None,
        "contract": {"dpa": False, "subprocessor_listed": False},
        "quota": {"tpm": None, "rpm": None},
        "capabilities": {"tools": True, "strict_structured_outputs": True, "tier": "basic"},
        "meter_weights": {"w_in": None, "w_cache": None, "w_out": None},
        "reason": "Alta para certificar",
    }
    body.update(over)
    return body


async def _audit(action: str) -> list[AuditLog]:
    async with get_sessionmaker()() as session:
        rows = await session.scalars(
            sa.select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at)
        )
        return list(rows.all())


async def _created(client, ops) -> dict[str, Any]:
    r = await client.post(BASE, headers=ops["headers"], json=_new())
    assert r.status_code == 201, r.text
    return r.json()


# ── el catálogo (41.1, 41.2, 54.1) ─────────────────────────────────────────


async def test_a_new_deployment_is_a_draft_and_says_what_it_lacks(client, ops) -> None:
    created = await _created(client, ops)
    assert created["deployment"]["id"] == KEY
    assert created["deployment"]["status"] == "draft"
    assert set(created["activation_missing"]) == {
        "no_zero_retention",
        "subprocessor_not_listed",
        "unweighted",
        "no_class_certification",
    }
    [audit] = await _audit("deployment.created")
    assert audit.actor == ops["actor"] and audit.tenant_id is None
    assert audit.after_json["reason"] == "Alta para certificar"

    listed = await client.get(f"{BASE}?status=draft", headers=ops["headers"])
    assert listed.status_code == 200
    [row] = [d for d in listed.json()["items"] if d["deployment"]["id"] == KEY]
    assert row["uuid"] == created["uuid"]
    assert row["activation_messages"]["unweighted"].startswith("Faltan los pesos")


async def test_a_license_that_forbids_the_service_is_rejected_and_the_reason_written(
    client, ops
) -> None:
    body = _new(license={"id": "llama-4-community", "url": "https://x", "read_at": None})
    r = await client.post(BASE, headers=ops["headers"], json=body)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "license_excluded"
    [audit] = await _audit("deployment.rejected")
    assert audit.after_json["code"] == "license_excluded"
    assert audit.after_json["id"] == KEY


async def test_activation_goes_through_the_gate(client, ops) -> None:
    created = await _created(client, ops)
    url = f"{BASE}/{created['uuid']}"
    refused = await client.post(f"{url}/activate", headers=ops["headers"], json={"reason": "x"})
    assert refused.status_code == 422
    assert "no_zero_retention" in refused.json()["detail"]["missing"]
    assert refused.json()["detail"]["messages"]

    patched = await client.patch(
        url,
        headers=ops["headers"],
        json={
            "retention": {"zero": True, "how": "store=false"},
            "contract": {"dpa": True, "subprocessor_listed": True},
            "meter_weights": {"w_in": 0.2, "w_cache": 0.02, "w_out": 1.0},
            "reason": "DPA firmado",
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["activation_missing"] == ["no_class_certification"]
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed) "
                "VALUES (:d, 'classify', 1, '{}'::jsonb, 0.95, true)"
            ),
            {"d": created["uuid"]},
        )
    ok = await client.post(
        f"{url}/activate", headers=ops["headers"], json={"reason": "Certificado"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["deployment"]["status"] == "active"
    [audit] = await _audit("deployment.activated")
    assert audit.actor == ops["actor"] and audit.after_json["reason"] == "Certificado"


async def test_changing_capabilities_expires_the_class_certifications(client, ops) -> None:
    created = await _created(client, ops)
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed) "
                "VALUES (:d, 'classify', 1, '{}'::jsonb, 0.95, true)"
            ),
            {"d": created["uuid"]},
        )
    r = await client.patch(
        f"{BASE}/{created['uuid']}",
        headers=ops["headers"],
        json={"capabilities": {"tools": True, "tier": "medium"}, "reason": "Otra cuantización"},
    )
    assert r.status_code == 200, r.text
    async with get_sessionmaker()() as session:
        live = await session.scalar(
            sa.text(
                "SELECT count(*) FROM model_task_certifications "
                "WHERE deployment_id = :d AND invalidated_at IS NULL"
            ),
            {"d": created["uuid"]},
        )
    assert live == 0, "las capacidades caducan la certificación (42.2)"


async def test_prices_retirement_and_unavailable(client, ops) -> None:
    created = await _created(client, ops)
    url = f"{BASE}/{created['uuid']}"
    price = await client.post(
        f"{url}/prices",
        headers=ops["headers"],
        json={
            "valid_from": "2030-01-01",
            "input": 0.11,
            "output": 0.55,
            "cache_read": 0.011,
            "source": "https://example.invalid/precios",
            "currency": "USD",
        },
    )
    assert price.status_code == 201, price.text
    assert price.json()["alerts"] == 0
    listed = (await client.get(BASE, headers=ops["headers"])).json()["items"]
    [row] = [d for d in listed if d["deployment"]["id"] == KEY]
    assert [p["valid_from"] for p in row["deployment"]["prices"]] == ["2030-01-01"]

    no_source = await client.post(
        f"{url}/prices", headers=ops["headers"], json={"valid_from": "2030-02-01", "input": 1}
    )
    assert no_source.status_code == 422, "un precio entra con su fuente"

    retire = await client.post(
        f"{url}/retire",
        headers=ops["headers"],
        json={"retire_after": "2031-01-01T00:00:00+00:00", "reason": "Lo retira el proveedor"},
    )
    assert retire.status_code == 200, retire.text
    assert retire.json()["deployment"]["deployment"]["status"] == "retiring"
    assert retire.json()["proposals"] == []

    gone = await client.post(
        f"{url}/unavailable", headers=ops["headers"], json={"reason": "Rompió el DPA"}
    )
    assert gone.status_code == 200
    assert gone.json()["deployment"]["status"] == "unavailable"
    [audit] = await _audit("deployment.unavailable")
    assert audit.after_json["reason"] == "Rompió el DPA"


async def test_every_write_names_the_operator(client, admin_headers, ops) -> None:
    anonymous = await client.post(BASE, headers=admin_headers, json=_new())
    assert anonymous.status_code == 400
    assert (await client.get(BASE)).status_code == 401
    no_reason = await client.post(BASE, headers=ops["headers"], json=_new(reason=""))
    assert no_reason.status_code == 422


# ── el router (40.13, 54.2, 54.9) ──────────────────────────────────────────


async def test_the_taxonomy_and_the_profiles(client, ops) -> None:
    taxonomy = (await client.get("/admin/router/taxonomy", headers=ops["headers"])).json()
    assert taxonomy["version"] == 1 and len(taxonomy["tasks"]) == 15
    profiles = (await client.get("/admin/router/profiles", headers=ops["headers"])).json()
    assert {p["profile"] for p in profiles["items"]} == {
        "auto",
        "economy",
        "balanced",
        "max",
        "platform",
    }


async def test_a_new_policy_version_with_its_reason_from_the_next_turn(client, ops) -> None:
    profiles = (await client.get("/admin/router/profiles", headers=ops["headers"])).json()
    auto = next(p for p in profiles["items"] if p["profile"] == "auto")
    policy = dict(auto["policy"])
    policy["tasks"] = {
        **policy["tasks"],
        "classify": {**policy["tasks"]["classify"], "min_quality": 0.93},
    }

    no_reason = await client.put(
        "/admin/router/profiles/auto", headers=ops["headers"], json={"policy": policy, "reason": ""}
    )
    assert no_reason.status_code == 422
    over = await client.put(
        "/admin/router/profiles/auto",
        headers=ops["headers"],
        json={"policy": {**policy, "max_calls_per_turn": 20}, "reason": "más llamadas"},
    )
    assert over.status_code == 422, "un perfil baja los techos de 40.10, nunca los sube"
    assert over.json()["detail"]["code"] == "over_ceiling"

    model_resolver.invalidate_catalog()
    before = await model_resolver.get_catalog_snapshot(force=True)
    saved = await client.put(
        "/admin/router/profiles/auto",
        headers=ops["headers"],
        json={"policy": policy, "reason": "El clasificador se equivoca con los audios"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == auto["version"] + 1
    after = await model_resolver.get_catalog_snapshot()
    assert after is not before, "el siguiente turno lee la versión nueva"
    assert after.profiles["auto"].version == auto["version"] + 1
    assert after.profiles["auto"].task("classify").min_quality == 0.93
    [audit] = await _audit("router.policy_changed")
    assert audit.actor == ops["actor"]
    assert audit.after_json["reason"] == "El clasificador se equivoca con los audios"
    assert audit.after_json["version"] == auto["version"] + 1


async def test_the_preview_says_what_it_would_choose_without_calling_a_model(
    client, ops, db_session, seed_tenants
) -> None:
    from ...isolation.conftest import seed_active_agent_config  # type: ignore[import-not-found]

    tenant = seed_tenants["a"]
    cfg = await seed_active_agent_config(db_session, tenant_id=tenant, system_prompt="x", tools=[])
    r = await client.post(
        "/admin/router/preview",
        headers=ops["headers"],
        json={"tenant_id": str(tenant), "agent_id": str(cfg.agent_id), "task": "answer"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task"] == "answer" and body["profile"] == "auto"
    assert body["outcome"] == "no_model", "con el catálogo de hoy nadie pasa (D44)"
    reasons = {x["reason"] for x in body["rejected"]}
    assert "retention" in reasons
    assert body["chain"] == []


async def test_the_anomalies_of_every_client(client, ops, seed_tenants) -> None:
    tenant = seed_tenants["b"]
    decision = uuid.uuid4()
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant):
        await record_anomaly(
            session, tenant_id=tenant, task="answer", kind="no_model", decision_id=decision
        )
    r = await client.get("/admin/router/anomalies", headers=ops["headers"])
    assert r.status_code == 200
    [item] = [x for x in r.json()["items"] if x["decision_id"] == str(decision)]
    assert item["tenant_id"] == str(tenant)
    assert item["tenant_name"] == "Tenant B"
    assert item["kind"] == "no_model" and item["task"] == "answer"


# ── las certificaciones (42.7, 54.3) ───────────────────────────────────────


async def test_the_certifications_by_deployment_and_by_agent(
    client, ops, db_session, seed_tenants
) -> None:
    from ...isolation.conftest import seed_active_agent_config  # type: ignore[import-not-found]

    created = await _created(client, ops)
    tenant = seed_tenants["a"]
    cfg = await seed_active_agent_config(db_session, tenant_id=tenant, system_prompt="x", tools=[])
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed) "
                "VALUES (:d, 'classify', 1, '{\"pass3\": 0.97}'::jsonb, 0.95, true)"
            ),
            {"d": created["uuid"]},
        )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant):
        await session.execute(
            sa.text(
                "INSERT INTO agent_model_certifications (tenant_id, agent_id, deployment_id, "
                "agent_config_id, suite_revision, result, passed, paid_by) VALUES "
                "(:t, :a, :d, :v, 1, '{}'::jsonb, true, 'auphere')"
            ),
            {"t": tenant, "a": cfg.agent_id, "d": created["uuid"], "v": cfg.id},
        )
    r = await client.get(f"/admin/certifications?deployment={KEY}", headers=ops["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    [klass] = body["by_deployment"]
    assert klass["deployment"] == KEY and klass["task"] == "classify"
    assert klass["battery_version"] == 1 and klass["quality"] == 0.95
    assert klass["scores"] == {"pass3": 0.97}
    [agent] = body["by_agent"]
    assert agent["tenant_id"] == str(tenant) and agent["agent_id"] == str(cfg.agent_id)
    assert agent["passed"] is True and agent["paid_by"] == "auphere"

    runs = await client.post(
        "/admin/certifications/runs",
        headers=ops["headers"],
        json={"deployment_id": created["uuid"], "tasks": ["classify"]},
    )
    assert runs.status_code == 409, "la certificación por clase corre fuera de línea"
    assert runs.json()["detail"]["code"] == "class_runner_offline"
    by_agent = await client.post(
        "/admin/certifications/runs",
        headers=ops["headers"],
        json={"deployment_id": created["uuid"], "agent_ids": [str(cfg.agent_id)]},
    )
    # La suite del agente con un despliegue es el trabajo ``quality_check`` de
    # T147, que aún no tiene manejador ni forma de entrada: no se lanza nada que
    # vaya a fallar en cola, y la razón queda dicha.
    assert by_agent.status_code == 409
    assert by_agent.json()["detail"]["code"] == "agent_runner_pending"
    assert await _audit("certification.run") == []
