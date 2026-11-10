"""Sectores sin guía y «Convertir en guía de Auphere» en el panel de operador — spec
047, enmienda del 2026-10-29 (T201; requisito 58.5; ``contracts/admin-sector-guides.md``;
research D66).

- ``GET /admin/builder/sector-guides``: las guías de Auphere (plantillas y convertidas);
- ``GET /admin/builder/sector-guides/missing?limit=``: las etiquetas sin guía que más
  se repiten, con sus guías generadas;
- ``GET /admin/builder/generated-guides/{tenant_id}/{guide_id}``: una, para revisarla;
- ``POST …/review`` y ``POST …/promote``: con ``X-Operator-Id``, en la auditoría con
  el correo de la persona, nunca el token.

Lo de cada cliente se lee y se escribe con su contexto declarado
(``services/builder/guides/promotion.py``).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import OperatorAccount
from nexus_api.services.builder.guides import promotion
from nexus_api.services.builder.guides.promotion import GuideAdminError

router = APIRouter(prefix="/builder", dependencies=[Depends(require_admin_token)])


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide: dict[str, Any] | None = None
    tests: list[dict[str, Any]] | None = None
    note: str | None = Field(default=None, max_length=300)


class PromoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z_]{2,40}$")
    label: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=3, max_length=300)


def _error(exc: GuideAdminError) -> HTTPException:
    detail: dict[str, Any] = {"code": exc.code}
    if exc.findings is not None:
        detail["findings"] = exc.findings
    return HTTPException(status_code=exc.status, detail=detail)


@router.get("/sector-guides")
async def list_guides(session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    async with session.begin():
        return {"items": await promotion.auphere_list(session)}


@router.get("/sector-guides/missing")
async def list_missing(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    async with session.begin():
        return await promotion.missing(session, limit=limit)


@router.get("/generated-guides/{tenant_id}/{guide_id}")
async def read_guide(
    tenant_id: uuid.UUID,
    guide_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        async with session.begin():
            return await promotion.read(session, tenant_id, guide_id)
    except GuideAdminError as exc:
        raise _error(exc) from None


@router.post("/generated-guides/{tenant_id}/{guide_id}/review")
async def review_guide(
    tenant_id: uuid.UUID,
    guide_id: uuid.UUID,
    body: ReviewIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    try:
        async with session.begin():
            return await promotion.review(
                session,
                tenant_id,
                guide_id,
                guide=body.guide,
                tests=body.tests,
                note=body.note,
                actor=operator_actor(operator),
            )
    except GuideAdminError as exc:
        raise _error(exc) from None


@router.post(
    "/generated-guides/{tenant_id}/{guide_id}/promote", status_code=status.HTTP_201_CREATED
)
async def promote_guide(
    tenant_id: uuid.UUID,
    guide_id: uuid.UUID,
    body: PromoteIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    try:
        async with session.begin():
            return await promotion.promote(
                session,
                tenant_id,
                guide_id,
                key=body.key,
                label=body.label,
                reason=body.reason,
                actor=operator_actor(operator),
            )
    except GuideAdminError as exc:
        raise _error(exc) from None


__all__ = ["router"]
