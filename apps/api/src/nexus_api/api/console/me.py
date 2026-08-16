"""``GET /console/me`` — who am I, in which partner, with what permissions.

The console frontend renders navigation and actions from THIS list; it
never keeps its own copy of the role→permission map.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.services.partner_clients import quota_state

from .schemas import MeOut, PartnerBrief, QuotaOut

router = APIRouter()


async def quota_out(session: AsyncSession, principal: ConsolePrincipal) -> QuotaOut:
    async with session.begin():
        state = await quota_state(session, principal.partner)
    return QuotaOut(
        max_clients=state.limit,
        used_clients=state.used,
        remaining_clients=state.remaining,
        max_channels_per_client=principal.partner.max_channels_per_client,
    )


@router.get("/me", response_model=MeOut)
async def me(
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
) -> MeOut:
    return MeOut(
        user_id=principal.user_id,
        email=principal.membership.email,
        display_name=principal.membership.display_name,
        role=principal.role,
        permissions=sorted(principal.permissions),
        membership_id=principal.membership.id,
        partner=PartnerBrief(
            slug=principal.partner.slug,
            name=principal.partner.name,
            status=principal.partner.status,
        ),
        quota=await quota_out(session, principal),
    )
