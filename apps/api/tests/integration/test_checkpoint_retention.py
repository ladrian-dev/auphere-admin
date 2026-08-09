"""WP-13: checkpoint retention against the real schema.

Seeds raw LangGraph checkpoint rows (the tables have no FKs into the app
schema) and pins the two prunes: per-thread trim keeps exactly the newest N,
and dead threads are purged entirely — writes → blobs → checkpoints — while
live threads keep their blobs.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from nexus_worker.streams.checkpoint_retention_cron import prune_once
from nexus_worker.streams.partition_maintenance_cron import ensure_partitions_once

from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _checkpoint_tables(db_session):
    """The public checkpoint tables are created by ``AsyncPostgresSaver.
    setup()`` at worker boot, not by Alembic — the test DB doesn't have
    them. Create the same shape (columns verified against the dev DB)."""
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
        await session.commit()
    yield


def _ckpt_id(seq: int) -> str:
    # Sortable ids, same property LangGraph's UUIDv6-style ids have.
    return f"1ef00000-0000-6000-8000-{seq:012d}"


async def _seed_thread(session, thread_id: str, *, n_checkpoints: int, ts: datetime) -> None:
    for seq in range(n_checkpoints):
        await session.execute(
            sa.text(
                "INSERT INTO checkpoints "
                "(thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
                " type, checkpoint, metadata) "
                "VALUES (:tid, '', :cid, NULL, NULL, CAST(:ckpt AS jsonb), '{}')"
            ),
            {
                "tid": thread_id,
                "cid": _ckpt_id(seq),
                "ckpt": json.dumps({"ts": ts.isoformat(), "v": 1}),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO checkpoint_writes "
                "(thread_id, checkpoint_ns, checkpoint_id, task_id, idx, "
                " channel, type, blob, task_path) "
                "VALUES (:tid, '', :cid, 't1', 0, 'ch', 'json', :blob, '')"
            ),
            {"tid": thread_id, "cid": _ckpt_id(seq), "blob": b"x"},
        )
    await session.execute(
        sa.text(
            "INSERT INTO checkpoint_blobs "
            "(thread_id, checkpoint_ns, channel, version, type, blob) "
            "VALUES (:tid, '', 'state', '1', 'json', :blob)"
        ),
        {"tid": thread_id, "blob": b"y"},
    )


async def _counts(session, thread_id: str) -> tuple[int, int, int]:
    c = await session.scalar(
        sa.text("SELECT count(*) FROM checkpoints WHERE thread_id = :t"), {"t": thread_id}
    )
    w = await session.scalar(
        sa.text("SELECT count(*) FROM checkpoint_writes WHERE thread_id = :t"),
        {"t": thread_id},
    )
    b = await session.scalar(
        sa.text("SELECT count(*) FROM checkpoint_blobs WHERE thread_id = :t"),
        {"t": thread_id},
    )
    return int(c), int(w), int(b)


async def test_trim_keeps_newest_and_purges_dead_threads(db_session) -> None:
    live = f"tenant:{uuid.uuid4()}:channel:{uuid.uuid4()}:user:live"
    dead = f"tenant:{uuid.uuid4()}:channel:{uuid.uuid4()}:user:dead"
    now = datetime.now(UTC)

    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_thread(session, live, n_checkpoints=30, ts=now)
        await _seed_thread(session, dead, n_checkpoints=5, ts=now - timedelta(days=120))
        await session.commit()

    stats = await prune_once(keep=20, max_age_days=90, batch_rows=7, pause_s=0.0)

    async with sm() as session:
        live_c, _live_w, live_b = await _counts(session, live)
        dead_c, dead_w, dead_b = await _counts(session, dead)
        # Trim: exactly the newest 20 survive, and the survivors are the
        # HIGHEST checkpoint ids.
        assert (live_c, live_b) == (20, 1)
        oldest_kept = await session.scalar(
            sa.text("SELECT min(checkpoint_id) FROM checkpoints WHERE thread_id = :t"),
            {"t": live},
        )
        assert oldest_kept == _ckpt_id(10)
        # Dead thread: gone entirely, blobs included.
        assert (dead_c, dead_w, dead_b) == (0, 0, 0)

    assert stats["trimmed_checkpoints"] == 10 + 0  # 30-20 from live; dead counted apart
    assert stats["purged_threads"] == 1

    # Idempotent: a second pass finds nothing.
    stats2 = await prune_once(keep=20, max_age_days=90, batch_rows=7, pause_s=0.0)
    assert stats2 == {"trimmed_checkpoints": 0, "purged_threads": 0}


async def test_partition_maintenance_creates_current_and_next(db_session) -> None:
    from nexus_worker.streams.partition_maintenance_cron import PARTITIONED_TABLES

    ensured = await ensure_partitions_once()
    # Mes corriente + siguiente, por cada tabla particionada. usage_records
    # (WP-16) entra aquí: una tabla de facturación que se quede sin
    # partición al cambiar de mes cae en la DEFAULT y deja de podarse por
    # DROP PARTITION, que es la razón de particionarla.
    assert len(ensured) == 2 * len(PARTITIONED_TABLES)
    assert any(name.startswith("usage_records_") for name in ensured)

    sm = get_sessionmaker()
    async with sm() as session:
        for name in ensured:
            exists = await session.scalar(
                sa.text("SELECT count(*) FROM pg_class WHERE relname = :n"), {"n": name}
            )
            assert exists == 1
