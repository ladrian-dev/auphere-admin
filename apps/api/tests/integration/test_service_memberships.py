"""Spec 077 · R6, R7, R8 y R9 — la membresía de un cliente.

Stripe se simula (``billing/tenant_membership``); lo demás es real: la tabla
con RLS, el libro del partner, la puerta de la API y la auditoría.

- Cargo fijo a la bolsa: una vez por periodo, sin saldo no cobra, usa la línea
  de crédito, no toca el tope del cliente ni cuenta como consumo, y la
  conciliación cuadra. Una caída entre el cargo y la fila no cobra dos veces.
- Puerta: 402 en el envío directo y en las difusiones; sin membresía, igual.
- Panel: configurar, enlace de pago (cliente propio, enlace anterior caducado),
  actualizar desde Stripe, cancelar, archivar, cobros y auditoría.
- Cron: cobra la bolsa al vencer y relee Stripe como mucho una vez por hora.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.billing import tenant_membership as stripe_membership
from nexus_api.billing.pricing import cents_to_credits
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ApiKeyScope,
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Partner,
    PartnerAllocation,
    PartnerApiKey,
    PartnerWallet,
    ServiceMembership,
    Tenant,
    TenantPlan,
    UsageLedger,
)
from nexus_api.metering.wallet import charge_fixed_fee, credit_burn, reconcile_purchased
from nexus_api.services import service_memberships as memberships
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_FEE = cents_to_credits(4000)
_TEMPLATE = TemplateOut(
    id="t1",
    name="aviso",
    language="es",
    category="UTILITY",
    status="APPROVED",
    components=[{"type": "BODY", "text": "Hola {{nombre}}"}],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_TEMPLATE], "waba-1"

    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)


# ── worlds ───────────────────────────────────────────────────────────────────


async def _partner(db_session: Any, *, purchased: int, credit_limit: int = 0) -> uuid.UUID:
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="Partner", slug=f"p-{pid.hex[:6]}"))
    await db_session.commit()
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        # A partner is born with its wallet; set it, or create it if not.
        row = await s.get(PartnerWallet, pid)
        if row is None:
            row = PartnerWallet(partner_id=pid, included_remaining=0, purchased_remaining=0)
            s.add(row)
        row.included_remaining = 0
        row.purchased_remaining = purchased
        row.credit_limit = credit_limit
    return pid


async def _tenant(db_session: Any, *, partner_id: uuid.UUID | None = None) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Tecfin",
            slug=f"tf-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            partner_id=partner_id,
            send_only=True,
        )
    )
    await db_session.flush()
    db_session.add(
        Channel(
            tenant_id=tid,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+5622{tid.int % 10_000_000:07d}",
            status=ChannelStatus.ACTIVE,
        )
    )
    await db_session.commit()
    return tid


async def _key(db_session: Any, tenant_id: uuid.UUID) -> dict[str, str]:
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="D", slug=f"d-{pid.hex[:6]}"))
    generated = generate_api_key()
    db_session.add(
        PartnerApiKey(
            partner_id=pid,
            tenant_id=tenant_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=[ApiKeyScope.MESSAGES_SEND.value],
        )
    )
    await db_session.commit()
    return {"Authorization": f"Bearer {generated.plaintext}"}


async def _operator(db_session: Any, admin_headers: dict[str, str]) -> tuple[dict[str, str], str]:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id)}, account.email


async def _purchased(partner_id: uuid.UUID) -> int:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        row = await s.get(PartnerWallet, partner_id)
        assert row is not None
        return int(row.purchased_remaining)


async def _row(tenant_id: uuid.UUID) -> ServiceMembership:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        row = await s.scalar(
            sa.select(ServiceMembership).where(ServiceMembership.archived_at.is_(None))
        )
        assert row is not None
        return row


async def _send(client: Any, headers: dict[str, str]) -> int:
    resp = await client.post(
        "/v1/messages/template",
        json={"to": "+56912345678", "template_name": "aviso", "variables": {"nombre": "Ana"}},
        headers=headers,
    )
    return resp.status_code


# ── R8: the fixed fee in the partner's book ──────────────────────────────────


async def test_fixed_fee_is_charged_once_per_period(db_session) -> None:
    pid = await _partner(db_session, purchased=_FEE * 2)
    tid = await _tenant(db_session, partner_id=pid)
    start = datetime(2026, 11, 24, 10, tzinfo=UTC)
    first = await charge_fixed_fee(
        partner_id=pid, tenant_id=tid, qty=_FEE, reason="membership", period_start=start
    )
    again = await charge_fixed_fee(
        partner_id=pid, tenant_id=tid, qty=_FEE, reason="membership", period_start=start
    )
    assert (first.outcome, again.outcome) == ("charged", "duplicate")
    assert await _purchased(pid) == _FEE


async def test_fixed_fee_without_balance_takes_nothing(db_session) -> None:
    pid = await _partner(db_session, purchased=_FEE - 1)
    tid = await _tenant(db_session, partner_id=pid)
    result = await charge_fixed_fee(
        partner_id=pid, tenant_id=tid, qty=_FEE, reason="membership", period_start=datetime.now(UTC)
    )
    assert result.outcome == "insufficient"
    assert await _purchased(pid) == _FEE - 1


async def test_fixed_fee_uses_the_credit_line(db_session) -> None:
    pid = await _partner(db_session, purchased=0, credit_limit=_FEE)
    tid = await _tenant(db_session, partner_id=pid)
    result = await charge_fixed_fee(
        partner_id=pid, tenant_id=tid, qty=_FEE, reason="membership", period_start=datetime.now(UTC)
    )
    assert result.outcome == "charged"
    assert await _purchased(pid) == -_FEE


async def test_fixed_fee_is_not_consumption_and_reconciles(db_session) -> None:
    pid = await _partner(db_session, purchased=_FEE * 3)
    tid = await _tenant(db_session, partner_id=pid)
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        s.add(PartnerAllocation(partner_id=pid, tenant_id=tid, cap=_FEE, remaining=_FEE))
        # The opening balance as a credit, so the book reconciles from zero.
        s.add(
            UsageLedger(
                partner_id=pid,
                qty=_FEE * 3,
                bucket="purchased",
                kind="credit_admin",
                idempotency_key=f"open-{pid}",
            )
        )
    await charge_fixed_fee(
        partner_id=pid, tenant_id=tid, qty=_FEE, reason="membership", period_start=datetime.now(UTC)
    )
    rec = await reconcile_purchased(pid)
    assert rec is not None and rec.balanced, rec
    burn = await credit_burn(pid, [tid], datetime.now(UTC) - timedelta(days=1))
    assert burn.get(tid, 0) == 0
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        alloc = await s.scalar(
            sa.select(PartnerAllocation.remaining).where(PartnerAllocation.tenant_id == tid)
        )
    assert alloc == _FEE


# ── R8 through the service ───────────────────────────────────────────────────


async def test_wallet_membership_activates_charges_and_lapses(
    client, db_session, admin_headers
) -> None:
    pid = await _partner(db_session, purchased=_FEE)
    tid = await _tenant(db_session, partner_id=pid)
    headers, _email = await _operator(db_session, admin_headers)
    put = await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "partner_wallet", "amount_cents": 4000},
        headers=headers,
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert (body["status"], body["active"]) == ("active", True)
    assert await _purchased(pid) == 0
    # Renewal with no balance: nothing taken, past due, sends stop.
    row = await _row(tid)
    end = row.current_period_end
    assert end is not None
    send_headers = await _key(db_session, tid)
    # Tried ahead of time: the paid period still runs, sends still go.
    assert await memberships.charge_wallet_if_due(tid, now=end - timedelta(minutes=30)) is False
    assert (await _row(tid)).status == "active"
    assert await _send(client, send_headers) == 202
    # Once it ends without balance: past due, and nothing goes out.
    assert await memberships.charge_wallet_if_due(tid, now=end + timedelta(minutes=1)) is False
    assert (await _row(tid)).status == "past_due"
    assert await _send(client, send_headers) == 402
    # Balance comes back: the next try charges and reactivates.
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        wallet = await s.get(PartnerWallet, pid)
        assert wallet is not None
        wallet.purchased_remaining = _FEE
    assert await memberships.charge_wallet_if_due(tid) is True
    assert (await _row(tid)).status == "active"
    assert await _send(client, send_headers) == 202


async def test_a_crash_between_charge_and_row_does_not_charge_twice(db_session) -> None:
    """Advisor 2: the period is stored before charging, so the retry's key is
    the same and the book answers duplicate."""
    pid = await _partner(db_session, purchased=_FEE * 2)
    tid = await _tenant(db_session, partner_id=pid)
    start = datetime.now(UTC).replace(microsecond=0)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(
            ServiceMembership(
                tenant_id=tid,
                payer="partner_wallet",
                amount_cents=4000,
                status="pending",
                next_period_start=start,
            )
        )
    # The charge went through, then the process died before writing the row.
    await charge_fixed_fee(
        partner_id=pid, tenant_id=tid, qty=_FEE, reason="membership", period_start=start
    )
    assert await memberships.charge_wallet_if_due(tid, force=True) is True
    row = await _row(tid)
    assert row.status == "active"
    assert row.current_period_start == start
    assert await _purchased(pid) == _FEE


async def test_wallet_membership_needs_a_partner(client, db_session, admin_headers) -> None:
    tid = await _tenant(db_session)
    headers, _ = await _operator(db_session, admin_headers)
    put = await client.put(
        f"/admin/tenants/{tid}/membership", json={"payer": "partner_wallet"}, headers=headers
    )
    assert put.status_code == 422
    assert put.json()["detail"] == "no_partner"


# ── R9: the gate ─────────────────────────────────────────────────────────────


async def test_no_membership_sends_as_today(client, db_session) -> None:
    tid = await _tenant(db_session)
    assert await _send(client, await _key(db_session, tid)) == 202


async def test_pending_membership_refuses_with_402_and_queues_nothing(client, db_session) -> None:
    tid = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(ServiceMembership(tenant_id=tid, payer="stripe", amount_cents=4000))
    resp = await client.post(
        "/v1/messages/template",
        json={"to": "+56912345678", "template_name": "aviso", "variables": {"nombre": "Ana"}},
        headers=await _key(db_session, tid),
    )
    assert resp.status_code == 402
    assert "membership_inactive" in resp.text


async def test_a_membership_of_one_client_does_not_gate_another(client, db_session) -> None:
    a = await _tenant(db_session)
    b = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, a):
        s.add(ServiceMembership(tenant_id=a, payer="stripe", amount_cents=4000))
    assert await _send(client, await _key(db_session, b)) == 202


async def test_broadcasts_are_gated_too(db_session) -> None:
    from fastapi import HTTPException

    from nexus_api.schemas.broadcasts import BroadcastCreateIn
    from nexus_api.services.broadcasts import create_broadcast

    tid = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(ServiceMembership(tenant_id=tid, payer="stripe", amount_cents=4000))
    with pytest.raises(HTTPException) as exc:
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
            await create_broadcast(
                s,
                tenant_id=tid,
                partner_id=uuid.uuid4(),
                recipient_cap=10,
                jti=None,
                payload=BroadcastCreateIn(
                    template_name="aviso",
                    recipients=[{"phone": "+56912345678", "variables": {"nombre": "Ana"}}],
                ),
            )
    assert exc.value.status_code == 402


# ── R7: Stripe, simulated ────────────────────────────────────────────────────


class FakeStripe:
    """The provider calls the service makes, recorded."""

    def __init__(self) -> None:
        self.customers: list[uuid.UUID] = []
        self.sessions: list[str] = []
        self.expired: list[str] = []
        self.canceled: list[str] = []
        self.subscription: dict[str, Any] = {}
        # Links already paid (session -> subscription) and a Stripe that fails.
        self.paid: dict[str, str] = {}
        self.down = False

    def ensure_tenant_customer(self, *, tenant_id: uuid.UUID, name: str, email: str | None) -> str:
        self.customers.append(tenant_id)
        return f"cus_{tenant_id.hex[:8]}"

    def open_tenant_membership_session(self, **kwargs: Any) -> Any:
        sid = f"cs_{len(self.sessions) + 1}"
        self.sessions.append(sid)
        assert kwargs["success_url"].endswith("/pago-recibido")
        return stripe_membership.OpenedCheckout(
            url=f"https://checkout.stripe.test/{sid}",
            session_id=sid,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )

    def expire_checkout_session(self, session_id: str) -> str | None:
        if self.down:
            raise RuntimeError("stripe is down")
        if session_id in self.paid:
            return self.paid[session_id]
        self.expired.append(session_id)
        return None

    def retrieve_checkout_session(self, session_id: str) -> dict[str, Any]:
        return {"id": session_id, "subscription": self.subscription.get("id")}

    def retrieve_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self.subscription

    def cancel_subscription(self, subscription_id: str) -> None:
        self.canceled.append(subscription_id)
        self.subscription = {**self.subscription, "status": "canceled"}

    def open_invoice_url(self, subscription_id: str) -> str | None:
        return f"https://invoice.stripe.test/open/{subscription_id}"

    def list_subscription_invoices(self, subscription_id: str, *, limit: int = 24) -> list[Any]:
        now = int(datetime.now(UTC).timestamp())
        return [
            {
                "status": "paid",
                "amount_paid": 4000,
                "amount_due": 4000,
                "hosted_invoice_url": "https://invoice.stripe.test/1",
                "lines": {"data": [{"period": {"start": now, "end": now + 30 * 86400}}]},
            }
        ]


@pytest.fixture
def fake_stripe(monkeypatch) -> FakeStripe:
    fake = FakeStripe()
    for name in (
        "ensure_tenant_customer",
        "open_tenant_membership_session",
        "expire_checkout_session",
        "retrieve_checkout_session",
        "retrieve_subscription",
        "cancel_subscription",
        "list_subscription_invoices",
        "open_invoice_url",
    ):
        monkeypatch.setattr(stripe_membership, name, getattr(fake, name))
    return fake


def _sub(tenant_id: uuid.UUID, status: str, *, customer: str | None = None) -> dict[str, Any]:
    now = int(datetime.now(UTC).timestamp())
    return {
        "id": "sub_1",
        "status": status,
        "customer": customer or f"cus_{tenant_id.hex[:8]}",
        "metadata": {"kind": "tenant_membership", "tenant_id": str(tenant_id)},
        "items": {"data": [{"current_period_start": now, "current_period_end": now + 30 * 86400}]},
    }


async def test_stripe_flow_from_link_to_cut(client, db_session, admin_headers, fake_stripe) -> None:
    tid = await _tenant(db_session)
    headers, email = await _operator(db_session, admin_headers)
    put = await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "stripe", "amount_cents": 4000, "billing_email": "pagos@tecfin.test"},
        headers=headers,
    )
    assert put.json()["status"] == "pending"
    first = await client.post(f"/admin/tenants/{tid}/membership/checkout", headers=headers)
    second = await client.post(f"/admin/tenants/{tid}/membership/checkout", headers=headers)
    assert first.status_code == second.status_code == 200
    # Its own Stripe customer, once; a new link expires the previous one.
    assert fake_stripe.customers == [tid]
    assert fake_stripe.expired == ["cs_1"]
    # Tecfin pays: the refresh finds the subscription through the session.
    fake_stripe.subscription = _sub(tid, "active")
    refreshed = await client.post(f"/admin/tenants/{tid}/membership/refresh", headers=headers)
    assert refreshed.json()["status"] == "active"
    send_headers = await _key(db_session, tid)
    assert await _send(client, send_headers) == 202
    # A failed renewal: Stripe says past_due, and sends stop at once.
    fake_stripe.subscription = _sub(tid, "past_due")
    await client.post(f"/admin/tenants/{tid}/membership/refresh", headers=headers)
    assert await _send(client, send_headers) == 402
    # Paying a failed renewal is paying ITS invoice: no second subscription.
    sessions_before = list(fake_stripe.sessions)
    pay = await client.post(f"/admin/tenants/{tid}/membership/checkout", headers=headers)
    assert pay.json()["url"] == "https://invoice.stripe.test/open/sub_1"
    assert fake_stripe.sessions == sessions_before
    # Charges come from Stripe; the amount cannot change with a live subscription.
    charges = (await client.get(f"/admin/tenants/{tid}/membership/charges", headers=headers)).json()
    assert charges[0]["status"] == "paid"
    change = await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "stripe", "amount_cents": 5000},
        headers=headers,
    )
    assert change.status_code == 409
    assert change.json()["detail"] == "subscription_in_progress"
    # Archive is refused while live; cancel, then archive.
    assert (
        await client.post(f"/admin/tenants/{tid}/membership/archive", headers=headers)
    ).status_code == 409
    canceled = await client.post(f"/admin/tenants/{tid}/membership/cancel", headers=headers)
    assert canceled.json()["status"] == "canceled"
    assert fake_stripe.canceled == ["sub_1"]
    assert (
        await client.post(f"/admin/tenants/{tid}/membership/archive", headers=headers)
    ).status_code == 204
    assert await _send(client, send_headers) == 202  # no membership required any more
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        actors = set(
            (
                await s.scalars(
                    sa.select(AuditLog.actor).where(AuditLog.action.like("membership.%"))
                )
            ).all()
        )
    assert actors == {f"operator:{email}"}


async def test_changing_the_amount_expires_the_old_link(
    client, db_session, admin_headers, fake_stripe
) -> None:
    """A link for 40 must not be paid once the membership costs 50."""
    tid = await _tenant(db_session)
    headers, _ = await _operator(db_session, admin_headers)
    await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "stripe", "amount_cents": 4000, "billing_email": "p@t.test"},
        headers=headers,
    )
    await client.post(f"/admin/tenants/{tid}/membership/checkout", headers=headers)
    changed = await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "stripe", "amount_cents": 5000},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["checkout_url"] is None
    assert changed.json()["amount_cents"] == 5000
    assert fake_stripe.expired == ["cs_1"]


async def _stripe_membership_with_link(client, db_session, admin_headers, **tenant_kw):
    tid = await _tenant(db_session, **tenant_kw)
    headers, _ = await _operator(db_session, admin_headers)
    await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "stripe", "amount_cents": 4000, "billing_email": "p@t.test"},
        headers=headers,
    )
    link = await client.post(f"/admin/tenants/{tid}/membership/checkout", headers=headers)
    assert link.status_code == 200, link.text
    return tid, headers


async def test_a_link_stripe_cannot_expire_changes_nothing(
    client, db_session, admin_headers, fake_stripe
) -> None:
    """/cso 2026-11-24 (R7.13): the old link could still be paid at 40 while
    the membership says 50. Stripe down: 503 and nothing saved."""
    tid, headers = await _stripe_membership_with_link(client, db_session, admin_headers)
    fake_stripe.down = True
    changed = await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "stripe", "amount_cents": 5000},
        headers=headers,
    )
    assert changed.status_code == 503, changed.text
    row = await _row(tid)
    assert (row.amount_cents, row.checkout_url) == (4000, "https://checkout.stripe.test/cs_1")


async def test_changing_the_payer_archiving_or_canceling_expires_the_open_link(
    client, db_session, admin_headers, fake_stripe
) -> None:
    """R7.13: a link left open would start a subscription nothing follows."""
    pid = await _partner(db_session, purchased=100_000_000)
    tid, headers = await _stripe_membership_with_link(
        client, db_session, admin_headers, partner_id=pid
    )
    moved = await client.put(
        f"/admin/tenants/{tid}/membership",
        json={"payer": "partner_wallet", "amount_cents": 4000},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert fake_stripe.expired == ["cs_1"]
    assert moved.json()["checkout_url"] is None

    other, headers = await _stripe_membership_with_link(client, db_session, admin_headers)
    archived = await client.post(f"/admin/tenants/{other}/membership/archive", headers=headers)
    assert archived.status_code == 204, archived.text
    assert fake_stripe.expired == ["cs_1", "cs_2"]

    third, headers = await _stripe_membership_with_link(client, db_session, admin_headers)
    canceled = await client.post(f"/admin/tenants/{third}/membership/cancel", headers=headers)
    assert canceled.status_code == 200, canceled.text
    assert fake_stripe.expired == ["cs_1", "cs_2", "cs_3"]


async def test_no_new_link_when_the_old_one_was_already_paid(
    client, db_session, admin_headers, fake_stripe
) -> None:
    """/cso 2026-11-24 (R7.14): the notice of the payment is late and the
    operator asks for another link. Two paid links are two subscriptions."""
    tid, headers = await _stripe_membership_with_link(client, db_session, admin_headers)
    fake_stripe.paid["cs_1"] = "sub_1"
    fake_stripe.subscription = _sub(tid, "active")
    again = await client.post(f"/admin/tenants/{tid}/membership/checkout", headers=headers)
    assert again.status_code == 409, again.text
    assert again.json()["detail"] == "checkout_already_paid"
    assert fake_stripe.sessions == ["cs_1"]
    row = await _row(tid)
    assert (row.status, row.stripe_subscription_id) == ("active", "sub_1")


async def test_canceling_with_a_paid_link_cancels_that_subscription_too(
    client, db_session, admin_headers, fake_stripe
) -> None:
    """R7.13-R7.14: cancel finds the payment the notice never brought, and
    cancels it, so nothing keeps charging the client."""
    tid, headers = await _stripe_membership_with_link(client, db_session, admin_headers)
    fake_stripe.paid["cs_1"] = "sub_1"
    fake_stripe.subscription = _sub(tid, "active")
    canceled = await client.post(f"/admin/tenants/{tid}/membership/cancel", headers=headers)
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "canceled"
    assert fake_stripe.canceled == ["sub_1"]


async def test_two_wallet_charges_at_once_take_one_fee(db_session) -> None:
    """Security review (HIGH): the cron and «Cobrar ahora» at the same time
    read the same period under the row lock, so the book charges once."""
    import asyncio

    pid = await _partner(db_session, purchased=_FEE * 3)
    tid = await _tenant(db_session, partner_id=pid)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(ServiceMembership(tenant_id=tid, payer="partner_wallet", amount_cents=4000))
    results = await asyncio.gather(
        memberships.charge_wallet_if_due(tid, force=True),
        memberships.charge_wallet_if_due(tid, force=True),
        memberships.charge_wallet_if_due(tid, force=True),
    )
    assert any(results)
    assert await _purchased(pid) == _FEE * 2
    assert (await _row(tid)).status == "active"


async def test_a_renewal_tried_early_without_balance_keeps_the_paid_period(db_session) -> None:
    """Security review (LOW): the hour before the end is still paid for."""
    pid = await _partner(db_session, purchased=0)
    tid = await _tenant(db_session, partner_id=pid)
    end = datetime.now(UTC) + timedelta(minutes=30)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(
            ServiceMembership(
                tenant_id=tid,
                payer="partner_wallet",
                amount_cents=4000,
                status="active",
                current_period_end=end,
            )
        )
    assert await memberships.charge_wallet_if_due(tid) is False
    row = await _row(tid)
    assert (row.status, row.last_failure) == ("active", "insufficient_balance")
    assert await memberships.charge_wallet_if_due(tid, now=end + timedelta(minutes=1)) is False
    assert (await _row(tid)).status == "past_due"


async def test_an_older_subscription_of_the_same_customer_changes_nothing(db_session) -> None:
    """Security review (MEDIUM): once a subscription is stored, another one of
    the same customer only replaces it through the current payment link."""
    tid = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(
            ServiceMembership(
                tenant_id=tid,
                payer="stripe",
                amount_cents=4000,
                status="active",
                stripe_customer_id=f"cus_{tid.hex[:8]}",
                stripe_subscription_id="sub_current",
                stripe_checkout_session_id="cs_current",
            )
        )
    old = {**_sub(tid, "canceled"), "id": "sub_old"}

    class Client:
        class subscriptions:  # noqa: N801
            @staticmethod
            def retrieve(_id: str) -> dict[str, Any]:
                return old

    assert await memberships.apply_stripe_event(
        Client, "customer.subscription.deleted", {"object_id": "sub_old"}
    )
    row = await _row(tid)
    assert (row.status, row.stripe_subscription_id) == ("active", "sub_current")


async def test_stripe_event_applies_only_to_its_client(db_session, fake_stripe) -> None:
    """R7.5: a subscription whose customer is not the client's own changes nothing."""
    a = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, a):
        s.add(
            ServiceMembership(
                tenant_id=a, payer="stripe", amount_cents=4000, stripe_customer_id="cus_real"
            )
        )

    class Client:
        class subscriptions:  # noqa: N801
            @staticmethod
            def retrieve(_id: str) -> dict[str, Any]:
                return _sub(a, "active", customer="cus_someone_else")

    handled = await memberships.apply_stripe_event(
        Client, "customer.subscription.updated", {"object_id": "sub_1"}
    )
    assert handled is True  # ours by its mark, never sent to the partners' path
    assert (await _row(a)).status == "pending"


