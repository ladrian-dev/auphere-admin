"""``GET /console/onboarding`` — the partner's getting-started checklist
(CP-29), DERIVED from the data every time (no checklist table, nothing to
drift): invite the team, create the first client, publish an agent,
connect a channel, get the first conversation.

Plus the activation metric: ``time_to_first_active_client_seconds`` =
``partners.activated_at - partners.created_at`` (``activated_at`` is
stamped by ``services/console_notifications.record_client_activation``
the first time a client goes ACTIVE with a published agent).

Dismissal of the home card is a client-side preference (localStorage,
``nexus.console.onboarding.dismissed``) — it is per person and per
browser, not partner data, so it does not belong in the API.

Per-tenant facts (agent, channel, conversations) live under RLS: they are
read tenant by tenant in short scoped transactions, the same pattern as
``usage.py``. N = the partner's client count (bounded by the quota).
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    Conversation,
    InvitationStatus,
    MembershipStatus,
    Partner,
    PartnerApiKey,
    PartnerInvitation,
    PartnerMembership,
    PartnerTenant,
    Tenant,
    TenantStatus,
)

from .schemas_onboarding import OnboardingOut, OnboardingStepOut

router = APIRouter(prefix="/onboarding")


@router.get("", response_model=OnboardingOut)
async def onboarding(
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
) -> OnboardingOut:
    partner_id = principal.partner.id
    async with session.begin():
        members = int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(PartnerMembership)
                .where(
                    PartnerMembership.partner_id == partner_id,
                    PartnerMembership.status == MembershipStatus.ACTIVE.value,
                )
            )
            or 0
        )
        invitations = int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(PartnerInvitation)
                .where(
                    PartnerInvitation.partner_id == partner_id,
                    PartnerInvitation.status.in_(
                        [InvitationStatus.PENDING.value, InvitationStatus.ACCEPTED.value]
                    ),
                )
            )
            or 0
        )
        mappings = (
            await session.execute(
                sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref)
                .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
                .where(
                    PartnerTenant.partner_id == partner_id,
                    Tenant.status != TenantStatus.ARCHIVED,
                )
                .order_by(Tenant.created_at)
            )
        ).all()
        live_keys = int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(PartnerApiKey)
                .where(PartnerApiKey.partner_id == partner_id, PartnerApiKey.revoked_at.is_(None))
            )
            or 0
        )
        # Re-read the partner row: ``activated_at`` may have been stamped
        # by another request since the principal resolved.
        partner_row = await session.get(Partner, partner_id)
    partner = partner_row or principal.partner

    agent_published = False
    channel_connected = live_keys > 0
    conversations = False
    first_ref: str | None = mappings[0][1] if mappings else None
    for tenant_id, _ref in mappings:
        if agent_published and channel_connected and conversations:
            break
        token = _current_tenant.set(tenant_id)
        try:
            async with session.begin():
                await apply_tenant_to_session(session, tenant_id)
                if not agent_published:
                    agent_published = (
                        await session.scalar(
                            sa.select(AgentConfig.id)
                            .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                            .limit(1)
                        )
                    ) is not None
                if not channel_connected:
                    channel_connected = (
                        await session.scalar(
                            sa.select(Channel.id)
                            .where(Channel.status == ChannelStatus.ACTIVE)
                            .limit(1)
                        )
                    ) is not None
                if not conversations:
                    conversations = (
                        await session.scalar(sa.select(Conversation.id).limit(1))
                    ) is not None
        finally:
            _current_tenant.reset(token)

    client_href = f"/clients/{first_ref}" if first_ref else "/clients/new"
    steps = [
        OnboardingStepOut(key="team", done=members >= 2 or invitations >= 1, href="/team"),
        OnboardingStepOut(key="first_client", done=bool(mappings), href="/clients/new"),
        OnboardingStepOut(
            key="agent_published",
            done=agent_published,
            href=f"{client_href}/agent" if first_ref else client_href,
        ),
        OnboardingStepOut(
            key="channel_connected",
            done=channel_connected,
            href=f"{client_href}/channels" if first_ref else client_href,
        ),
        OnboardingStepOut(
            key="first_conversation",
            done=conversations,
            href=f"{client_href}/conversations" if first_ref else client_href,
        ),
    ]
    done_count = sum(1 for s in steps if s.done)
    ttfa: int | None = None
    if partner.activated_at is not None:
        ttfa = max(int((partner.activated_at - partner.created_at).total_seconds()), 0)
    return OnboardingOut(
        steps=steps,
        done_count=done_count,
        total=len(steps),
        complete=done_count == len(steps),
        partner_created_at=partner.created_at,
        activated_at=partner.activated_at,
        time_to_first_active_client_seconds=ttfa,
    )


__all__ = ["router"]
