"""Consola: el libro se lee sin partner_id del cliente; B es 404 opaco."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
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
    # Spec 004 (R4.6): un solo número decide, así que un solo código lo dice.
    # Antes había dos puertas sobre el mismo saldo —la del presupuesto y
    # ``_require_wallet``— y devolvían ``budget_paused`` y ``wallet_empty``
    # para un estado idéntico. Queda la primera, que además se pinta como
    # pausa y lleva la instantánea del presupuesto dentro.
    assert resp.json()["detail"]["code"] == "budget_paused"


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


async def test_a_cap_above_the_current_balance_is_accepted(client, console_world) -> None:
    """Spec 004 (R6, decidido 2026-09-12): el tope es un LÍMITE DE GASTO.

    Antes esto devolvía 409 ``over_allocated``, porque el tope se trataba como
    una reserva sobre el saldo. Acotarlo así tenía una consecuencia que solo
    apareció al implementarlo: un partner sin créditos comprados no podía dar
    cuota a ningún cliente, y **sus clientes nacían mudos** — el modo de fallo
    que costó el corte del 31-ago.

    Lo que impide gastar de más sigue siendo ``allow_channel_turn``, que mira el
    saldo real en cada turno. El tope es otra cosa: el techo que el partner le
    pone a un cliente para que no se lleve todo.
    """
    a = console_world["a"]
    resp = await client.put(
        "/console/clients/{}/allocation".format(a["ref"]),
        headers=a["headers"](),
        json={"cap": 500_001},
    )
    assert resp.status_code == 200, resp.text

    own = await client.get(
        "/console/clients/{}/allocation".format(a["ref"]), headers=a["headers"]()
    )
    assert own.status_code == 200, own.text
    assert own.json()["cap"] == 500_001


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


# Los cinco tests de la recarga del partner vivían aquí y **se borraron con
# la spec 005**, junto a la ruta que probaban.
#
# ``POST /console/wallet/purchased`` era un juguete de desarrollo apagado por
# entorno: un partner acreditándose saldo sin pagar. Ahora la compra es real
# y el crédito entra por el aviso del pago confirmado.
#
# Lo que sustituye a estos tests es
# ``tests/integration/test_wallet_purchased_is_gone.py``, que comprueba que la
# puerta no está —ni registrada, ni declarada, ni apagada por entorno— y que
# la recarga de OPERADOR, que sí deja auditoría, sigue viva.


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


async def test_a_first_cap_is_accepted_even_with_the_balance_committed(
    client, console_world, db_session
) -> None:
    """El compañero del test de arriba, para el cliente que aún no tiene fila.

    Con la lectura vieja, un segundo cliente no podía recibir ni **un** token de
    tope si el primero ya tenía comprometido todo el saldo. Con el tope como
    límite de gasto, sí: lo que decide si atiende es el saldo del momento.
    """
    a = console_world["a"]
    ref = "client-a-over"
    await _add_unallocated_client(db_session, partner_id=a["partner_id"], ref=ref)
    resp = await client.put(
        f"/console/clients/{ref}/allocation",
        headers=a["headers"](),
        json={"cap": 1},
    )
    assert resp.status_code == 200, resp.text
    now = await client.get(f"/console/clients/{ref}/allocation", headers=a["headers"]())
    assert now.status_code == 200, now.text
    assert now.json()["cap"] == 1


# ── admin C3 (F1) ────────────────────────────────────────────────────────────


def _admin_wallet(partner_id) -> str:
    return f"/admin/partners/{partner_id}/wallet"


async def test_admin_purchased_credits_and_shows_ledger(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    before = await client.get(_admin_wallet(pid), headers=admin_headers)
    assert before.status_code == 200, before.text
    purchased = before.json()["purchased_remaining"]
    available = before.json()["available"]

    resp = await client.post(
        f"{_admin_wallet(pid)}/purchased",
        headers=admin_headers,
        json={"qty": 250},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchased_remaining"] == purchased + 250
    assert body["available"] == available + 250

    again = await client.get(_admin_wallet(pid), headers=admin_headers)
    assert again.status_code == 200, again.text
    assert again.json()["purchased_remaining"] == purchased + 250

    ledger = await client.get(f"{_admin_wallet(pid)}/ledger", headers=admin_headers)
    assert ledger.status_code == 200, ledger.text
    rows = ledger.json()
    assert any(
        row["qty"] == 250 and row["bucket"] == "purchased" and row["reason"] == "admin_purchased"
        for row in rows
    )
    for row in rows:
        assert set(row) == {"id", "bucket", "qty", "reason", "created_at"}

    import sqlalchemy as sa

    from nexus_api.db.models import AuditLog

    audit = await db_session.scalar(
        sa.select(AuditLog)
        .where(AuditLog.action == "wallet.admin_purchased")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.tenant_id is None
    assert audit.actor == "admin:test-adm"
    assert audit.actor != f"admin:{admin_headers['Authorization'].removeprefix('Bearer ')}"
    assert audit.target == f"partner:{pid}"
    assert audit.before_json == {"available": available}
    assert audit.after_json == {"available": available + 250}


async def test_admin_purchased_rejects_extra_and_partner_id(
    client, console_world, admin_headers
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    before = await client.get(_admin_wallet(pid), headers=admin_headers)
    assert before.status_code == 200, before.text
    purchased = before.json()["purchased_remaining"]

    extra = await client.post(
        f"{_admin_wallet(pid)}/purchased",
        headers=admin_headers,
        json={"qty": 1, "note": "nope"},
    )
    in_body = await client.post(
        f"{_admin_wallet(pid)}/purchased",
        headers=admin_headers,
        json={"qty": 1, "partner_id": str(pid)},
    )
    assert extra.status_code == 422, extra.text
    assert in_body.status_code == 422, in_body.text

    after = await client.get(_admin_wallet(pid), headers=admin_headers)
    assert after.status_code == 200, after.text
    assert after.json()["purchased_remaining"] == purchased


async def test_admin_path_a_does_not_return_or_credit_b(
    client, console_world, admin_headers
) -> None:
    a, b = console_world["a"], console_world["b"]
    before_b = await client.get(_admin_wallet(b["partner_id"]), headers=admin_headers)
    assert before_b.status_code == 200, before_b.text
    wallet_a = await client.get(_admin_wallet(a["partner_id"]), headers=admin_headers)
    assert wallet_a.status_code == 200, wallet_a.text
    assert wallet_a.json()["purchased_remaining"] != before_b.json()["purchased_remaining"] or (
        wallet_a.json()["included_remaining"] == 500_000
    )

    resp = await client.post(
        f"{_admin_wallet(a['partner_id'])}/purchased",
        headers=admin_headers,
        json={"qty": 77},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchased_remaining"] == wallet_a.json()["purchased_remaining"] + 77

    after_b = await client.get(_admin_wallet(b["partner_id"]), headers=admin_headers)
    assert after_b.status_code == 200, after_b.text
    assert after_b.json()["purchased_remaining"] == before_b.json()["purchased_remaining"]
    assert after_b.json()["available"] == before_b.json()["available"]

    ledger_a = await client.get(f"{_admin_wallet(a['partner_id'])}/ledger", headers=admin_headers)
    ledger_b = await client.get(f"{_admin_wallet(b['partner_id'])}/ledger", headers=admin_headers)
    assert ledger_a.status_code == 200, ledger_a.text
    assert ledger_b.status_code == 200, ledger_b.text
    ids_a = {row["id"] for row in ledger_a.json()}
    ids_b = {row["id"] for row in ledger_b.json()}
    assert ids_a.isdisjoint(ids_b)


async def test_admin_recharge_works_in_prod_and_leaves_an_audit_row(
    client, console_world, admin_headers, monkeypatch
) -> None:
    """D4 — en producción Auphere SÍ puede recargar.

    Hasta el 2026-09-08 este endpoint devolvía 404 opaco si ``is_prod``, así
    que en producción no recargaba nadie y el único camino era escribir en la
    BD a mano. Un entorno no es un permiso: quien manda aquí es el token de
    admin, y cada recarga deja auditoría.
    """

    from nexus_api.config import Settings

    monkeypatch.setattr(Settings, "is_prod", property(lambda self: True))
    pid = console_world["a"]["partner_id"]
    before = await client.get(_admin_wallet(pid), headers=admin_headers)
    assert before.status_code == 200, before.text
    purchased = before.json()["purchased_remaining"]

    resp = await client.post(
        f"{_admin_wallet(pid)}/purchased",
        headers=admin_headers,
        json={"qty": 1_000},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["purchased_remaining"] == purchased + 1_000

    after = await client.get(_admin_wallet(pid), headers=admin_headers)
    assert after.status_code == 200, after.text
    assert after.json()["purchased_remaining"] == purchased + 1_000


# ``test_partner_self_recharge_stays_closed_in_prod`` también se fue: decía que
# la puerta seguía cerrada en producción, y la puerta ya no existe en ningún
# entorno. Comprobar que un 404 sigue siendo 404 cuando la ruta se borró es un
# test que pasa por la razón equivocada.


# ── spec 016 · una sola definición de «sin cupo» ───────────────────────


async def test_quota_state_matches_the_channel_gate(client, console_world, db_session) -> None:
    """R2.1 / R2.5: ``quota_state`` (lote, lo que pinta la consola) dice lo
    mismo que ``allow_channel_turn`` (la puerta del canal) en los cuatro
    casos: con cupo, cupo agotado, sin fila y sin cartera."""
    import uuid as _uuid

    from nexus_api.metering.wallet import allow_channel_turn, quota_state

    a = console_world["a"]
    unalloc_ref = "client-a-noquota"
    unalloc_tid = await _add_unallocated_client(
        db_session, partner_id=a["partner_id"], ref=unalloc_ref
    )
    ok = await client.put(
        f"/console/clients/{a['ref']}/allocation", headers=a["headers"](), json={"cap": 50_000}
    )
    assert ok.status_code == 200, ok.text

    states = await quota_state(a["partner_id"], [a["tenant_id"], unalloc_tid])
    assert states[a["tenant_id"]] is False
    assert states[unalloc_tid] is True
    assert await allow_channel_turn(a["tenant_id"]) is True
    assert await allow_channel_turn(unalloc_tid) is False

    # Agotado: el tope baja a lo consumido (0) y la fila sigue existiendo.
    zero = await client.put(
        f"/console/clients/{a['ref']}/allocation", headers=a["headers"](), json={"cap": 0}
    )
    assert zero.status_code == 200, zero.text
    assert (await quota_state(a["partner_id"], [a["tenant_id"]]))[a["tenant_id"]] is True
    assert await allow_channel_turn(a["tenant_id"]) is False

    # Sin cartera: un partner que no existe lee como agotado (fail closed).
    ghost = _uuid.uuid4()
    assert (await quota_state(ghost, [a["tenant_id"]]))[a["tenant_id"]] is True
    # Un tenant ajeno no aparece con cupo por error: también agotado.
    assert (await quota_state(a["partner_id"], [_uuid.uuid4()])) != {}


# ── spec 016 · mover tope en una transacción (R3.1-R3.3) ─────────────────────


async def _caps(client, headers) -> dict[str, tuple[int, int]]:
    rows = (await client.get("/console/wallet/allocations", headers=headers)).json()
    return {r["client_ref"]: (r["cap"], r["remaining"]) for r in rows}


async def test_move_allocation_lowers_and_raises_in_one_call(
    client, console_world, db_session
) -> None:
    """CE-003: la suma de topes no cambia; el destino sin fila nace con ``qty``."""
    a = console_world["a"]
    other = "client-a-move-to"
    await _add_unallocated_client(db_session, partner_id=a["partner_id"], ref=other)
    before = await _caps(client, a["headers"]())
    assert other not in before
    total_before = sum(cap for cap, _ in before.values())

    resp = await client.post(
        "/console/wallet/allocations/move",
        headers=a["headers"](),
        json={"from_ref": a["ref"], "to_ref": other, "qty": 20_000},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["from"]["client_ref"] == a["ref"]
    assert body["from"]["cap"] == before[a["ref"]][0] - 20_000
    assert body["from"]["remaining"] == min(before[a["ref"]][1], body["from"]["cap"])
    assert body["to"] == {"client_ref": other, "cap": 20_000, "remaining": 20_000}
    assert "tenant_id" not in resp.text and "partner_id" not in resp.text

    after = await _caps(client, a["headers"]())
    assert sum(cap for cap, _ in after.values()) == total_before
    assert after[other] == (20_000, 20_000)

    # Recorte del restante: un origen que ya gastó no puede quedar con
    # ``remaining > cap`` (misma regla que ``set_allocation``).
    from nexus_api.db.models import PartnerAllocation

    row = await db_session.scalar(
        sa.select(PartnerAllocation).where(PartnerAllocation.tenant_id == a["tenant_id"])
    )
    assert row is not None and row.remaining <= row.cap

    from nexus_api.db.models import AuditLog

    audit = (
        await db_session.scalars(
            sa.select(AuditLog).where(AuditLog.action == "console.allocation.move")
        )
    ).all()
    assert len(audit) == 1
    assert audit[0].actor.startswith("console:")
    assert audit[0].target == f"partner:{a['partner_id']}"
    assert audit[0].after_json == {"from": a["ref"], "to": other, "qty": 20_000}


async def test_move_allocation_errors_by_code_and_nothing_changes(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    other = "client-a-move-err"
    await _add_unallocated_client(db_session, partner_id=a["partner_id"], ref=other)
    before = await _caps(client, a["headers"]())
    cap_a = before[a["ref"]][0]

    same = await client.post(
        "/console/wallet/allocations/move",
        headers=a["headers"](),
        json={"from_ref": a["ref"], "to_ref": a["ref"], "qty": 1},
    )
    assert same.status_code == 422, same.text
    assert same.json()["detail"] == {"code": "same_client"}

    too_much = await client.post(
        "/console/wallet/allocations/move",
        headers=a["headers"](),
        json={"from_ref": a["ref"], "to_ref": other, "qty": cap_a + 1},
    )
    assert too_much.status_code == 422, too_much.text
    assert too_much.json()["detail"] == {
        "code": "insufficient_cap",
        "cap": cap_a,
        "qty": cap_a + 1,
    }

    # El destino sin fila tampoco puede ser origen: su tope es 0.
    empty_source = await client.post(
        "/console/wallet/allocations/move",
        headers=a["headers"](),
        json={"from_ref": other, "to_ref": a["ref"], "qty": 1},
    )
    assert empty_source.status_code == 422, empty_source.text
    assert empty_source.json()["detail"]["code"] == "insufficient_cap"
    assert empty_source.json()["detail"]["cap"] == 0

    for qty in (0, -5):
        bad = await client.post(
            "/console/wallet/allocations/move",
            headers=a["headers"](),
            json={"from_ref": a["ref"], "to_ref": other, "qty": qty},
        )
        assert bad.status_code == 422, bad.text

    extra = await client.post(
        "/console/wallet/allocations/move",
        headers=a["headers"](),
        json={"from_ref": a["ref"], "to_ref": other, "qty": 1, "partner_id": "x"},
    )
    assert extra.status_code == 422, extra.text

    assert await _caps(client, a["headers"]()) == before


async def test_move_allocation_forbidden_without_usage_write(
    client, console_world, db_session
) -> None:
    from tests.conftest import add_console_member

    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    resp = await client.post(
        "/console/wallet/allocations/move",
        headers=analyst["headers"](),
        json={"from_ref": a["ref"], "to_ref": "x", "qty": 1},
    )
    assert resp.status_code == 403, resp.text


async def test_move_allocation_is_atomic(client, console_world, db_session, monkeypatch) -> None:
    """CE-003: si el destino falla después de que el origen ya bajó, la
    transacción se deshace y ningún tope cambia."""
    from nexus_api.metering import wallet as wallet_module

    a = console_world["a"]
    other = "client-a-move-atomic"
    await _add_unallocated_client(db_session, partner_id=a["partner_id"], ref=other)
    before = await _caps(client, a["headers"]())

    def _boom(row, qty):
        raise RuntimeError("destino roto")

    monkeypatch.setattr(wallet_module, "_credit_allocation", _boom)
    # El transporte de pruebas relanza la excepción del servidor (en
    # producción sería un 500): lo que importa es lo que queda en el libro.
    with pytest.raises(RuntimeError, match="destino roto"):
        await client.post(
            "/console/wallet/allocations/move",
            headers=a["headers"](),
            json={"from_ref": a["ref"], "to_ref": other, "qty": 20_000},
        )
    assert await _caps(client, a["headers"]()) == before

    from nexus_api.db.models import AuditLog

    assert (
        await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "console.allocation.move")
        )
    ) == 0
