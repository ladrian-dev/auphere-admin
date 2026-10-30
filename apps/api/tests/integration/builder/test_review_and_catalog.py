"""Spec 047, T088, T090 y T087 — la revisión en la consola, el catálogo de pruebas
del sector y la calibración del juez.

- La revisión de un borrador dice sus hallazgos con gravedad y arreglo, la lista
  de comprobaciones que corrieron, y el arreglo de un clic es una propuesta que
  una persona aplica (22.2). A un analyst se le explica, sin propuestas (19.5).
- El catálogo del sector tiene 12 pruebas por sector y Auphere publica versiones
  nuevas; las suites que ya existen no cambian (21.1, 54.10).
- La calibración del juez guarda su acuerdo con las etiquetas humanas como la
  certificación de la tarea ``judge``; con un 85 % o más, el juez bloquea (21.8).
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.sector_tests import set_calibration_judge
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models.agent_spec import AgentReview
from nexus_api.services import operator_identity
from nexus_api.services.testing.judge import calibration_set, judge_calibrated
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    # La barbería tiene Reservas encendido: sin él, la agenda cuenta como sin activar (D67).
    await turn_reservas_on(db_session, biz)
    return biz


@pytest_asyncio.fixture
async def ops(db_session: AsyncSession, admin_headers: dict[str, str]) -> dict[str, str]:
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-047-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def _agent(client: Any, biz: Biz, fake_redis: Any, reply: dict[str, Any]) -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=reply))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    return uuid.UUID(body["result"]["agent_id"])


async def test_the_review_says_what_blocks_and_fixes_in_one_click(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    reply = copy.deepcopy(RECEPTION)
    reply["instructions"].append(
        {"title": "Más", "body": "Si piden cambiar, usa reservas.mover_cita."}
    )
    agent_id = await _agent(client, biz, fake_redis, reply)
    url = f"/console/clients/{biz.ref}/agents/{agent_id}"
    got = await client.get(f"{url}/review", headers=biz.headers())
    assert got.status_code == 200, got.text
    out = got.json()
    codes = {f["code"]: f["severity"] for f in out["findings"]}
    # Sin horario y con herramientas de reservas: bloquea. El aviso de IA, sin decidir.
    assert codes["no_hours"] == "block"
    assert codes["ai_disclosure_undecided"] == "block"
    assert codes["unknown_tool"] == "block"
    assert out["blocking"] >= 3
    checks = {c["check"]: c["ok"] for c in out["checks"]}
    assert checks["hours"] is False and checks["skills_integrations"] is True
    unknown = next(f for f in out["findings"] if f["code"] == "unknown_tool")
    assert unknown["fix"]["kind"] == "proposal"
    applied = await client.post(
        f"{url}/proposals/{unknown['fix']['proposal_id']}/apply", headers=biz.headers()
    )
    assert applied.status_code == 200, applied.text
    again = (await client.get(f"{url}/review", headers=biz.headers())).json()
    assert "unknown_tool" not in {f["code"] for f in again["findings"]}
    async with tenant_scoped_session(db_session, biz.tenant_id):
        stored = (await db_session.scalars(sa.select(AgentReview))).all()
    assert len(stored) == 2

    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    explained = (await client.get(f"{url}/review", headers=analyst["headers"]())).json()
    assert all((f.get("fix") or {}).get("kind") != "proposal" for f in explained["findings"])


async def test_the_sector_catalog_has_twelve_per_sector_and_new_versions(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any, ops: dict[str, str]
) -> None:
    listed = await client.get("/admin/builder/sector-tests", headers=ops)
    assert listed.status_code == 200, listed.text
    sectors = {s["sector"]: s for s in listed.json()}
    assert set(sectors) == {
        "barberia_peluqueria",
        "clinica",
        "restaurante",
        "tienda",
        "servicios_profesionales",
        "mayorista",
    }
    assert all(s["version"] == 1 and len(s["tests"]) == 12 for s in sectors.values())

    agent_id = await _agent(client, biz, fake_redis, RECEPTION)
    tests = copy.deepcopy(sectors["barberia_peluqueria"]["tests"])
    tests[0]["name"] = "Pide cita para pasado mañana"
    bad = await client.post(
        "/admin/builder/sector-tests/barberia_peluqueria", json={"tests": tests[:11]}, headers=ops
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "twelve_tests_required"
    published = await client.post(
        "/admin/builder/sector-tests/barberia_peluqueria", json={"tests": tests}, headers=ops
    )
    assert published.status_code == 201, published.text
    assert published.json()["version"] == 2
    # La suite que ya existía sigue con la versión 1.
    suite = (
        await client.get(
            f"/console/clients/{biz.ref}/agents/{agent_id}/tests", headers=biz.headers()
        )
    ).json()
    refs = {t["sector_test_ref"] for t in suite["tests"] if t["kind"] == "sector"}
    assert refs and all(r.startswith("barberia_peluqueria@1#") for r in refs)
    unknown = await client.post(
        "/admin/builder/sector-tests/astronautas", json={"tests": tests}, headers=ops
    )
    assert unknown.status_code == 404
    async with db_session.begin():
        await db_session.execute(
            sa.text(
                "DELETE FROM sector_test_catalog WHERE sector_key = 'barberia_peluqueria' AND version = 2"
            )
        )


async def test_the_judge_blocks_only_once_calibrated(
    client: Any, db_session: AsyncSession, ops: dict[str, str]
) -> None:
    examples = {e["id"]: e for e in calibration_set()}

    def judge_that(agree: bool) -> Any:
        async def judge(messages: list[dict[str, str]]) -> str:
            text = messages[1]["content"]
            example = next(e for e in examples.values() if e["transcript"][1]["bubbles"][0] in text)
            dims = [
                {
                    "key": key,
                    "verdict": label if agree else ("fail" if label == "pass" else "pass"),
                    "why": "",
                }
                for key, label in example["labels"].items()
            ]
            return json.dumps({"dimensions": dims})

        return judge

    async with db_session.begin():
        deployment = await db_session.scalar(sa.text("SELECT id FROM model_profiles LIMIT 1"))
    try:
        set_calibration_judge(judge_that(agree=False))
        poor = await client.post(
            "/admin/builder/judge-calibration", json={"deployment_id": str(deployment)}, headers=ops
        )
        assert poor.status_code == 201, poor.text
        assert poor.json()["passed"] is False and poor.json()["agreement"] < 0.85
        async with db_session.begin():
            assert await judge_calibrated(db_session) is False

        set_calibration_judge(judge_that(agree=True))
        good = await client.post(
            "/admin/builder/judge-calibration", json={"deployment_id": str(deployment)}, headers=ops
        )
        assert good.json()["passed"] is True and good.json()["agreement"] == 1.0
        async with db_session.begin():
            assert await judge_calibrated(db_session) is True
        report = (await client.get("/admin/builder/judge-calibration", headers=ops)).json()
        assert report[0]["passed"] is True
        assert len(report[0]["scores"]["items"]) == sum(len(e["labels"]) for e in examples.values())
    finally:
        set_calibration_judge(None)
        async with db_session.begin():
            await db_session.execute(
                sa.text("DELETE FROM model_task_certifications WHERE task = 'judge'")
            )


async def test_the_builder_eval_measures_the_bank_and_compares(
    client: Any, ops: dict[str, str]
) -> None:
    """T100 (54.4, CE-002, CE-003): el banco v2 tiene las 100 descripciones de
    antes, cada una con su negocio, y 20 de sectores sin guía (58.7); la evaluación
    guarda el validador a la primera y el p90, y la diferencia con la vez anterior."""
    from nexus_api.api.admin.sector_tests import set_eval_model
    from nexus_api.services.builder.evaluation import bank

    assert len(bank()) == 120
    calls = {"n": 0}

    async def model(_messages: list[dict[str, str]]) -> str:
        calls["n"] += 1
        reply = copy.deepcopy(RECEPTION)
        if calls["n"] % 2 == 0:
            reply["tools"] = [*reply["tools"], "calendar.unknown"]
        return json.dumps(reply)

    try:
        set_eval_model(model)
        first = await client.post("/admin/builder/eval", json={"limit": 4}, headers=ops)
        assert first.status_code == 201, first.text
        assert first.json()["validator_first_pass_pct"] == 50.0
        assert first.json()["draft_p90_ms"] is not None
        second = await client.post("/admin/builder/eval", json={"limit": 2}, headers=ops)
        assert second.json()["vs_previous"]["validator_first_pass_pct"] == 0.0
        listed = (await client.get("/admin/builder/eval", headers=ops)).json()
        assert len(listed) >= 2
    finally:
        set_eval_model(None)
