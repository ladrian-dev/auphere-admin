"""La 0227 marca como atendido el aviso «Espera a una persona» (spec 056, requisito 8.1).

``console_notifications.handled_at``: cuando alguien toma, devuelve, resuelve o
libera la conversación, su aviso ``inbox.waiting`` deja de contar en la campana
y sigue en la lista. El índice parcial encuentra los pendientes de una
conversación sin recorrer los de todo el partner.

La bajada quita la columna y el índice. Deja la base en head pase lo que pase.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from nexus_api.db.models.console_notification import ConsoleNotification
from tests.conftest import _TRUNCATE_TABLES, TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0226_correction_batches"
_INDEX = "ix_console_notifications_waiting_pending"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    _alembic("upgrade", "head")
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


async def _notice(partner_id: uuid.UUID, conversation_id: uuid.UUID) -> uuid.UUID:
    nid = uuid.uuid4()
    await _exec(
        "INSERT INTO console_notifications (id, partner_id, external_client_ref, kind, payload, "
        "audience) VALUES (:i, :p, 'cliente-1', 'inbox.waiting', CAST(:j AS jsonb), 'client')",
        i=nid,
        p=partner_id,
        j=json.dumps({"conversation_id": str(conversation_id), "contact": "Ana"}),
    )
    return nid


async def test_a_waiting_notice_starts_pending_and_can_be_handled(
    at_head_afterwards: Any,
) -> None:
    pid = uuid.uuid4()
    await _exec(
        "INSERT INTO partners (id, name, slug, status) VALUES (:i, 'P', :s, 'active')",
        i=pid,
        s=f"m227-{pid.hex[:10]}",
    )
    conversation = uuid.uuid4()
    first = await _notice(pid, conversation)
    (row,) = await _exec("SELECT handled_at FROM console_notifications WHERE id = :i", i=first)
    assert row[0] is None

    await _exec(
        "UPDATE console_notifications SET handled_at = now() "
        "WHERE partner_id = :p AND external_client_ref = 'cliente-1' AND kind = 'inbox.waiting' "
        "AND handled_at IS NULL AND payload->>'conversation_id' = :c",
        p=pid,
        c=str(conversation),
    )
    # Un escalado nuevo de la misma conversación es un aviso nuevo, pendiente.
    second = await _notice(pid, conversation)
    rows = await _exec(
        "SELECT id, handled_at IS NOT NULL FROM console_notifications WHERE partner_id = :p",
        p=pid,
    )
    assert dict(rows) == {first: True, second: False}


async def test_the_index_holds_only_pending_waiting_notices(at_head_afterwards: Any) -> None:
    (row,) = await _exec("SELECT indexdef FROM pg_indexes WHERE indexname = :n", n=_INDEX)
    assert "((payload ->> 'conversation_id'::text))" in row[0]
    assert "'inbox.waiting'::text" in row[0] and "handled_at IS NULL" in row[0]
    column = ConsoleNotification.__table__.c.handled_at
    assert column.nullable and isinstance(column.type, sa.DateTime) and column.type.timezone


async def test_downgrade_drops_the_column_and_the_index(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert not await _exec(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'console_notifications' AND column_name = 'handled_at'"
    )
    assert not await _exec("SELECT 1 FROM pg_indexes WHERE indexname = :n", n=_INDEX)
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
