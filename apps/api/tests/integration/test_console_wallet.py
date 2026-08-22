"""Consola: el libro se lee sin partner_id del cliente; B es 404 opaco."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.companion import build_companion_graph
from nexus_worker.runtime.llm import InMemoryProvider

from nexus_api.api.console import companion as companion_api
from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionRun

pytestmark = pytest.mark.asyncio


def _answer_and_meter(_call: Any) -> str:
    from nexus_worker.metering import collector

    collector.record_llm_usage(
        model="anthropic/claude-sonnet-4-6",
        provider="anthropic",
        usage={"prompt_tokens": 1200, "completion_tokens": 340},
    )
    return "ok"


@pytest_asyncio.fixture(autouse=True)
async def _companion_graph() -> Any:
    provider = InMemoryProvider(responder=_answer_and_meter, thinking_text="pensando")
    graph = build_companion_graph(
        provider=provider,
        model="anthropic/claude-sonnet-4-6",
        checkpointer=MemorySaver(),
    )
    companion_api.set_graph_for_tests(graph)
    yield graph
    companion_api.reset_graph_cache_for_tests()


async def _finished(run_id, principal_id: str, timeout: float = 5.0) -> CompanionRun:
    sm = get_sessionmaker()
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, principal_id)
            run = await session.get(CompanionRun, run_id)
            if run is not None and run.status != "running":
                await session.refresh(run)
                return run
        await asyncio.sleep(0.05)
    raise AssertionError("el run no se cerró a tiempo")


async def test_wallet_is_the_caller_partners(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.get("/console/wallet", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["included_remaining"] == 500_000
    assert body["purchased_remaining"] == 0
    assert body["available"] == 500_000
    assert body["reserve"] == 0
    assert body["exhausted"] is False
    assert "partner_id" not in body


async def test_allocation_of_other_partner_is_opaque_404(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    missing = await client.get("/console/clients/no-such-client/allocation", headers=a["headers"]())
    other = await client.get(
        "/console/clients/{}/allocation".format(b["ref"]), headers=a["headers"]()
    )
    own = await client.get(
        "/console/clients/{}/allocation".format(a["ref"]), headers=a["headers"]()
    )
    assert missing.status_code == 404
    assert other.status_code == 404
    assert missing.json() == other.json()
    assert own.status_code == 200, own.text
    assert own.json()["cap"] == 500_000


async def test_start_run_without_client_uses_partner_wallet(
    client, console_world, db_session
) -> None:
    import uuid

    import sqlalchemy as sa

    from nexus_api.db.models.partner_wallet import PartnerWallet

    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "no-client"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["client_ref"] is None
    resp = await client.post(
        f"/console/companion/threads/{created.json()['id']}/runs",
        headers=a["headers"](),
        json={"prompt": "hola"},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json().get("detail", {}).get("code") != "allocation_empty"
    await _finished(uuid.UUID(resp.json()["run_id"]), a["user_id"])

    wallet = None
    for _ in range(80):
        wallet = await db_session.get(PartnerWallet, a["partner_id"])
        if wallet is not None and int(wallet.included_remaining) < 500_000:
            break
        await asyncio.sleep(0.05)
        db_session.expire_all()
    assert wallet is not None
    assert int(wallet.included_remaining) < 500_000
    remaining = await db_session.scalar(
        sa.text(
            "SELECT remaining FROM partner_allocations WHERE partner_id = :p AND tenant_id = :t"
        ),
        {"p": str(a["partner_id"]), "t": str(a["tenant_id"])},
    )
    assert int(remaining) == 500_000


async def test_start_run_is_409_when_wallet_empty(client, console_world, db_session) -> None:
    import sqlalchemy as sa

    a = console_world["a"]
    await db_session.execute(
        sa.text(
            "UPDATE partner_wallets SET included_remaining = 0, purchased_remaining = 0 "
            "WHERE partner_id = :p"
        ),
        {"p": str(a["partner_id"])},
    )
    await db_session.commit()

    created = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "empty-wallet"},
    )
    assert created.status_code == 201, created.text
    resp = await client.post(
        f"/console/companion/threads/{created.json()['id']}/runs",
        headers=a["headers"](),
        json={"prompt": "hola"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "wallet_empty"


async def test_empty_allocation_does_not_block_companion(client, console_world, db_session) -> None:
    import sqlalchemy as sa

    a = console_world["a"]
    await db_session.execute(
        sa.text(
            "UPDATE partner_allocations SET remaining = 0 WHERE partner_id = :p AND tenant_id = :t"
        ),
        {"p": str(a["partner_id"]), "t": str(a["tenant_id"])},
    )
    await db_session.commit()

    created = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "empty-alloc", "client_ref": a["ref"]},
    )
    assert created.status_code == 201, created.text
    resp = await client.post(
        f"/console/companion/threads/{created.json()['id']}/runs",
        headers=a["headers"](),
        json={"prompt": "hola"},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json().get("detail", {}).get("code") != "allocation_empty"


async def test_allocations_list_is_only_the_caller_partners(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    resp = await client.get("/console/wallet/allocations", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    refs = [row["client_ref"] for row in body]
    assert a["ref"] in refs
    assert b["ref"] not in refs
    for row in body:
        assert "partner_id" not in row
        assert "tenant_id" not in row
        assert set(row) == {"client_ref", "cap", "remaining"}


async def test_unreadable_book_is_zeros_and_empty_allocations(
    client, console_world, monkeypatch
) -> None:
    async def gone(_partner_id):
        return None

    monkeypatch.setattr("nexus_api.api.console.wallet.read_wallet", gone)
    a = console_world["a"]
    wallet = await client.get("/console/wallet", headers=a["headers"]())
    allocs = await client.get("/console/wallet/allocations", headers=a["headers"]())
    assert wallet.status_code == 200, wallet.text
    body = wallet.json()
    assert body["included_remaining"] == 0
    assert body["purchased_remaining"] == 0
    assert body["available"] == 0
    assert body["reserve"] == 0
    assert body["exhausted"] is True
    assert "partner_id" not in body
    assert allocs.status_code == 200, allocs.text
    assert allocs.json() == []


async def test_unreadable_allocations_list_is_empty(client, console_world, monkeypatch) -> None:
    async def boom(_partner_id):
        raise RuntimeError("allocations down")

    monkeypatch.setattr("nexus_api.api.console.wallet._list_allocations", boom)
    a = console_world["a"]
    resp = await client.get("/console/wallet/allocations", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_put_allocation_of_other_partner_is_opaque_404(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    missing = await client.put(
        "/console/clients/no-such-client/allocation",
        headers=a["headers"](),
        json={"cap": 1},
    )
    other = await client.put(
        "/console/clients/{}/allocation".format(b["ref"]),
        headers=a["headers"](),
        json={"cap": 1},
    )
    assert missing.status_code == 404
    assert other.status_code == 404
    assert missing.json() == other.json()


async def test_put_own_allocation_raises_cap(client, console_world, db_session) -> None:
    import sqlalchemy as sa

    a = console_world["a"]
    await db_session.execute(
        sa.text("UPDATE partner_wallets SET purchased_remaining = 100000 WHERE partner_id = :p"),
        {"p": str(a["partner_id"])},
    )
    await db_session.commit()

    resp = await client.put(
        "/console/clients/{}/allocation".format(a["ref"]),
        headers=a["headers"](),
        json={"cap": 600_000},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["client_ref"] == a["ref"]
    assert body["cap"] == 600_000
    assert body["remaining"] == 600_000
    assert "partner_id" not in body
    assert "tenant_id" not in body

    again = await client.get(
        "/console/clients/{}/allocation".format(a["ref"]), headers=a["headers"]()
    )
    assert again.status_code == 200, again.text
    assert again.json()["cap"] == 600_000
    assert again.json()["remaining"] == 600_000


async def test_put_allocation_409_when_sum_exceeds_available(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.put(
        "/console/clients/{}/allocation".format(a["ref"]),
        headers=a["headers"](),
        json={"cap": 500_001},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "over_allocated"

    own = await client.get(
        "/console/clients/{}/allocation".format(a["ref"]), headers=a["headers"]()
    )
    assert own.status_code == 200, own.text
    assert own.json()["cap"] == 500_000
    assert own.json()["remaining"] == 500_000


async def test_put_allocation_forbidden_without_usage_write(
    client, console_world, db_session
) -> None:
    from tests.conftest import add_console_member

    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    resp = await client.put(
        "/console/clients/{}/allocation".format(a["ref"]),
        headers=analyst["headers"](),
        json={"cap": 1},
    )
    assert resp.status_code == 403, resp.text
    readable = await client.get(
        "/console/clients/{}/allocation".format(a["ref"]), headers=analyst["headers"]()
    )
    assert readable.status_code == 200, readable.text


async def test_put_allocation_rejects_partner_id_in_body(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.put(
        "/console/clients/{}/allocation".format(a["ref"]),
        headers=a["headers"](),
        json={"cap": 1, "partner_id": str(a["partner_id"])},
    )
    assert resp.status_code == 422, resp.text


async def test_recharge_purchased_adds_tokens_for_the_caller(client, console_world) -> None:
    a = console_world["a"]
    before = await client.get("/console/wallet", headers=a["headers"]())
    assert before.status_code == 200, before.text
    purchased = before.json()["purchased_remaining"]
    resp = await client.post(
        "/console/wallet/purchased",
        headers=a["headers"](),
        json={"qty": 250},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchased_remaining"] == purchased + 250
    assert "partner_id" not in body
    again = await client.get("/console/wallet", headers=a["headers"]())
    assert again.json()["purchased_remaining"] == purchased + 250


async def test_recharge_rejects_bad_qty_and_partner_id_in_body(client, console_world) -> None:
    a = console_world["a"]
    zero = await client.post("/console/wallet/purchased", headers=a["headers"](), json={"qty": 0})
    extra = await client.post(
        "/console/wallet/purchased",
        headers=a["headers"](),
        json={"qty": 1, "partner_id": str(a["partner_id"])},
    )
    assert zero.status_code == 422, zero.text
    assert extra.status_code == 422, extra.text


async def test_recharge_of_a_never_credits_b(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    before_b = await client.get("/console/wallet", headers=b["headers"]())
    assert before_b.status_code == 200, before_b.text
    resp = await client.post(
        "/console/wallet/purchased",
        headers=a["headers"](),
        json={"qty": 77},
    )
    assert resp.status_code == 200, resp.text
    after_b = await client.get("/console/wallet", headers=b["headers"]())
    assert after_b.status_code == 200, after_b.text
    assert after_b.json()["purchased_remaining"] == before_b.json()["purchased_remaining"]
    assert after_b.json()["available"] == before_b.json()["available"]


async def test_recharge_in_prod_is_opaque_404_and_does_not_credit(
    client, console_world, monkeypatch
) -> None:
    from nexus_api.config import Settings

    monkeypatch.setattr(Settings, "is_prod", property(lambda self: True))
    a = console_world["a"]
    before = await client.get("/console/wallet", headers=a["headers"]())
    assert before.status_code == 200, before.text
    purchased = before.json()["purchased_remaining"]
    missing = await client.get("/console/clients/no-such-client/allocation", headers=a["headers"]())
    resp = await client.post(
        "/console/wallet/purchased",
        headers=a["headers"](),
        json={"qty": 1},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json() == missing.json()
    after = await client.get("/console/wallet", headers=a["headers"]())
    assert after.status_code == 200, after.text
    assert after.json()["purchased_remaining"] == purchased


async def test_recharge_forbidden_without_usage_write(client, console_world, db_session) -> None:
    from tests.conftest import add_console_member

    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    resp = await client.post(
        "/console/wallet/purchased",
        headers=analyst["headers"](),
        json={"qty": 1},
    )
    assert resp.status_code == 403, resp.text


async def _add_unallocated_client(db_session, *, partner_id, ref: str):
    import uuid

    from nexus_api.db.models import PartnerTenant, Tenant, TenantPlan, TenantStatus

    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name=f"Unallocated {ref}",
            slug=f"p-unalloc-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            partner_id=partner_id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=partner_id,
            external_client_ref=ref,
            tenant_id=tenant_id,
            client_name=f"Unallocated {ref}",
        )
    )
    await db_session.commit()
    return tenant_id


async def test_put_creates_allocation_for_client_without_row(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    ref = "client-a-unalloc"
    await _add_unallocated_client(db_session, partner_id=a["partner_id"], ref=ref)

    missing = await client.get(f"/console/clients/{ref}/allocation", headers=a["headers"]())
    assert missing.status_code == 404, missing.text

    lowered = await client.put(
        "/console/clients/{}/allocation".format(a["ref"]),
        headers=a["headers"](),
        json={"cap": 400_000},
    )
    assert lowered.status_code == 200, lowered.text

    created = await client.put(
        f"/console/clients/{ref}/allocation",
        headers=a["headers"](),
        json={"cap": 100_000},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["client_ref"] == ref
    assert body["cap"] == 100_000
    assert body["remaining"] == 100_000
    assert "tenant_id" not in body
    assert "partner_id" not in body


async def test_put_first_allocation_409_when_sum_exceeds_available(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    ref = "client-a-over"
    await _add_unallocated_client(db_session, partner_id=a["partner_id"], ref=ref)
    resp = await client.put(
        f"/console/clients/{ref}/allocation",
        headers=a["headers"](),
        json={"cap": 1},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "over_allocated"
    still = await client.get(f"/console/clients/{ref}/allocation", headers=a["headers"]())
    assert still.status_code == 404, still.text

