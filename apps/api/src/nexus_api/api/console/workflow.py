"""``/console/clients/{ref}/workflow`` — apply path for packs (Fase 4)."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models.workflow import WorkflowCron, WorkflowPack, WorkflowRun
from nexus_api.packs.cron import next_run_utc
from nexus_api.packs.schema import WorkflowPackIn, WorkflowPackSpec, parse_workflow_body

from .deps import ClientRef, resolve_mapping
from .schemas_workflow import WorkflowCronOut, WorkflowPackOut, WorkflowRunOut, WorkflowRunsOut

router = APIRouter()


def _http_422(exc: Exception | str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _spec_to_yaml(spec: WorkflowPackSpec) -> dict[str, Any]:
    return spec.model_dump(mode="json", exclude_none=True)


def _out(ref: str, pack: WorkflowPack | None) -> WorkflowPackOut:
    if pack is None:
        return WorkflowPackOut(client_ref=ref, is_set=False)
    raw = dict(pack.yaml or {})
    cron_raw = raw.get("cron")
    cron = None
    if isinstance(cron_raw, dict):
        cron = WorkflowCronOut(
            hour=int(cron_raw["hour"]),
            minute=int(cron_raw["minute"]),
            timezone=str(cron_raw["timezone"]),
        )
    return WorkflowPackOut(
        client_ref=ref,
        is_set=True,
        version=pack.version,
        trigger=raw.get("trigger"),
        steps=list(raw.get("steps") or []),
        template_id=raw.get("template_id"),
        cron=cron,
        enabled=raw.get("enabled", True),
        end_time=raw.get("end_time"),
        stop=raw.get("stop", "end"),
    )


@router.get(
    "/clients/{ref}/workflow",
    response_model=WorkflowPackOut,
    responses={404: {"description": "Unknown client reference."}},
)
async def get_client_workflow(
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("agents:read")),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowPackOut:
    mapping = await resolve_mapping(session, principal, ref)
    async with session.begin():
        await apply_partner_to_session(session, principal.partner.id)
        pack = (
            await session.scalars(
                sa.select(WorkflowPack).where(
                    WorkflowPack.partner_id == principal.partner.id,
                    WorkflowPack.client_ref == mapping.external_client_ref,
                )
            )
        ).first()
    return _out(ref, pack)


@router.put(
    "/clients/{ref}/workflow",
    response_model=WorkflowPackOut,
    responses={
        404: {"description": "Unknown client reference."},
        422: {"description": "Invalid pack or extra keys (including partner_id)."},
    },
)
async def put_client_workflow(
    body: WorkflowPackIn,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("agents:write")),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowPackOut:
    try:
        spec = parse_workflow_body(body)
    except (ValidationError, ValueError) as exc:
        raise _http_422(exc) from exc
    if spec.client_ref and spec.client_ref != ref:
        raise _http_422("client_ref in body must match the path")
    spec = spec.model_copy(update={"client_ref": ref})
    mapping = await resolve_mapping(session, principal, ref)
    yaml_doc = _spec_to_yaml(spec)
    async with session.begin():
        await apply_partner_to_session(session, principal.partner.id)
        existing = (
            await session.scalars(
                sa.select(WorkflowPack).where(
                    WorkflowPack.partner_id == principal.partner.id,
                    WorkflowPack.client_ref == mapping.external_client_ref,
                )
            )
        ).first()
        if existing is None:
            pack = WorkflowPack(
                partner_id=principal.partner.id,
                client_ref=mapping.external_client_ref,
                yaml=yaml_doc,
                version=1,
            )
            session.add(pack)
            await session.flush()
        else:
            existing.yaml = yaml_doc
            existing.version = int(existing.version) + 1
            pack = existing
            await session.flush()
        await _sync_cron(session, pack, spec)
    return _out(ref, pack)


@router.get(
    "/clients/{ref}/workflow/runs",
    response_model=WorkflowRunsOut,
    responses={404: {"description": "Unknown client reference."}},
)
async def list_client_workflow_runs(
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("agents:read")),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunsOut:
    mapping = await resolve_mapping(session, principal, ref)
    async with session.begin():
        await apply_partner_to_session(session, principal.partner.id)
        pack = (
            await session.scalars(
                sa.select(WorkflowPack).where(
                    WorkflowPack.partner_id == principal.partner.id,
                    WorkflowPack.client_ref == mapping.external_client_ref,
                )
            )
        ).first()
        if pack is None:
            return WorkflowRunsOut(items=[])
        rows = (
            await session.scalars(
                sa.select(WorkflowRun)
                .where(WorkflowRun.pack_id == pack.id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(100)
            )
        ).all()
    return WorkflowRunsOut(
        items=[WorkflowRunOut(thread_id=r.thread_id, status=r.status) for r in rows]
    )


async def _sync_cron(session: AsyncSession, pack: WorkflowPack, spec: WorkflowPackSpec) -> None:
    existing = (
        await session.scalars(sa.select(WorkflowCron).where(WorkflowCron.pack_id == pack.id))
    ).first()
    live = spec.trigger == "cron" and spec.enabled and spec.cron is not None
    if not live:
        if existing is not None:
            existing.enabled = False
        return
    assert spec.cron is not None
    run_at = next_run_utc(spec.cron.hour, spec.cron.minute, spec.cron.timezone)
    if existing is None:
        session.add(
            WorkflowCron(
                partner_id=pack.partner_id,
                pack_id=pack.id,
                run_at_utc=run_at,
                timezone=spec.cron.timezone,
                hour=spec.cron.hour,
                minute=spec.cron.minute,
                enabled=True,
                end_time=spec.end_time,
            )
        )
        return
    existing.run_at_utc = run_at
    existing.timezone = spec.cron.timezone
    existing.hour = spec.cron.hour
    existing.minute = spec.cron.minute
    existing.enabled = True
    existing.end_time = spec.end_time


# silence unused import if ruff wants insert