async def test_stripe_state_comes_from_the_subscription_not_the_event(db_session) -> None:
    """Advisor 3: a payment_failed notice that arrives after the card was paid
    leaves what Stripe says now."""
    tid = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(
            ServiceMembership(
                tenant_id=tid,
                payer="stripe",
                amount_cents=4000,
                stripe_customer_id=f"cus_{tid.hex[:8]}",
            )
        )

    class Client:
        class invoices:  # noqa: N801
            @staticmethod
            def retrieve(_id: str) -> dict[str, Any]:
                return {"id": "in_1", "subscription": "sub_1"}

        class subscriptions:  # noqa: N801
            @staticmethod
            def retrieve(_id: str) -> dict[str, Any]:
                return _sub(tid, "active")

    assert await memberships.apply_stripe_event(
        Client, "invoice.payment_failed", {"object_id": "in_1"}
    )
    assert (await _row(tid)).status == "active"


async def test_a_partners_notice_is_not_taken(db_session) -> None:
    """R11.2: an object without our mark goes down the partners' path."""

    class Client:
        class subscriptions:  # noqa: N801
            @staticmethod
            def retrieve(_id: str) -> dict[str, Any]:
                return {"id": "sub_p", "status": "active", "metadata": {"partner_id": "x"}}

    assert (
        await memberships.apply_stripe_event(
            Client, "customer.subscription.updated", {"object_id": "sub_p"}
        )
        is False
    )


