"""Spec 059, T031 (requisitos 5.4 y 5.5) — el juez solo bloquea si está calibrado él.

Antes bastaba con que **algún** despliegue tuviera una calibración aprobada de la
tarea ``judge`` para que el juez bloqueara, aunque el modelo que juzga fuera otro.
Ahora cuenta solo la calibración aprobada y vigente del modelo que hace de juez en
el despliegue (``default_models()["judge"]``):

- ``judge_calibrated(session, model=…)`` ignora la de otro modelo;
- la consola (``api/console/agent_tests.py``) le pasa el juez del registro;
- ``GET /admin/builder/judge-calibration`` dice qué modelo es el juez y si está
  calibrado.

El trabajo del worker se prueba en ``test_model_failures_are_not_agent_failures.py``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.platform_models import default_models
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services import operator_identity
from nexus_api.services.testing.judge import JUDGE_TASK, judge_calibrated

from ..business._business_world import Biz, new_business
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft, turn_reservas_on

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def two_models(db_session: AsyncSession) -> Any:
    """Dos despliegues del catálogo: ``judge`` (el que juzga) y ``other``."""
    async with db_session.begin():
        # Ninguna calibración que haya dejado otra prueba.
        await db_session.execute(
            sa.text("DELETE FROM model_task_certifications WHERE task = :t"), {"t": JUDGE_TASK}
        )
        rows = (
            await db_session.execute(
                sa.text("SELECT id, model_id FROM model_profiles ORDER BY model_id LIMIT 2")
            )
        ).all()
    assert len(rows) == 2, "el catálogo sembrado tiene al menos dos despliegues"
    yield {"judge": (rows[0][0], rows[0][1]), "other": (rows[1][0], rows[1][1])}
    async with db_session.begin():
        await db_session.execute(
            sa.text("DELETE FROM model_task_certifications WHERE task = :t"), {"t": JUDGE_TASK}
        )


async def _certify(
    db_session: AsyncSession, deployment_id: uuid.UUID, *, passed: bool = True, stale: bool = False
) -> None:
    async with db_session.begin():
        await db_session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed, invalidated_at) "
                "VALUES (:d, :t, 1, CAST(:s AS jsonb), :q, :p, "
                "CASE WHEN :stale THEN now() ELSE NULL END) "
                "ON CONFLICT (deployment_id, task, battery_version) DO UPDATE SET "
                "passed = EXCLUDED.passed, quality = EXCLUDED.quality, "
                "invalidated_at = EXCLUDED.invalidated_at"
            ),
            {
                "d": deployment_id,
                "t": JUDGE_TASK,
                "s": json.dumps({"agreement": 0.9, "threshold": 0.85, "items": []}),
                "q": 0.9 if passed else 0.5,
                "p": passed,
                "stale": stale,
            },
        )


async def test_only_the_calibration_of_the_judge_counts(
    db_session: AsyncSession, two_models: dict[str, tuple[uuid.UUID, str]]
) -> None:
    (judge_id, judge), (other_id, other) = two_models["judge"], two_models["other"]

    await _certify(db_session, other_id)
    async with db_session.begin():
        assert await judge_calibrated(db_session, model=judge) is False, (
            "la calibración de otro modelo no hace bloquear al juez"
        )
        assert await judge_calibrated(db_session, model=other) is True

    await _certify(db_session, judge_id, passed=False)
    async with db_session.begin():
        assert await judge_calibrated(db_session, model=judge) is False, "suspendida no cuenta"

    await _certify(db_session, judge_id, stale=True)
    async with db_session.begin():
        assert await judge_calibrated(db_session, model=judge) is False, "caducada no cuenta"

    await _certify(db_session, judge_id)
    async with db_session.begin():
        assert await judge_calibrated(db_session, model=judge) is True


@pytest_asyncio.fixture
async def ops(db_session: AsyncSession, admin_headers: dict[str, str]) -> dict[str, str]:
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-059-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def test_the_panel_names_the_judge_and_says_if_it_is_calibrated(
    client: Any,
    db_session: AsyncSession,
    ops: dict[str, str],
    two_models: dict[str, tuple[uuid.UUID, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (judge_id, judge), (other_id, other) = two_models["judge"], two_models["other"]
    monkeypatch.setenv("NEXUS_LLM_JUDGE_MODEL", judge)
    assert default_models()["judge"] == judge

    await _certify(db_session, other_id)
    page = await client.get("/admin/builder/judge-calibration", headers=ops)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["judge_model"] == judge
    assert body["judge_calibrated"] is False
    assert [r["model_id"] for r in body["reports"]] == [other]

    await _certify(db_session, judge_id)
    body = (await client.get("/admin/builder/judge-calibration", headers=ops)).json()
    assert body["judge_calibrated"] is True
    assert {r["model_id"] for r in body["reports"]} == {judge, other}


async def test_the_console_asks_about_the_judge_of_the_registry(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    fake_redis: Any,
    two_models: dict[str, tuple[uuid.UUID, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (judge_id, judge), (other_id, _other) = two_models["judge"], two_models["other"]
    monkeypatch.setenv("NEXUS_LLM_JUDGE_MODEL", judge)
    biz: Biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    await turn_reservas_on(db_session, biz)
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name="Recepción")
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    url = f"/console/clients/{biz.ref}/agents/{job['result']['agent_id']}/tests"

    await _certify(db_session, other_id)
    suite = (await client.get(url, headers=biz.headers())).json()
    assert suite["judge_calibrated"] is False, "otro modelo calibrado no hace bloquear al juez"

    await _certify(db_session, judge_id)
    suite = (await client.get(url, headers=biz.headers())).json()
    assert suite["judge_calibrated"] is True
