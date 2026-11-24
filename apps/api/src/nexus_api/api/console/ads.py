"""El informe de anuncios de un cliente en la consola de partners — spec 076, requisito 3.

``GET /console/clients/{ref}/ads/report?days=7|30|90``. El cliente sale de
``{ref}`` bajo el partner del token (``client_scope``), y la sesión queda con su
tenant: la RLS decide. Ningún campo se llama ``body``, ``text``, ``message``,
``content`` ni ``reason`` (``test_console_scope.py``), y no hay nombres ni
teléfonos de clientes finales: el titular es texto del anunciante.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from nexus_api.services.ad_report import PERIODS, ads_report

from .deps import ClientScope, client_scope

router = APIRouter(prefix="/clients/{ref}")


class AdAmountOut(BaseModel):
    currency: str
    amount_minor: int


class AdRowOut(BaseModel):
    ad_id: str | None
    ad_kind: Literal["ad", "post"]
    ad_headline: str | None
    ad_url: str | None
    conversations: int
    bookings: int
    amounts: list[AdAmountOut]


class AdsReportOut(BaseModel):
    days: int
    rows: list[AdRowOut]


@router.get("/ads/report", response_model=AdsReportOut)
async def read_ads_report(
    days: int = Query(default=30),
    scope: ClientScope = Depends(client_scope("conversations:read")),
) -> AdsReportOut:
    if days not in PERIODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bad_period", "allowed": list(PERIODS)},
        )
    rows = await ads_report(scope.session, days=days)
    return AdsReportOut(
        days=days,
        rows=[
            AdRowOut(
                ad_id=r.ad_id,
                ad_kind="post" if r.ad_kind == "post" else "ad",
                ad_headline=r.ad_headline,
                ad_url=r.ad_url,
                conversations=r.conversations,
                bookings=r.bookings,
                amounts=[
                    AdAmountOut(currency=c, amount_minor=a) for c, a in sorted(r.amounts.items())
                ],
            )
            for r in rows
        ],
    )
