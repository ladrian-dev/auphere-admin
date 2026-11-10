"""Spec 050, requirement 2 — who the person is, with or without a phone.

The rules of ``upsert_customer`` (data-model.md): by BSUID, then by phone
(attaching the BSUID Meta gave alongside), then by the legacy identifier,
else a new row. ``identifier`` is never rewritten, and two existing rows
are never merged.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from nexus_worker.persistence.messages import upsert_customer
from sqlalchemy import func, select

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Customer, Tenant, TenantPlan, TenantStatus

pytestmark = pytest.mark.asyncio

PHONE = "34611000001"
BSUID = "ES.100000000000000001"


@pytest_asyncio.fixture
async def tenant(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Id",
            slug=f"id-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            owner_phone="+56999990011",
        )
    )
    await db_session.commit()
    return tid


async def _upsert(tid: uuid.UUID, **kw) -> Customer:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tid):
        c = await upsert_customer(s, **kw)
        return c


async def _count(tid: uuid.UUID) -> int:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tid):
        return int(await s.scalar(select(func.count()).select_from(Customer)) or 0)


async def test_today_a_phone_only_person_is_unchanged(tenant):
    c = await _upsert(tenant, identifier=PHONE, phone=PHONE)
    again = await _upsert(tenant, identifier=PHONE)
    assert again.id == c.id
    assert again.identifier == PHONE


async def test_a_bsuid_only_person_is_created_keyed_by_bsuid(tenant):
    c = await _upsert(tenant, identifier=BSUID, bsuid=BSUID, username="@ana")
    assert c.identifier == BSUID and c.bsuid == BSUID and c.phone is None and c.username == "@ana"
    again = await _upsert(tenant, identifier=BSUID, bsuid=BSUID)
    assert again.id == c.id


async def test_an_existing_phone_person_gets_the_bsuid_attached(tenant):
    legacy = await _upsert(tenant, identifier=PHONE)  # a row from before the BSUID existed
    linked = await _upsert(tenant, identifier=PHONE, phone=PHONE, bsuid=BSUID)
    assert linked.id == legacy.id
    assert linked.bsuid == BSUID
    assert linked.identifier == PHONE  # never rewritten
    # Later, the same person writes with only the BSUID: same row, same thread key.
    later = await _upsert(tenant, identifier=BSUID, bsuid=BSUID)
    assert later.id == legacy.id and later.identifier == PHONE
    assert await _count(tenant) == 1


async def test_two_people_are_never_merged(tenant):
    by_phone = await _upsert(tenant, identifier=PHONE, phone=PHONE)
    by_bsuid = await _upsert(tenant, identifier="ES.999", bsuid="ES.999")
    # Meta now says the BSUID-only row has that phone: the BSUID's row wins,
    # the phone row is not touched and nothing is merged.
    result = await _upsert(tenant, identifier=PHONE, phone=PHONE, bsuid="ES.999")
    assert result.id == by_bsuid.id
    assert result.phone is None  # the phone stays with the person who has it
    assert await _count(tenant) == 2
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant):
        untouched = await s.get(Customer, by_phone.id)
        assert untouched is not None and untouched.bsuid is None
