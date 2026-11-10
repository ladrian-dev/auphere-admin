"""Las certificaciones en el panel de operador — spec 047, T150 (requisitos
42.1, 42.7 y 54.3; ``contracts/admin-api.md`` §3).

- **Por despliegue** (``model_task_certifications``, plataforma): batería, fecha,
  notas, umbral y caducidad, también las caducadas, para ver por qué un
  despliegue dejó de contar.
- **Por agente** (``agent_model_certifications``, por cliente con RLS): cada
  cliente leído con su GUC; ninguna fila de un cliente sale con el id de otro.
- **Lanzar una certificación**: la batería común (por clase) corre hoy fuera de
  línea con ``nexus_worker.certification`` —no hay trabajo de plataforma que la
  lleve—, y la suite de un agente con un despliegue es el trabajo
  ``quality_check`` de T147, que aún no tiene manejador. La ruta lo dice con su
  código (``409``) en vez de dejar en cola un trabajo que fallaría.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OperatorAccount

router = APIRouter(prefix="/certifications", dependencies=[Depends(require_admin_token)])


class ClassCertificationOut(BaseModel):
    deployment: str
    task: str
    battery_version: int
    quality: float
    passed: bool
    scores: dict[str, Any]
    certified_at: datetime
    invalidated_at: datetime | None


class AgentCertificationOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    agent_id: uuid.UUID
    agent_name: str
    deployment: str
    agent_config_id: uuid.UUID
    suite_revision: int
    passed: bool
    paid_by: str
    result: dict[str, Any]
    certified_at: datetime
    invalidated_at: datetime | None


class CertificationsOut(BaseModel):
    by_deployment: list[ClassCertificationOut]
    by_agent: list[AgentCertificationOut]
    battery_version: int | None


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: uuid.UUID
    tasks: list[str] = Field(default_factory=list, max_length=15)
    agent_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


_CLASS_SQL = """
    SELECT p.model_id AS deployment, c.task, c.battery_version, c.quality, c.passed, c.scores,
           c.certified_at, c.invalidated_at
      FROM model_task_certifications c
      JOIN model_profiles p ON p.id = c.deployment_id
     WHERE (CAST(:deployment AS text) IS NULL OR p.model_id = :deployment)
       AND (CAST(:task AS text) IS NULL OR c.task = :task)
     ORDER BY p.model_id, c.task, c.battery_version DESC
"""
_AGENT_SQL = """
    SELECT c.agent_id, a.name AS agent_name, p.model_id AS deployment, c.agent_config_id,
           c.suite_revision, c.passed, c.paid_by, c.result, c.certified_at, c.invalidated_at
      FROM agent_model_certifications c
      JOIN agents a ON a.id = c.agent_id
      JOIN model_profiles p ON p.id = c.deployment_id
     WHERE (CAST(:deployment AS text) IS NULL OR p.model_id = :deployment)
       AND (CAST(:agent AS uuid) IS NULL OR c.agent_id = :agent)
     ORDER BY c.certified_at DESC
"""


@router.get("", response_model=CertificationsOut)
async def list_certifications(
    deployment: str | None = None,
    task: str | None = None,
    agent: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> CertificationsOut:
    async with session.begin():
        by_deployment = [
            ClassCertificationOut(
                deployment=str(r.deployment),
                task=str(r.task),
                battery_version=int(r.battery_version),
                quality=float(r.quality),
                passed=bool(r.passed),
                scores=dict(r.scores or {}),
                certified_at=r.certified_at,
                invalidated_at=r.invalidated_at,
            )
            for r in (
                await session.execute(sa.text(_CLASS_SQL), {"deployment": deployment, "task": task})
            ).all()
        ]
        battery = await session.scalar(
            sa.text(
                "SELECT max(battery_version) FROM model_task_certifications "
                "WHERE invalidated_at IS NULL"
            )
        )
        tenants = (
            await session.execute(
                sa.text("SELECT id, name FROM tenants WHERE status <> 'archived' ORDER BY name")
            )
        ).all()
    by_agent: list[AgentCertificationOut] = []
    if task is None or task in ("answer", "tool_turn"):
        sm = get_sessionmaker()
        for tenant_id, tenant_name in tenants:
            async with sm() as scoped, tenant_scoped_session(scoped, tenant_id):
                for r in (
                    await scoped.execute(
                        sa.text(_AGENT_SQL), {"deployment": deployment, "agent": agent}
                    )
                ).all():
                    by_agent.append(
                        AgentCertificationOut(
                            tenant_id=tenant_id,
                            tenant_name=str(tenant_name),
                            agent_id=r.agent_id,
                            agent_name=str(r.agent_name),
                            deployment=str(r.deployment),
                            agent_config_id=r.agent_config_id,
                            suite_revision=int(r.suite_revision),
                            passed=bool(r.passed),
                            paid_by=str(r.paid_by),
                            result=dict(r.result or {}),
                            certified_at=r.certified_at,
                            invalidated_at=r.invalidated_at,
                        )
                    )
    return CertificationsOut(
        by_deployment=by_deployment,
        by_agent=by_agent,
        battery_version=None if battery is None else int(battery),
    )


@router.get("/batteries")
async def batteries() -> dict[str, Any]:
    """La batería común en español que está en el código (v1) y lo que le falta."""
    from nexus_worker.certification.battery import coverage_gaps, load_battery_v1

    battery = load_battery_v1(tau_bench_path=None)
    sources: dict[str, int] = {}
    for case in battery.cases:
        sources[case.source] = sources.get(case.source, 0) + 1
    return {
        "items": [
            {
                "version": battery.version,
                "cases": len(battery.cases),
                "sources": sources,
                "weights": dict(battery.weights),
                "threshold": battery.threshold,
                "coverage_gaps": list(coverage_gaps(battery)),
            }
        ]
    }


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def launch(
    body: RunIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    """Lanzar una certificación pagada por Auphere, fuera de las partidas (42.6)."""
    if bool(body.tasks) == bool(body.agent_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "tasks_or_agents"},
        )
    async with session.begin():
        found = await session.scalar(
            sa.text("SELECT model_id FROM model_profiles WHERE id = :d"), {"d": body.deployment_id}
        )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "unknown_deployment"})
    if body.tasks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "class_runner_offline",
                "message": (
                    "La batería común corre fuera de línea (nexus_worker.certification) "
                    "hasta que tenga un trabajo de plataforma."
                ),
            },
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "agent_runner_pending",
            "message": (
                "La suite del agente con un despliegue es el trabajo quality_check (T147), "
                "que aún no tiene manejador."
            ),
        },
    )


__all__ = ["router"]
