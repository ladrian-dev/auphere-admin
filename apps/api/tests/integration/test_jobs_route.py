"""Spec 047, T003 — ``GET /console/jobs/{job_id}`` (``contracts/console-api.md`` §1).

La consola consulta aquí, con espera creciente, el trabajo que lanzó. Lo que se
fija:

- devuelve el estado, el progreso por bloques, las preguntas y el resultado,
  **nunca el coste** (C9);
- un trabajo de un cliente de **otro partner** responde **404 opaco**: el mismo
  cuerpo, byte a byte, que un id que no existe (no confirma que exista);
- un trabajo colgado se da por ``failed``/``timeout`` al leerlo;
- sin credencial, 401; un rol sin ``clients:read``, 403.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job
from nexus_api.services import jobs
from tests.conftest import add_console_member

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _job(db_session: AsyncSession, tenant_id: uuid.UUID, *, kind: str = "client_read") -> Job:
    async with tenant_scoped_session(db_session, tenant_id):
        return await jobs.create_job(db_session, kind=kind, created_by="owner@example.com")


async def test_the_partner_reads_its_own_job(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    job = await _job(db_session, a["tenant_id"], kind="agent_draft")
    async with tenant_scoped_session(db_session, a["tenant_id"]):
        await jobs.start_job(db_session, job.id)
        await jobs.report_progress(
            db_session, job.id, step="skills", block={"key": "purpose", "value": "Citas"}
        )

    resp = await client.get(f"/console/jobs/{job.id}", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == str(job.id)
    assert body["kind"] == "agent_draft"
    assert body["status"] == "running"
    assert body["progress"] == {"step": "skills", "blocks": [{"key": "purpose", "value": "Citas"}]}
    assert body["error_code"] is None
    assert body["finished_at"] is None


async def test_a_finished_job_brings_its_result_and_never_its_cost(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    job = await _job(db_session, a["tenant_id"])
    async with tenant_scoped_session(db_session, a["tenant_id"]):
        await jobs.start_job(db_session, job.id)
        await jobs.finish_job(db_session, job.id, result={"pages": 12}, cost_micros=98_765)

    resp = await client.get(f"/console/jobs/{job.id}", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["result"] == {"pages": 12}
    assert body["finished_at"] is not None
    assert "cost_micros" not in body
    assert "98765" not in resp.text
    assert "tenant_id" not in resp.text


async def test_another_partners_job_is_an_opaque_404(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a, b = console_world["a"], console_world["b"]
    job_b = await _job(db_session, b["tenant_id"])

    foreign = await client.get(f"/console/jobs/{job_b.id}", headers=a["headers"]())
    missing = await client.get(f"/console/jobs/{uuid.uuid4()}", headers=a["headers"]())

    assert foreign.status_code == 404
    assert missing.status_code == 404
    # Byte-identical: the answer never confirms the job exists elsewhere.
    assert foreign.content == missing.content
    # And the owner still sees it.
    own = await client.get(f"/console/jobs/{job_b.id}", headers=b["headers"]())
    assert own.status_code == 200


async def test_a_client_of_the_partner_that_is_not_mapped_is_a_404(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    # A tenant that carries the partner's id but has no ``partner_tenants`` row
    # is not one of its clients: the mapping is the only proof.
    from nexus_api.db.models import Tenant, TenantPlan, TenantStatus

    a = console_world["a"]
    orphan = uuid.uuid4()
    db_session.add(
        Tenant(
            id=orphan,
            name="Sin mapa",
            slug=f"orphan-{orphan.hex[:8]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            partner_id=a["partner_id"],
        )
    )
    await db_session.commit()
    job = await _job(db_session, orphan)

    resp = await client.get(f"/console/jobs/{job.id}", headers=a["headers"]())
    assert resp.status_code == 404


async def test_a_hung_job_is_read_as_failed_with_timeout(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    job = await _job(db_session, a["tenant_id"])
    async with tenant_scoped_session(db_session, a["tenant_id"]):
        await jobs.start_job(db_session, job.id)
        # The replica died: no heartbeat since long before the window.
        await db_session.execute(
            sa.update(Job)
            .where(Job.id == job.id)
            .values(updated_at=sa.func.now() - jobs.RUNNING_STALE_AFTER * 2)
        )

    resp = await client.get(f"/console/jobs/{job.id}", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["status"], body["error_code"]) == ("failed", "timeout")
    assert body["finished_at"] is not None


async def test_without_a_token_it_is_a_401(client: Any, console_world: dict[str, Any]) -> None:
    resp = await client.get(f"/console/jobs/{uuid.uuid4()}")
    assert resp.status_code == 401


async def test_a_role_without_clients_read_is_a_403(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    job = await _job(db_session, a["tenant_id"])
    billing = await add_console_member(db_session, partner_id=a["partner_id"], role="billing")

    resp = await client.get(f"/console/jobs/{job.id}", headers=billing["headers"]())
    assert resp.status_code == 403


async def test_an_analyst_can_follow_a_job(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    job = await _job(db_session, a["tenant_id"])
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")

    resp = await client.get(f"/console/jobs/{job.id}", headers=analyst["headers"]())
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
