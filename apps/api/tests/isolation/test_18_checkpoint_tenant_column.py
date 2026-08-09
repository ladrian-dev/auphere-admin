"""Garantía 4 ampliada (WP-14): el aislamiento del estado conversacional ya
no depende SOLO del formato del ``thread_id``.

Las tablas de checkpoint llevan ``tenant_id`` real, derivado y validado por
un trigger de base de datos (migración 0065):

- un ``thread_id`` bien formado deriva su ``tenant_id`` automáticamente —
  incluso si el que escribe intenta poner un tenant_id DISTINTO, el trigger
  lo sobreescribe con el del prefijo (la columna nunca puede contradecir al
  thread);
- un ``thread_id`` sin el prefijo ``tenant:<uuid>:`` es RECHAZADO por
  Postgres, venga del código que venga.

Bloqueante como el resto de la suite de aislamiento.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _checkpoint_tables(db_session):
    """LangGraph creates these tables at worker boot; the test DB gets the
    same shape here, then applies the 0065 hardening exactly like the
    worker's checkpointer does after ``setup()``."""
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id text NOT NULL,
                    checkpoint_ns text NOT NULL DEFAULT '',
                    checkpoint_id text NOT NULL,
                    parent_checkpoint_id text,
                    type text,
                    checkpoint jsonb NOT NULL,
                    metadata jsonb NOT NULL DEFAULT '{}',
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
                """
            )
        )
        await session.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_blobs (
                    thread_id text NOT NULL,
                    checkpoint_ns text NOT NULL DEFAULT '',
                    channel text NOT NULL,
                    version text NOT NULL,
                    type text NOT NULL,
                    blob bytea,
                    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
                )
                """
            )
        )
        await session.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id text NOT NULL,
                    checkpoint_ns text NOT NULL DEFAULT '',
                    checkpoint_id text NOT NULL,
                    task_id text NOT NULL,
                    idx integer NOT NULL,
                    channel text NOT NULL,
                    type text,
                    blob bytea NOT NULL,
                    task_path text NOT NULL DEFAULT '',
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                )
                """
            )
        )
        # Same call the worker's checkpointer makes after setup().
        await session.execute(sa.text("SELECT harden_checkpoint_tables()"))
        await session.commit()
    yield


def _thread(tenant_id: uuid.UUID) -> str:
    return f"tenant:{tenant_id}:channel:{uuid.uuid4()}:user:56911112222"


async def _set_guc(session, tenant_id) -> None:
    """WP-14b: con RLS FORCE (0066) hasta el owner necesita el GUC para
    escribir — mismo contrato que aplica el TenantScopedPostgresSaver."""
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, false)"),
        {"t": str(tenant_id)},
    )


async def _insert_checkpoint(session, thread_id: str) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO checkpoints "
            "(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata) "
            "VALUES (:tid, '', :cid, CAST(:c AS jsonb), '{}')"
        ),
        {"tid": thread_id, "cid": str(uuid.uuid4()), "c": json.dumps({"v": 1})},
    )


async def test_tenant_id_derived_from_thread_prefix(db_session) -> None:
    tenant_id = uuid.uuid4()
    thread = _thread(tenant_id)
    sm = get_sessionmaker()
    async with sm() as session:
        await _set_guc(session, tenant_id)
        await _insert_checkpoint(session, thread)
        await session.commit()
        derived = await session.scalar(
            sa.text("SELECT tenant_id FROM checkpoints WHERE thread_id = :t"),
            {"t": thread},
        )
    assert derived == tenant_id


async def test_malformed_thread_id_is_rejected(db_session) -> None:
    sm = get_sessionmaker()
    for evil in ("global", "tenant:not-a-uuid:channel:x:user:y", ""):
        async with sm() as session:
            with pytest.raises(Exception, match="thread_id must start with tenant"):
                await _insert_checkpoint(session, evil)


async def test_forged_tenant_id_is_overwritten_by_trigger(db_session) -> None:
    """A writer that supplies a tenant_id contradicting the thread prefix
    does not win: the trigger derives from the prefix, always."""
    real_tenant = uuid.uuid4()
    forged_tenant = uuid.uuid4()
    thread = _thread(real_tenant)
    sm = get_sessionmaker()
    async with sm() as session:
        # GUC del tenant REAL: el WITH CHECK compara contra el tenant_id ya
        # corregido por el trigger, así que el forjado no cuela ni con RLS.
        await _set_guc(session, real_tenant)
        await session.execute(
            sa.text(
                "INSERT INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, checkpoint, metadata, tenant_id) "
                "VALUES (:tid, '', :cid, '{}', '{}', :forged)"
            ),
            {"tid": thread, "cid": str(uuid.uuid4()), "forged": str(forged_tenant)},
        )
        await session.commit()
        stored = await session.scalar(
            sa.text("SELECT tenant_id FROM checkpoints WHERE thread_id = :t"),
            {"t": thread},
        )
    assert stored == real_tenant
    assert stored != forged_tenant


async def test_writes_and_blobs_also_guarded(db_session) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        with pytest.raises(Exception, match="thread_id must start with tenant"):
            await session.execute(
                sa.text(
                    "INSERT INTO checkpoint_writes "
                    "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, "
                    " channel, blob, task_path) "
                    "VALUES ('evil', '', 'c', 't', 0, 'ch', :b, '')"
                ),
                {"b": b"x"},
            )
    async with sm() as session:
        with pytest.raises(Exception, match="thread_id must start with tenant"):
            await session.execute(
                sa.text(
                    "INSERT INTO checkpoint_blobs "
                    "(thread_id, checkpoint_ns, channel, version, type, blob) "
                    "VALUES ('evil', '', 'ch', '1', 'json', :b)"
                ),
                {"b": b"x"},
            )
