"""El catálogo de pruebas del sector en el panel de operador — spec 047, T090
(requisito 54.10).

- ``GET /admin/builder/sector-tests``: cada sector con su versión vigente y sus
  12 pruebas;
- ``POST /admin/builder/sector-tests/{sector}`` ``{tests: [...12]}``: publica una
  versión nueva. Las suites de los agentes que ya existen no cambian: cada prueba
  recuerda de qué versión salió.

Tabla de plataforma: sin datos de ningún cliente.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.services.builder.sectors import SECTORS
from nexus_api.services.testing import sector_catalog

router = APIRouter(prefix="/builder/sector-tests", dependencies=[Depends(require_admin_token)])


class SectorOut(BaseModel):
    sector: str
    name: str
    version: int | None
    published_at: datetime | None
    published_by: str | None
    tests: list[dict[str, Any]]


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tests: list[dict[str, Any]]


@router.get("", response_model=list[SectorOut])
async def list_sectors(session: AsyncSession = Depends(get_db_session)) -> list[SectorOut]:
    out: list[SectorOut] = []
    async with session.begin():
        for key, name in SECTORS.items():
            row = await sector_catalog.latest(session, key)
            out.append(
                SectorOut(
                    sector=key,
                    name=name,
                    version=row.version if row else None,
                    published_at=row.published_at if row else None,
                    published_by=row.published_by if row else None,
                    tests=list(row.tests) if row else [],
                )
            )
    return out


@router.post("/{sector}", response_model=SectorOut, status_code=status.HTTP_201_CREATED)
async def publish_sector(
    sector: str,
    body: PublishIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> SectorOut:
    async with session.begin():
        try:
            row = await sector_catalog.publish(
                session, sector, body.tests, by=f"operator:{operator.id}"
            )
        except sector_catalog.SectorCatalogError as exc:
            code = status.HTTP_404_NOT_FOUND if exc.code == "unknown_sector" else 422
            raise HTTPException(status_code=code, detail={"code": exc.code}) from exc
        return SectorOut(
            sector=sector,
            name=SECTORS[sector],
            version=row.version,
            published_at=row.published_at,
            published_by=row.published_by,
            tests=list(row.tests),
        )


# ── la calibración del juez (T087, requisito 21.8) ─────────────────────────

calibration_router = APIRouter(
    prefix="/builder/judge-calibration", dependencies=[Depends(require_admin_token)]
)

_judge_override: Any | None = None


def set_calibration_judge(judge: Any | None) -> None:
    """Gancho de pruebas: el juez de mentira."""
    global _judge_override
    _judge_override = judge


def _judge_for(model_id: str) -> Any:
    if _judge_override is not None:
        return _judge_override
    import uuid as _uuid

    from nexus_worker.runtime.llm import LiteLLMProvider

    provider = LiteLLMProvider(context_management=None)

    async def judge(messages: list[dict[str, str]]) -> str:
        return str(
            await provider.acomplete(
                tenant_id=_uuid.UUID(int=0), role="judge", model=model_id, messages=messages
            )
        )

    return judge


class CalibrateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_id: str


@calibration_router.get("")
async def calibration_report(
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    from nexus_api.services.testing.calibration import latest_report

    async with session.begin():
        return await latest_report(session)


@calibration_router.post("", status_code=status.HTTP_201_CREATED)
async def run_calibration(
    body: CalibrateIn,
    session: AsyncSession = Depends(get_db_session),
    _operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    """Corre el juez de ese despliegue sobre el conjunto etiquetado y guarda su
    acuerdo como certificación de la tarea ``judge``. La paga Auphere."""
    import sqlalchemy as sa

    from nexus_api.services.testing.calibration import calibrate, record

    async with session.begin():
        model_id = await session.scalar(
            sa.text("SELECT model_id FROM model_profiles WHERE id = CAST(:d AS uuid)"),
            {"d": body.deployment_id},
        )
    if model_id is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_deployment"})
    report = await calibrate(_judge_for(str(model_id)))
    async with session.begin():
        import uuid as _uuid

        await record(session, _uuid.UUID(body.deployment_id), report)
    return {"deployment_id": body.deployment_id, **report.scores(), "passed": report.passed}


# ── la evaluación del constructor (T100, requisito 54.4) ───────────────────

eval_router = APIRouter(prefix="/builder/eval", dependencies=[Depends(require_admin_token)])

_eval_model_override: Any | None = None


def set_eval_model(complete: Any | None) -> None:
    """Gancho de pruebas: el modelo del constructor en la evaluación."""
    global _eval_model_override
    _eval_model_override = complete


class EvalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int | None = None


async def _catalog_context(session: AsyncSession) -> Any:
    """El catálogo como lo vería un cliente sin integraciones conectadas."""
    import sqlalchemy as sa

    from nexus_api.api.console.capability_names import requires_connector
    from nexus_api.db.models import Connector, ToolCatalog
    from nexus_api.services.agent_spec.validator import Context, ToolInfo, _model_visible_args

    args = _model_visible_args()
    rows = await session.execute(
        sa.select(ToolCatalog, Connector.slug, Connector.status).outerjoin(
            Connector, Connector.id == ToolCatalog.connector_id
        )
    )
    tools = {}
    for tool, slug, connector_status in rows.tuples().all():
        integration = slug or requires_connector(tool.name, "tool")
        tools[tool.name] = ToolInfo(
            name=tool.name,
            status=getattr(tool.status, "value", str(tool.status)),
            integration=integration,
            integration_offered=connector_status in (None, "available", "beta"),
            connected=integration is None,
            args=args.get(tool.name, frozenset()),
        )
    return Context(tools=tools)


@eval_router.get("")
async def eval_history(session: AsyncSession = Depends(get_db_session)) -> list[dict[str, Any]]:
    from nexus_api.services.builder.evaluation import history

    async with session.begin():
        return await history(session)


@eval_router.post("", status_code=status.HTTP_201_CREATED)
async def run_eval(
    body: EvalIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    """Corre el constructor sobre el banco (o sus primeras ``limit``) y guarda las
    métricas. Lo paga Auphere; no escribe nada en ningún cliente."""
    from nexus_api.services.builder.evaluation import bank, evaluate, history, record

    complete = _eval_model_override
    if complete is None:
        import os
        import uuid as _uuid

        from nexus_worker.config import get_worker_settings
        from nexus_worker.runtime.llm import LiteLLMProvider

        provider = LiteLLMProvider(context_management=None)
        model = os.environ.get("NEXUS_LLM_BUILD_MODEL") or get_worker_settings().llm_respond_model

        async def complete(messages: list[dict[str, str]]) -> str:
            return str(
                await provider.acomplete(
                    tenant_id=_uuid.UUID(int=0), role="build", model=model, messages=messages
                )
            )

    async with session.begin():
        ctx = await _catalog_context(session)
    items = bank()[: body.limit] if body.limit else bank()
    report = await evaluate(complete, ctx=ctx, items=items)
    async with session.begin():
        await record(session, report, by=f"operator:{operator.id}")
        return (await history(session, limit=2))[0]


__all__ = ["calibration_router", "eval_router", "router", "set_calibration_judge", "set_eval_model"]
