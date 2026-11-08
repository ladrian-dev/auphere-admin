"""La 0223 añade ``booking_unbacked`` a los motivos de espera (spec 056, requisito 1.2).

Cuando el agente da por hecha una cita que no existe y el freno lo pasa a una
persona, la conversación espera con ese motivo. El CHECK lo acepta y sigue
rechazando un código inventado. El motivo **no** es de puerta: la siguiente
respuesta del agente no lo libera.

La bajada devuelve esas conversaciones como ``escalated``, que tampoco libera la
siguiente respuesta. Corre en su propio proceso de Alembic y deja la base en
head pase lo que pase.
"""

from __future__ import annotations

import re
import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from nexus_api.db.models.conversation import WAITING_REASONS
from nexus_api.services.inbox_lifecycle import GATE_REASONS
from tests.conftest import _TRUNCATE_TABLES, TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0222_merge_0220_heads"


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


async def _conversation() -> uuid.UUID:
    tid, ch, cu, cid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'T', :s, 'pro', 'active')",
        i=tid,
        s=f"m223-{tid.hex[:10]}",
    )
    await _exec(
        "INSERT INTO channels (id, tenant_id, type, provider, provider_identifier, config, status) "
        "VALUES (:i, :t, 'whatsapp', 'meta', :p, '{}'::jsonb, 'active')",
        i=ch,
        t=tid,
        p=f"wa-{ch.hex[:8]}",
    )
    await _exec(
        "INSERT INTO customers (id, tenant_id, identifier, preferences) "
        "VALUES (:i, :t, :n, '{}'::jsonb)",
        i=cu,
        t=tid,
        n=f"569{cu.int % 10**8:08d}",
    )
    await _exec(
        "INSERT INTO conversations (id, tenant_id, channel_id, customer_id, status) "
        "VALUES (:i, :t, :ch, :cu, 'open')",
        i=cid,
        t=tid,
        ch=ch,
        cu=cu,
    )
    return cid


async def _set_reason(cid: uuid.UUID, reason: str) -> None:
    await _exec("UPDATE conversations SET waiting_reason = :r WHERE id = :i", r=reason, i=cid)


async def _reason(cid: uuid.UUID) -> str | None:
    (row,) = await _exec("SELECT waiting_reason FROM conversations WHERE id = :i", i=cid)
    return row[0]


async def _check_codes() -> set[str]:
    (row,) = await _exec(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_conversations_waiting_reason'"
    )
    return set(re.findall(r"'([a-z_]+)'::", row[0]))


async def test_the_check_takes_booking_unbacked_and_refuses_an_invented_one(
    at_head_afterwards: Any,
) -> None:
    cid = await _conversation()
    await _set_reason(cid, "booking_unbacked")
    assert await _reason(cid) == "booking_unbacked"
    with pytest.raises(IntegrityError, match="ck_conversations_waiting_reason"):
        await _set_reason(cid, "booking_maybe")


async def test_the_check_and_the_model_say_the_same_list(at_head_afterwards: Any) -> None:
    assert "booking_unbacked" in WAITING_REASONS
    assert await _check_codes() == set(WAITING_REASONS)


async def test_the_next_agent_reply_does_not_release_it() -> None:
    assert "booking_unbacked" not in GATE_REASONS


async def test_downgrade_hands_it_back_as_escalated(at_head_afterwards: Any) -> None:
    cid = await _conversation()
    await _set_reason(cid, "booking_unbacked")

    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    assert await _reason(cid) == "escalated"
    assert "booking_unbacked" not in await _check_codes()
    with pytest.raises(IntegrityError, match="ck_conversations_waiting_reason"):
        await _set_reason(cid, "booking_unbacked")

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    await _set_reason(cid, "booking_unbacked")
    assert await _reason(cid) == "booking_unbacked"
