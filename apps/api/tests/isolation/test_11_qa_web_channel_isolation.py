"""Garantía 8 (ADR-020) — the QA Playground ``web`` channel is per-tenant.

The QA Playground chat is a first-class ``web`` channel that
``_ensure_qa_channel`` get-or-creates lazily on the first QA run, instead
of borrowing the tenant's WhatsApp channel (bug #7). This test pins the
isolation properties of that helper:

  1. Each tenant gets its OWN ``web`` / ``qa_playground`` channel — the
     helper never returns another tenant's channel.
  2. The helper is idempotent: a second call for the same tenant returns
     the same row, never a duplicate.
  3. RLS on ``channels`` hides tenant A's QA channel from tenant B.
  4. A session scoped to tenant A cannot forge a QA channel for tenant B —
     the policy's WITH CHECK clause rejects it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from nexus_api.api.qa import _ensure_qa_channel
from nexus_api.db.models import Channel, ChannelType

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_qa_web_channel_is_per_tenant(db_session, tenants_ab):
    tenant_a = tenants_ab["a"]
    tenant_b = tenants_ab["b"]

    async with db_session.begin():
        await set_tenant(db_session, tenant_a)
        ch_a = await _ensure_qa_channel(db_session, tenant_a)
        assert ch_a.tenant_id == tenant_a
        assert ch_a.type == ChannelType.WEB
        assert ch_a.provider == "qa_playground"
        ch_a_id = ch_a.id

    async with db_session.begin():
        await set_tenant(db_session, tenant_b)
        ch_b = await _ensure_qa_channel(db_session, tenant_b)
        assert ch_b.tenant_id == tenant_b
        ch_b_id = ch_b.id
        assert ch_b_id != ch_a_id

    # Tenant A sees only its own QA web channel; tenant B's is hidden by RLS.
    async with db_session.begin():
        await set_tenant(db_session, tenant_a)
        rows = (
            (await db_session.execute(select(Channel).where(Channel.type == ChannelType.WEB)))
            .scalars()
            .all()
        )
        assert [c.id for c in rows] == [ch_a_id]


async def test_qa_web_channel_get_or_create_is_idempotent(db_session, tenants_ab):
    tenant = tenants_ab["a"]

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        first = await _ensure_qa_channel(db_session, tenant)
        first_id = first.id

    async with db_session.begin():
        await set_tenant(db_session, tenant)
        second = await _ensure_qa_channel(db_session, tenant)
        assert second.id == first_id

    # Exactly one QA web channel exists for the tenant — no duplicate.
    async with db_session.begin():
        await set_tenant(db_session, tenant)
        rows = (
            (await db_session.execute(select(Channel).where(Channel.type == ChannelType.WEB)))
            .scalars()
            .all()
        )
        assert len(rows) == 1


async def test_qa_web_channel_cross_tenant_insert_rejected(db_session, tenants_ab):
    """A session scoped to tenant A cannot mint a QA channel for tenant B."""
    from sqlalchemy.exc import IntegrityError, ProgrammingError

    tenant_a = tenants_ab["a"]
    tenant_b = tenants_ab["b"]

    async with db_session.begin():
        await set_tenant(db_session, tenant_a)
        db_session.add(
            Channel(
                tenant_id=tenant_b,
                type=ChannelType.WEB,
                provider="qa_playground",
                provider_identifier=f"qa_playground:{tenant_b}",
            )
        )
        with pytest.raises((IntegrityError, ProgrammingError)):
            await db_session.flush()
