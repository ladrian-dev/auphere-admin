import uuid

import pytest

from nexus_api.db.models import Tenant, TenantPlan
from nexus_api.repositories import TenantRepository

pytestmark = pytest.mark.asyncio


async def test_list_tenants_returns_all(db_session, seed_tenants):
    repo = TenantRepository(db_session)
    items = await repo.list_all()
    slugs = {t.slug for t in items}
    assert {"tenant-a", "tenant-b"} <= slugs


async def test_get_tenant_by_id(db_session, seed_tenants):
    repo = TenantRepository(db_session)
    t = await repo.get(seed_tenants["a"])
    assert t is not None
    assert t.slug == "tenant-a"


async def test_get_tenant_returns_none_for_unknown(db_session):
    repo = TenantRepository(db_session)
    assert await repo.get(uuid.uuid4()) is None


async def test_get_tenant_by_slug(db_session, seed_tenants):
    repo = TenantRepository(db_session)
    t = await repo.get_by_slug("tenant-a")
    assert t is not None
    assert t.id == seed_tenants["a"]


async def test_get_tenant_by_slug_unknown(db_session):
    repo = TenantRepository(db_session)
    assert await repo.get_by_slug("does-not-exist") is None


async def test_create_tenant(db_session):
    repo = TenantRepository(db_session)
    t = Tenant(name="New", slug="new-co", plan=TenantPlan.PRO)
    async with db_session.begin():
        created = await repo.create(t)
    assert created.id is not None
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.name == "New"
