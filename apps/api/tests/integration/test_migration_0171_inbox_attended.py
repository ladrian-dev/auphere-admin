"""Spec 045 — la migración 0171 rellena lo atendido desde los mensajes.

Baja a 0170, siembra cuatro conversaciones y vuelve a subir:

- con entrantes atendidos → ``attended_at`` = el primero, ``last_attended_inbound_at`` = el último;
- solo con entrantes silenciados (``not_admin``) → sin ``attended_at``;
- solo con un saliente del sistema → sin ``attended_at``;
- en un número solo de envío → sin ``attended_at``.

Repetirla no cambia nada. Corre en su propio proceso de Alembic y deja la base
en head pase lo que pase.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0170_canonical_business_hours"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


@pytest.fixture
def at_head_afterwards() -> Any:
    yield
    _alembic("upgrade", "head")


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _world(send_only: bool = False) -> tuple[uuid.UUID, uuid.UUID]:
    tid, ch, cu = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'T', :s, 'pro', 'active')",
        i=tid,
        s=f"att-{tid.hex[:10]}",
    )
    await _exec(
        "INSERT INTO channels (id, tenant_id, type, provider, provider_identifier, config, status) "
        "VALUES (:i, :t, 'whatsapp', 'meta', :p, CAST(:c AS jsonb), 'active')",
        i=ch,
        t=tid,
        p=f"wa-{ch.hex[:8]}",
        c='{"agent_enabled": false}' if send_only else "{}",
    )
    await _exec(
        "INSERT INTO customers (id, tenant_id, identifier, preferences) "
        "VALUES (:i, :t, :n, '{}'::jsonb)",
        i=cu,
        t=tid,
        n=f"569{cu.int % 10**8:08d}",
    )
    return tid, await _conversation(tid, ch, cu)


async def _conversation(tid: uuid.UUID, ch: uuid.UUID, cu: uuid.UUID) -> uuid.UUID:
    cid = uuid.uuid4()
    await _exec(
        "INSERT INTO conversations (id, tenant_id, channel_id, customer_id, status) "
        "VALUES (:i, :t, :ch, :cu, 'open')",
        i=cid,
        t=tid,
        ch=ch,
        cu=cu,
    )
    return cid


async def _message(
    tid: uuid.UUID, cid: uuid.UUID, direction: str, minutes_ago: int, skipped: str | None = None
) -> None:
    await _exec(
        "INSERT INTO messages (id, tenant_id, conversation_id, direction, status, content, "
        "tool_calls, attempts, skipped_reason, created_at) VALUES (:i, :t, :c, "
        "CAST(:d AS message_direction), 'sent', 'x', '[]'::jsonb, 0, :s, "
        "now() - make_interval(mins => :m))",
        i=uuid.uuid4(),
        t=tid,
        c=cid,
        d=direction,
        s=skipped,
        m=minutes_ago,
    )


async def _attended(cid: uuid.UUID) -> tuple[Any, Any]:
    rows = await _exec(
        "SELECT attended_at, last_attended_inbound_at FROM conversations WHERE id = :i", i=cid
    )
    return rows[0][0], rows[0][1]


async def test_0171_backfills_only_what_the_agent_attended(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    tid, attended = await _world()
    await _message(tid, attended, "inbound", 50, skipped="not_admin")  # antes de estar permitido
    await _message(tid, attended, "inbound", 40)
    await _message(tid, attended, "outbound", 39)
    await _message(tid, attended, "inbound", 10)

    tid2, silenced = await _world()
    await _message(tid2, silenced, "inbound", 30, skipped="not_admin")

    tid3, system_only = await _world()
    await _message(tid3, system_only, "outbound", 30)

    tid4, send_only = await _world(send_only=True)
    await _message(tid4, send_only, "inbound", 30)

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    first, last = await _attended(attended)
    assert first is not None and last is not None
    assert first < last
    rows = await _exec(
        "SELECT MIN(created_at), MAX(created_at) FROM messages "
        "WHERE conversation_id = :c AND direction = 'inbound' AND skipped_reason IS NULL",
        c=attended,
    )
    assert (first, last) == (rows[0][0], rows[0][1])

    assert await _attended(silenced) == (None, None)
    assert await _attended(system_only) == (None, None)
    assert await _attended(send_only) == (None, None)

    # Idempotente: bajar y subir otra vez deja lo mismo.
    assert _alembic("downgrade", _BEFORE).returncode == 0
    assert _alembic("upgrade", "head").returncode == 0
    assert await _attended(attended) == (first, last)
