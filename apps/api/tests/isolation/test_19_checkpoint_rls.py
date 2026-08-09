"""Garantía 4 cerrada (WP-14b): RLS en las tablas de checkpoint.

0065 puso la INTEGRIDAD (tenant_id derivado y validado por trigger); 0066
pone el AISLAMIENTO: ENABLE + FORCE RLS con policy por tenant (GUC
``app.tenant_id``) + policy de mantenimiento (GUC ``app.rls_maintenance``,
solo barridos del scheduler). El ``TenantScopedPostgresSaver`` del worker
activa la primera en cada operación (set_config + SET ROLE nexus_app).

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio

# Reutiliza la creación de tablas + hardening de test_18.
from .test_18_checkpoint_tenant_column import _checkpoint_tables  # noqa: E402,F401


def _thread(tenant_id: uuid.UUID) -> str:
    return f"tenant:{tenant_id}:channel:{uuid.uuid4()}:user:56900000001"


async def _seed_checkpoint(session, tenant_id: uuid.UUID) -> str:
    """Insert one checkpoint for the tenant, GUC-scoped like the wrapper."""
    thread = _thread(tenant_id)
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, false)"),
        {"t": str(tenant_id)},
    )
    await session.execute(
        sa.text(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
            "VALUES (:tid, '', :cid, CAST(:c AS jsonb), '{}')"
        ),
        {"tid": thread, "cid": str(uuid.uuid4()), "c": json.dumps({"v": 1})},
    )
    await session.execute(sa.text("SELECT set_config('app.tenant_id', '', false)"))
    return thread


async def _as_app_role(session, tenant_id: uuid.UUID | None) -> None:
    """Adopt the exact posture of the TenantScopedPostgresSaver."""
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, false)"),
        {"t": "" if tenant_id is None else str(tenant_id)},
    )
    await session.execute(sa.text("SET ROLE nexus_app"))


async def test_saver_posture_sees_only_its_tenant(db_session) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        thread_a = await _seed_checkpoint(session, a)
        await _seed_checkpoint(session, b)
        await session.commit()

    async with sm() as session:
        await _as_app_role(session, a)
        rows = (
            await session.execute(
                sa.text("SELECT thread_id, tenant_id FROM checkpoints WHERE tenant_id IN (:a, :b)"),
                {"a": str(a), "b": str(b)},
            )
        ).all()
        assert [r[0] for r in rows] == [thread_a]
        assert all(r[1] == a for r in rows)


async def test_unscoped_session_sees_nothing(db_session) -> None:
    a = uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_checkpoint(session, a)
        await session.commit()

    async with sm() as session:
        await _as_app_role(session, None)  # sin GUC: fail-closed
        visible = await session.scalar(
            sa.text("SELECT count(*) FROM checkpoints WHERE tenant_id = :a"),
            {"a": str(a)},
        )
        assert visible == 0


async def test_cross_tenant_write_is_rejected(db_session) -> None:
    """Scoped al tenant A, un INSERT de un thread de B viola el WITH CHECK
    (el trigger deriva tenant_id=B del prefijo; la policy exige =A)."""
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _as_app_role(session, a)
        with pytest.raises(Exception, match=r"row-level security|violates"):
            await session.execute(
                sa.text(
                    "INSERT INTO checkpoints "
                    "(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
                    "VALUES (:tid, '', :cid, '{}', '{}')"
                ),
                {"tid": _thread(b), "cid": str(uuid.uuid4())},
            )


async def test_maintenance_guc_sees_all_tenants(db_session) -> None:
    """El camino del checkpoint_retention_cron: barrido global explícito."""
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_checkpoint(session, a)
        await _seed_checkpoint(session, b)
        await session.commit()

    async with sm() as session:
        await session.execute(sa.text("SELECT set_config('app.rls_maintenance', 'on', false)"))
        visible = await session.scalar(
            sa.text("SELECT count(*) FROM checkpoints WHERE tenant_id IN (:a, :b)"),
            {"a": str(a), "b": str(b)},
        )
        assert visible == 2


async def test_wrapper_rejects_unprefixed_thread_id() -> None:
    """El wrapper del worker corta ANTES de tocar SQL si el thread_id no
    lleva el prefijo tenant:<uuid>: — mismo contrato que el trigger."""
    from nexus_worker.runtime.checkpointer import tenant_from_thread_config

    tenant = uuid.uuid4()
    ok = tenant_from_thread_config(
        {"configurable": {"thread_id": f"tenant:{tenant}:channel:x:user:1"}}
    )
    assert ok == str(tenant)

    for evil in ("global", f"TENANT:{tenant}:x", "", None):
        with pytest.raises(ValueError, match="sin prefijo"):
            tenant_from_thread_config({"configurable": {"thread_id": evil}})
