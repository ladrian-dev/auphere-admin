"""La 0226 junta en un lote las correcciones de «Todo el negocio» (spec 056, requisito 9.1).

``inbox_corrections.batch_id`` apunta a la cabeza del lote, que es la corrección
que envió la persona del cliente (``batch_id = id``). La FK es **compuesta**,
``(tenant_id, batch_id)``: la comprobación de una FK no pasa por la RLS, así que
una de una sola columna dejaría a un cliente colgar su corrección del lote de
otro ([[fk-no-pasa-por-rls]]).

- la cabeza se apunta a sí misma y una hermana a la cabeza, en el mismo cliente;
- un ``batch_id`` de otro cliente viola la FK;
- borrar la cabeza deja a las hermanas sin lote, no las borra;
- la bajada quita la columna, su FK y su índice. Deja la base en head pase lo que pase.
"""

from __future__ import annotations

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

from nexus_api.db.models.inbox_correction import InboxCorrection
from tests.conftest import _TRUNCATE_TABLES, TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0225_client_access_audit_actor"


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


async def _client() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Un cliente con una conversación y dos agentes."""
    tid, ch, cu, cid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'T', :s, 'pro', 'active')",
        i=tid,
        s=f"m226-{tid.hex[:10]}",
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
    agents = []
    for n in range(2):
        aid = uuid.uuid4()
        await _exec(
            "INSERT INTO agents (id, tenant_id, name, status, lifecycle, is_default) "
            "VALUES (:a, :t, :n, 'active', 'published', :d)",
            a=aid,
            t=tid,
            n=f"Agente {n}",
            d=n == 0,
        )
        agents.append(aid)
    return tid, cid, agents[0], agents[1]


async def _correction(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    batch: uuid.UUID | None = None,
    head: bool = False,
) -> uuid.UUID:
    """``head``: la cabeza del lote, que se apunta a sí misma."""
    cid = uuid.uuid4()
    await _exec(
        "INSERT INTO inbox_corrections (id, tenant_id, conversation_id, message_id, agent_id, "
        "author_client_user_id, origin, scope, kind, lesson, status, batch_id) VALUES "
        "(:i, :t, :c, :m, :a, 'user-1', 'lite_web', 'business', 'behavior', "
        "'Los domingos no abrimos', 'proposed', :b)",
        i=cid,
        t=tenant_id,
        c=conversation_id,
        m=uuid.uuid4(),
        a=agent_id,
        b=cid if head else batch,
    )
    return cid


async def _batch_of(correction_id: uuid.UUID) -> uuid.UUID | None:
    (row,) = await _exec("SELECT batch_id FROM inbox_corrections WHERE id = :i", i=correction_id)
    return row[0]


async def test_a_batch_lives_inside_one_client(at_head_afterwards: Any) -> None:
    tenant, conversation, first, second = await _client()
    head = await _correction(tenant, conversation, first, head=True)
    sister = await _correction(tenant, conversation, second, batch=head)
    alone = await _correction(tenant, conversation, second)
    assert await _batch_of(head) == head
    assert await _batch_of(sister) == head
    assert await _batch_of(alone) is None

    other, other_conversation, other_agent, _ = await _client()
    with pytest.raises(IntegrityError, match="fk_inbox_corrections_batch"):
        await _correction(other, other_conversation, other_agent, batch=head)
    with pytest.raises(IntegrityError, match="fk_inbox_corrections_batch"):
        await _correction(tenant, conversation, second, batch=uuid.uuid4())


async def test_deleting_the_head_leaves_the_sisters_without_a_batch(
    at_head_afterwards: Any,
) -> None:
    tenant, conversation, first, second = await _client()
    head = await _correction(tenant, conversation, first, head=True)
    sister = await _correction(tenant, conversation, second, batch=head)

    await _exec("DELETE FROM inbox_corrections WHERE id = :i", i=head)

    assert await _batch_of(sister) is None
    (row,) = await _exec("SELECT tenant_id FROM inbox_corrections WHERE id = :i", i=sister)
    assert row[0] == tenant


async def test_the_index_only_holds_batched_rows(at_head_afterwards: Any) -> None:
    (row,) = await _exec(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_inbox_corrections_batch'"
    )
    assert "(tenant_id, batch_id)" in row[0]
    assert "WHERE (batch_id IS NOT NULL)" in row[0]
    assert "batch_id" in InboxCorrection.__table__.c


async def test_downgrade_drops_the_column(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert not await _exec(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'inbox_corrections' AND column_name = 'batch_id'"
    )
    assert not await _exec(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_inbox_corrections_batch'"
    )
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
