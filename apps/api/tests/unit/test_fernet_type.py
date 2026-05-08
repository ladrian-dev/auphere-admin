import pytest

from nexus_api.db.types import FernetEncrypted


@pytest.mark.asyncio
async def test_fernet_round_trip(db_session, seed_tenants):
    from nexus_api.db.models import TenantCredentials

    tid = seed_tenants["a"]
    cred = TenantCredentials(
        tenant_id=tid,
        integration="agendapro",
        encrypted_payload=b"super-secret-token",
    )
    # Setting tenant_id manually via SET LOCAL because the per-test session
    # is not auto-scoped.
    from sqlalchemy import text

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(cred)
        await db_session.flush()
        loaded = await db_session.get(TenantCredentials, cred.id)
        assert loaded is not None
        assert loaded.encrypted_payload == b"super-secret-token"


@pytest.mark.asyncio
async def test_fernet_str_input_roundtrips_to_bytes(db_session, seed_tenants):
    """Strings get encoded to bytes by the type adapter on read.

    SQLAlchemy keeps the assigned Python value in memory until expiration, so
    we must expire & re-fetch to verify the type adapter round-trip.
    """
    from sqlalchemy import text

    from nexus_api.db.models import TenantCredentials

    tid = seed_tenants["a"]
    cred = TenantCredentials(
        tenant_id=tid,
        integration="ycloud",
        encrypted_payload="hello-world",  # str, not bytes
    )
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(cred)
        await db_session.flush()
        cred_id = cred.id
    db_session.expire_all()
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tid)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        loaded = await db_session.get(TenantCredentials, cred_id)
        assert loaded is not None
        assert loaded.encrypted_payload == b"hello-world"


def test_fernet_type_python_type():
    assert FernetEncrypted().python_type is bytes


def test_fernet_type_rejects_non_bytes_non_str():
    t = FernetEncrypted()
    with pytest.raises(TypeError):
        t.process_bind_param(12345, None)
