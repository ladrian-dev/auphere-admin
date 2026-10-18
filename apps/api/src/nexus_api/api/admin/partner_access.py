"""Admin — which console views and services a partner has (spec 032).

``GET/PUT /admin/partners/{id}/access``. The partner is the path; the person
is ``X-Operator-Id`` (ADR-034) and the audit names them. The response carries
the catalog so the panel draws its tiles from the API's list.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import PARTNER_MODULES, PARTNER_NAV_MODULES, OperatorAccount
from nexus_api.services import partner_access
from nexus_api.services.partner_access import PartnerAccessError, PartnerAccessView

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])

ModuleLiteral = Literal[
    "panel",
    "clients",
    "usage",
    "audit",
    "knowledge",
    "workstation",
    "team",
    "billing",
    "keys",
    "companion",
]


class CatalogItemOut(BaseModel):
    id: str
    #: ``nav`` = a view of the console's sidebar; ``assistant`` = the Companion.
    kind: Literal["nav", "assistant"]


class PartnerAccessOut(BaseModel):
    console_enabled: bool
    modules: list[str]
    catalog: list[CatalogItemOut]


class PartnerAccessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    console_enabled: bool
    modules: list[ModuleLiteral] = Field(max_length=len(PARTNER_MODULES))


def _out(view: PartnerAccessView) -> PartnerAccessOut:
    return PartnerAccessOut(
        console_enabled=view.console_enabled,
        modules=view.modules,
        catalog=[
            CatalogItemOut(id=m, kind="nav" if m in PARTNER_NAV_MODULES else "assistant")
            for m in PARTNER_MODULES
        ],
    )


def _error(exc: PartnerAccessError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code})


@router.get("/{partner_id}/access", response_model=PartnerAccessOut)
async def get_partner_access(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> PartnerAccessOut:
    try:
        async with session.begin():
            return _out(await partner_access.read_access(session, partner_id))
    except PartnerAccessError as exc:
        raise _error(exc) from None


@router.put("/{partner_id}/access", response_model=PartnerAccessOut)
async def set_partner_access(
    partner_id: uuid.UUID,
    body: PartnerAccessIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
) -> PartnerAccessOut:
    try:
        async with session.begin():
            view = await partner_access.set_access(
                session,
                partner_id,
                console_enabled=body.console_enabled,
                modules=list(body.modules),
                actor=operator_actor(operator),
            )
            return _out(view)
    except PartnerAccessError as exc:
        raise _error(exc) from None
