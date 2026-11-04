"""Un partner nuevo nace sin saldo (owner, 2026-11-03), y el panel no llama saldo al pool.

- nace con 0 US$, también en el pool, y la reposición semanal no le da nada;
- «Saldo disponible» es lo recargado, sin el pool, también para quien lo conserva.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.api.console.companion import partner_budget
from nexus_api.billing.pricing import cents_to_credits
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import Partner, PartnerWallet
from nexus_api.metering.wallet import renew_included_if_expired
from nexus_api.services import operator_identity

pytestmark = pytest.mark.asyncio


async def _operator_headers(db_session, admin_headers) -> dict[str, str]:
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def _new_partner(client, op_headers) -> str:
    suffix = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/admin/partners",
        headers=op_headers,
        json={
            "name": "Nace",
            "slug": f"nace-{suffix}",
            "owner_email": f"duena-{suffix}@example.com",
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test_a_new_partner_starts_at_zero_everywhere(client, db_session, admin_headers) -> None:
    op_headers = await _operator_headers(db_session, admin_headers)
    partner_id = await _new_partner(client, op_headers)

    partner = (await client.get(f"/admin/partners/{partner_id}", headers=admin_headers)).json()
    assert partner["available_cents"] == 0
    assert partner["weekly_pool_tokens"] == 0

    wallet = (
        await client.get(f"/admin/partners/{partner_id}/wallet", headers=admin_headers)
    ).json()
    assert wallet["included_cents"] == 0
    assert wallet["purchased_cents"] == 0


async def test_the_weekly_refill_gives_a_new_partner_nothing(
    client, db_session, admin_headers
) -> None:
    op_headers = await _operator_headers(db_session, admin_headers)
    partner_id = uuid.UUID(await _new_partner(client, op_headers))
    async with db_session.begin():
        await apply_partner_to_session(db_session, partner_id)
        await renew_included_if_expired(
            db_session, partner_id=partner_id, now=datetime.now(UTC) + timedelta(days=8)
        )
        row = await db_session.get(PartnerWallet, partner_id)
        assert row is not None
        assert row.included_remaining == 0


async def test_a_top_up_is_what_the_available_balance_shows(
    client, db_session, admin_headers
) -> None:
    op_headers = await _operator_headers(db_session, admin_headers)
    partner_id = await _new_partner(client, op_headers)
    resp = await client.post(
        f"/admin/partners/{partner_id}/wallet/purchased",
        headers=op_headers,
        json={"amount_cents": 1000, "idempotency_key": str(uuid.uuid4())},
    )
    assert resp.status_code in (200, 201), resp.text
    partner = (await client.get(f"/admin/partners/{partner_id}", headers=admin_headers)).json()
    assert partner["available_cents"] == 1000


async def test_without_a_pool_the_companion_opens_with_a_top_up(
    client, db_session, admin_headers
) -> None:
    op_headers = await _operator_headers(db_session, admin_headers)
    partner_id = await _new_partner(client, op_headers)
    before = await partner_budget(db_session, uuid.UUID(partner_id))
    assert before.exhausted is True

    await client.post(
        f"/admin/partners/{partner_id}/wallet/purchased",
        headers=op_headers,
        json={"amount_cents": 1000, "idempotency_key": str(uuid.uuid4())},
    )
    after = await partner_budget(db_session, uuid.UUID(partner_id))
    assert after.exhausted is False
    assert after.used == 0
    assert after.cap == after.remaining == cents_to_credits(1000)
    assert after.percent == 0


async def test_a_partner_with_a_pool_still_stops_when_it_runs_out(
    db_session,
) -> None:
    """Recargar no alarga el pool de quien lo conserva: eso no ha cambiado."""
    partner_id = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Partner(
                id=partner_id,
                name="Con pool",
                slug=f"con-pool-{partner_id.hex[:6]}",
                weekly_pool_tokens=115_000,
            )
        )
    async with db_session.begin():
        await apply_partner_to_session(db_session, partner_id)
        row = await db_session.get(PartnerWallet, partner_id)
        assert row is not None
        row.included_remaining = 0
        row.purchased_remaining = 1_000_000
    budget = await partner_budget(db_session, partner_id)
    assert budget.exhausted is True
    assert budget.cap == 115_000


async def test_a_partner_that_keeps_its_pool_does_not_show_it_as_balance(
    client, db_session, admin_headers
) -> None:
    partner_id = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Partner(
                id=partner_id,
                name="Con pool",
                slug=f"con-pool-{partner_id.hex[:6]}",
                weekly_pool_tokens=115_000,
            )
        )
    partner = (await client.get(f"/admin/partners/{partner_id}", headers=admin_headers)).json()
    assert partner["available_cents"] == 0
    wallet = (
        await client.get(f"/admin/partners/{partner_id}/wallet", headers=admin_headers)
    ).json()
    assert wallet["included_cents"] == 115