async def test_tick_charges_due_wallets_and_rereads_stripe_hourly(
    db_session, fake_stripe, monkeypatch
) -> None:
    pid = await _partner(db_session, purchased=_FEE)
    wallet_tid = await _tenant(db_session, partner_id=pid)
    stripe_tid = await _tenant(db_session)
    now = datetime.now(UTC)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, wallet_tid):
        s.add(
            ServiceMembership(
                tenant_id=wallet_tid,
                payer="partner_wallet",
                amount_cents=4000,
                status="active",
                current_period_end=now + timedelta(minutes=20),
            )
        )
    async with get_sessionmaker()() as s, tenant_scoped_session(s, stripe_tid):
        s.add(
            ServiceMembership(
                tenant_id=stripe_tid,
                payer="stripe",
                amount_cents=4000,
                status="pending",
                stripe_customer_id=f"cus_{stripe_tid.hex[:8]}",
                stripe_checkout_session_id="cs_9",
            )
        )
    monkeypatch.setattr(
        "nexus_api.config.Settings.billing_enabled", property(lambda _self: True), raising=False
    )
    fake_stripe.subscription = _sub(stripe_tid, "active")
    reads: list[str] = []
    original = fake_stripe.retrieve_checkout_session

    def _counting(session_id: str) -> dict[str, Any]:
        reads.append(session_id)
        return original(session_id)

    monkeypatch.setattr(stripe_membership, "retrieve_checkout_session", _counting)
    await memberships.tick(now=now)
    assert (await _row(wallet_tid)).current_period_end > now + timedelta(days=27)
    assert await _purchased(pid) == 0
    assert (await _row(stripe_tid)).status == "active"
    # Within the hour, no second read.
    await memberships.tick(now=now + timedelta(minutes=10))
    assert reads == ["cs_9"]
