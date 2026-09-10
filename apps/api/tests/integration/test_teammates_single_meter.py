"""Puerta del medidor — un teammate gasta por el mismo camino que el Companion (spec 003, R9).

No hay contador nuevo: el turno de un teammate pasa por ``llm_proxy_partner_scope``
y debita ``partner_wallets`` como cualquier turno del Companion; ``companion.runs``
lleva ``teammate_id`` para atribuirlo, y ``usage_events`` no gana filas nuevas por
teammate. La igualdad byte a byte entre ``/console/teammates/usage.budget`` y
``/console/companion/budget`` se afirma en ``test_teammates_usage.py`` (US5).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Teammate
from nexus_api.db.models.companion import CompanionRun
from nexus_api.db.models.partner_wallet import PartnerWallet

from .test_companion_endpoints import _companion_graph, _finished  # noqa: F401 — fixture y helper

pytestmark = pytest.mark.asyncio


async def _seed_teammate(db_session, world) -> uuid.UUID:
    row = Teammate(
        id=uuid.uuid4(),
        partner_id=world["partner_id"],
        name="Sofía",
        job="Atención al cliente",
        model="anthropic/claude-sonnet-4-6",
        tool_names=["console.whoami", "console.list_clients"],
        permissions={
            "read": True,
            "write": False,
            "spend": False,
            "publish": False,
            "contact": False,
        },
        local_exec=False,
        created_by=world["user_id"],
    )
    db_session.add(row)
    await db_session.commit()
    return row.id


async def _start_teammate_turn(client, world, teammate_id: uuid.UUID) -> tuple[str, str]:
    created = await client.post(
        "/console/companion/threads",
        headers=world["headers"](),
        json={"title": "t", "mode": "build", "teammate_id": str(teammate_id)},
    )
    assert created.status_code == 201, created.text
    thread = created.json()
    assert thread["teammate_id"] == str(teammate_id)
    started = await client.post(
        f"/console/companion/threads/{thread['id']}/runs",
        headers=world["headers"](),
        json={"prompt": "hola"},
    )
    assert started.status_code == 202, started.text
    return thread["id"], started.json()["run_id"]


async def test_a_teammate_turn_debits_the_same_wallet_and_nothing_else(
    client, console_world, db_session
):
    a = console_world["a"]
    teammate_id = await _seed_teammate(db_session, a)
    before = await db_session.scalar(sa.text("SELECT count(*) FROM usage_events"))

    _thread_id, run_id = await _start_teammate_turn(client, a, teammate_id)
    run = await _finished(uuid.UUID(run_id), a["user_id"])
    assert run.teammate_id == teammate_id

    remaining = None
    for _ in range(80):
        db_session.expire_all()
        wallet = await db_session.get(PartnerWallet, a["partner_id"])
        assert wallet is not None
        remaining = int(wallet.included_remaining) + int(wallet.purchased_remaining)
        if remaining < 500_000:
            break
        await asyncio.sleep(0.05)
    assert remaining is not None and remaining < 500_000

    # Ni una fila nueva de consumo con nombre de teammate: un solo medidor.
    after = await db_session.scalar(sa.text("SELECT count(*) FROM usage_events"))
    assert after == before
    named = await db_session.scalar(
        sa.text("SELECT count(*) FROM usage_events WHERE event_type ILIKE '%teammate%'")
    )
    assert int(named) == 0


async def test_the_budget_endpoint_counts_the_teammate_turn(client, console_world, db_session):
    a = console_world["a"]
    teammate_id = await _seed_teammate(db_session, a)
    _thread_id, run_id = await _start_teammate_turn(client, a, teammate_id)
    await _finished(uuid.UUID(run_id), a["user_id"])
    budget = await client.get("/console/companion/budget", headers=a["headers"]())
    assert budget.status_code == 200, budget.text
    assert budget.json()["used"] > 0


async def test_the_console_thread_list_never_shows_a_teammate_thread(
    client, console_world, db_session
):
    a = console_world["a"]
    teammate_id = await _seed_teammate(db_session, a)
    thread_id, _run_id = await _start_teammate_turn(client, a, teammate_id)
    plain = await client.get("/console/companion/threads", headers=a["headers"]())
    assert thread_id not in {t["id"] for t in plain.json()}
    mine = await client.get(
        f"/console/companion/threads?teammate_id={teammate_id}", headers=a["headers"]()
    )
    assert [t["id"] for t in mine.json()] == [thread_id]
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        rows = (await session.execute(sa.select(CompanionRun.teammate_id))).scalars().all()
        assert set(rows) == {teammate_id}
