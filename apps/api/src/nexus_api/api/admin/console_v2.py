"""La consola nueva de un partner en el panel de operador — spec 047, T180
(requisitos 55.2, 55.4 y 55.5; ``contracts/admin-api.md`` §5).

- ``POST /admin/partners/{id}/console-v2/dry-run``: el ensayo; compara por agente
  (prompt idéntico byte a byte y modelo fijado) y por número (audiencia efectiva
  antes y después) y deja su informe. No cambia nada.
- ``POST /admin/partners/{id}/console-v2/enable``: activa con un ensayo limpio de
  las últimas 24 h (``409 dry_run_required`` o ``dry_run_has_differences``).
- ``POST /admin/partners/{id}/console-v2/disable``: devuelve la consola de hoy
  hasta que el partner confirme el reparto en bolsas (``409
  wallet_split_confirmed``).
- ``GET /admin/partners/{id}/console-v2/reports``: los informes, del último al
  primero, con el nombre de cada cliente.
- ``GET /admin/partners/{id}/console-v2``: qué consola ve hoy el partner.

Cada escritura acepta ``{reason}``: queda en el informe y en la auditoría.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import MigrationReport, OperatorAccount, PartnerTenant
from nexus_api.services import console_v2

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, min_length=3, max_length=300)


def _error(exc: console_v2.ConsoleV2Error) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


def _state(state: console_v2.ConsoleV2State) -> dict[str, Any]:
    return {
        "version": state.version,
        "enabled_at": state.enabled_at.isoformat() if state.enabled_at else None,
        "enabled_by": state.enabled_by,
    }


@router.post("/{partner_id}/console-v2/dry-run")
async def dry_run(
    partner_id: uuid.UUID,
    body: ReasonIn | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    try:
        run = await console_v2.dry_run(
            session,
            partner_id,
            actor=operator_actor(operator),
            reason=body.reason if body else None,
        )
    except console_v2.ConsoleV2Error as exc:
        raise _error(exc) from None
    return {"status": run.status, "agents": run.agents, "channels": run.channels}


@router.post("/{partner_id}/console-v2/enable")
async def enable(
    partner_id: uuid.UUID,
    body: ReasonIn | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    try:
        state = await console_v2.activate(
            session,
            partner_id,
            actor=operator_actor(operator),
            reason=body.reason if body else None,
        )
    except console_v2.ConsoleV2Error as exc:
        raise _error(exc) from None
    return _state(state)


@router.post("/{partner_id}/console-v2/disable")
async def disable(
    partner_id: uuid.UUID,
    body: ReasonIn | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    try:
        state = await console_v2.deactivate(
            session,
            partner_id,
            actor=operator_actor(operator),
            reason=body.reason if body else None,
        )
    except console_v2.ConsoleV2Error as exc:
        raise _error(exc) from None
    return _state(state)


@router.get("/{partner_id}/console-v2")
async def current(
    partner_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> dict[str, Any]:
    try:
        return _state(await console_v2.state_of(session, partner_id))
    except console_v2.ConsoleV2Error as exc:
        raise _error(exc) from None


@router.get("/{partner_id}/console-v2/reports")
async def reports(
    partner_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> list[dict[str, Any]]:
    async with session.begin():
        names = {
            str(tid): name
            for tid, name in (
                await session.execute(
                    sa.select(PartnerTenant.tenant_id, PartnerTenant.client_name).where(
                        PartnerTenant.partner_id == partner_id
                    )
                )
            ).all()
        }
    async with session.begin():
        await apply_partner_to_session(session, partner_id)
        rows = (
            await session.scalars(
                sa.select(MigrationReport)
                .where(MigrationReport.partner_id == partner_id)
                .order_by(MigrationReport.created_at.desc())
                .limit(50)
            )
        ).all()

    def _named(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**i, "client_name": names.get(str(i.get("tenant_id")))} for i in items]

    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "status": r.status,
            "agents": _named(r.eval_diff),
            "channels": _named(r.audience_diff),
            "created_by": r.created_by,
            "reason": r.reason,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


__all__ = ["router"]
