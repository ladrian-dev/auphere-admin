"""La beta «WhatsApp login» por país en el panel de operador — spec 047, T117
(requisitos 31.5 y 54.7; ``contracts/admin-api.md``).

- ``GET /admin/whatsapp/login-beta/countries``: dónde está activada;
- ``PUT /admin/whatsapp/login-beta/countries/{iso2}`` ``{enabled, reason}``:
  activarla o quitarla. Un país de la UE o del EEE es un ``422``
  (``eu_country_not_allowed``); la base lo rechaza también (CHECK de la 0191).

Auphere la activa cuando Meta se la da a su app; el enlace del dueño la ofrece solo
a los clientes de esos países (``channel_signup_links.whatsapp_login_allowed``).
Cada cambio queda en la auditoría con la persona de Auphere y su motivo.
"""

from __future__ import annotations

import re
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog, OperatorAccount, WhatsappLoginBetaCountry

#: Lo que queda en la auditoría de plataforma (vocabulario en 0202).
ENABLED_ACTION = "whatsapp.login_beta.enabled"
DISABLED_ACTION = "whatsapp.login_beta.disabled"

router = APIRouter(
    prefix="/whatsapp/login-beta/countries", dependencies=[Depends(require_admin_token)]
)

#: La UE y el EEE (D12): la misma lista que el CHECK de la migración 0191.
EU_EEA = frozenset(
    {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
        "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS",
        "LI", "NO",
        # Territorios de la UE con código propio (regiones ultraperiféricas, San
        # Martín y Åland).
        "GF", "GP", "MQ", "RE", "YT", "MF", "AX",
    }
)  # fmt: skip
_ISO2 = re.compile(r"^[A-Z]{2}$")


class CountryOut(BaseModel):
    country: str
    enabled_at: datetime
    enabled_by: str


class CountryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    reason: str = Field(min_length=3, max_length=300)


@router.get("", response_model=list[CountryOut])
async def list_countries(session: AsyncSession = Depends(get_db_session)) -> list[CountryOut]:
    async with session.begin():
        rows = (
            await session.scalars(
                sa.select(WhatsappLoginBetaCountry).order_by(WhatsappLoginBetaCountry.country)
            )
        ).all()
    return [
        CountryOut(country=r.country, enabled_at=r.enabled_at, enabled_by=r.enabled_by)
        for r in rows
    ]


@router.put("/{iso2}", response_model=list[CountryOut])
async def set_country(
    body: CountryIn,
    iso2: str = Path(min_length=2, max_length=2),
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> list[CountryOut]:
    country = iso2.upper()
    if not _ISO2.match(country):
        raise HTTPException(status_code=422, detail={"code": "invalid_country"})
    if body.enabled and country in EU_EEA:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "eu_country_not_allowed"},
        )
    actor = operator_actor(operator)
    async with session.begin():
        current = await session.get(WhatsappLoginBetaCountry, country)
        if body.enabled and current is None:
            session.add(WhatsappLoginBetaCountry(country=country, enabled_by=actor))
        elif not body.enabled and current is not None:
            await session.delete(current)
        else:
            return await _listed(session)
        session.add(
            AuditLog(
                tenant_id=None,
                actor=actor,
                action=ENABLED_ACTION if body.enabled else DISABLED_ACTION,
                target=f"country:{country}",
                after_json={"country": country, "reason": body.reason},
            )
        )
        await session.flush()
        return await _listed(session)


async def _listed(session: AsyncSession) -> list[CountryOut]:
    rows = (
        await session.scalars(
            sa.select(WhatsappLoginBetaCountry).order_by(WhatsappLoginBetaCountry.country)
        )
    ).all()
    return [
        CountryOut(country=r.country, enabled_at=r.enabled_at, enabled_by=r.enabled_by)
        for r in rows
    ]


__all__ = ["EU_EEA", "router"]
