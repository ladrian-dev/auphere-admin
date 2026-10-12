"""Bug ``doble-cobro-del-tope`` — la migración 0156 devuelve lo descontado de más.

Baja a 0155, siembra lo que había en producción el 2026-10-10 y vuelve a
subir. Fija:

- un tope afectado vuelve a ``cap - lo cobrado en la semana``: el cliente que
  estaba mudo con tope de sobra vuelve a contestar;
- lo de semanas anteriores no cuenta (ya se repuso al renovar);
- nunca baja un restante, aunque la cuenta saliera menor;
- un tope sin asientos ``:allocation`` en la semana ni se toca;
- repetirla no cambia nada.

Corre en su propio proceso de Alembic y deja la base en head pase lo que pase.
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
_BEFORE = "0155_agents_tenant_fk"


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


async def _cap(tenant_id: uuid.UUID, cap: int, remaining: int) -> None:
    await _exec(
        "UPDATE partner_allocations SET cap = :c, remaining = :r WHERE tenant_id = :t",
        c=cap,
        r=remaining,
        t=tenant_id,
    )


async def _entry(
    partner_id: uuid.UUID, tenant_id: uuid.UUID, kind: str, qty: int, days_ago: int
) -> None:
    turn = uuid.uuid4().hex[:8]
    await _exec(
        "INSERT INTO usage_ledger (id, partner_id, tenant_id, qty, bucket, idempotency_key, created_at) "
        "VALUES (:i, :p, :t, :q, :b, :k, now() - make_interval(days => :d))",
        i=uuid.uuid4(),
        p=partner_id,
        t=tenant_id,
        q=qty,
        b="included" if kind == "allocation" else "purchased",
        k=f"channel:{turn}:{kind}",
        d=days_ago,
    )


async def _remaining(tenant_id: uuid.UUID) -> int:
    rows = await _exec(
        "SELECT remaining FROM partner_allocations WHERE tenant_id = :t", t=tenant_id
    )
    return int(rows[0][0])


async def test_the_week_s_over_debit_goes_back_to_each_client(
    console_world, at_head_afterwards
) -> None:
    a, b = console_world["a"], console_world["b"]
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    # Both partners renewed three days ago: their week started four days ago.
    for partner in (a["partner_id"], b["partner_id"]):
        await _exec(
            "UPDATE partner_wallets SET included_expires_at = now() + interval '3 days' "
            "WHERE partner_id = :p",
            p=partner,
        )
    # A third client of partner A, with no over-debit this week.
    untouched = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:t, 'c', :s, 'pro', 'active')",
        t=untouched,
        s=f"c-{untouched.hex[:8]}",
    )
    await _exec(
        "INSERT INTO partner_allocations (partner_id, tenant_id, cap, remaining) VALUES (:p, :t, 0, 0)",
        p=a["partner_id"],
        t=untouched,
    )

    # Affected and silent: 3 000 spent this week, 3 000 taken twice; older
    # weeks carry their own (already replenished) entries.
    await _cap(a["tenant_id"], 10_000, 0)
    await _entry(a["partner_id"], a["tenant_id"], "purchased", 3_000, days_ago=1)
    await _entry(a["partner_id"], a["tenant_id"], "allocation", 3_000, days_ago=1)
    await _entry(a["partner_id"], a["tenant_id"], "purchased", 5_000, days_ago=10)
    await _entry(a["partner_id"], a["tenant_id"], "allocation", 5_000, days_ago=10)
    # Affected, but its remaining is already above cap - spent: never lowered.
    await _cap(b["tenant_id"], 10_000, 9_500)
    await _entry(b["partner_id"], b["tenant_id"], "purchased", 3_000, days_ago=2)
    await _entry(b["partner_id"], b["tenant_id"], "allocation", 100, days_ago=2)
    # Not affected: spent 6 000 this week, no ``:allocation`` entries.
    await _cap(untouched, 10_000, 4_000)
    await _entry(a["partner_id"], untouched, "purchased", 6_000, days_ago=1)

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    assert await _remaining(a["tenant_id"]) == 7_000
    assert await _remaining(b["tenant_id"]) == 9_500
    assert await _remaining(untouched) == 4_000

    # Running it again changes nothing.
    assert _alembic("downgrade", _BEFORE).returncode == 0
    assert _alembic("upgrade", "head").returncode == 0
    assert await _remaining(a["tenant_id"]) == 7_000
    assert await _remaining(b["tenant_id"]) == 9_500
    assert await _remaining(untouched) == 4_000
