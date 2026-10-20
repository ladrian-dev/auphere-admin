"""Spec 041 — the partner's card, automatic recharge and postpaid.

Only Stripe is faked. The wallet, the ledger, the credit-line CHECK, the
charge rows and the reconciliation run against the database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.billing.pricing import CREDITS_PER_CENT
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Partner, PartnerBilling, PartnerCharge, PartnerWallet
from nexus_api.metering.wallet import (
    add_purchased,
    allow_channel_turn,
    debit_wallet,
    reconcile_purchased,
)
from nexus_api.services import partner_billing as pb

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


class _Ns:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class _FakeStripe:
    """What the billing service asks of Stripe, and nothing else."""

    def __init__(self, *, decline: bool = False, sca: bool = False) -> None:
        self.decline = decline
        #: The bank asks for 3D Secure: off-session payment cannot finish.
        self.sca = sca
        self.invoices_paid: list[dict[str, Any]] = []
        self._items: list[dict[str, Any]] = []
        outer = self

        class _Customers:
            def create(self, params, options=None):
                return {"id": "cus_test"}

            def update(self, customer_id, params):
                outer.default_pm = params["invoice_settings"]["default_payment_method"]
                return {"id": customer_id}

        class _Sessions:
            def create(self, params, options=None):
                outer.setup_params = params
                return {"id": "cs_setup", "url": "https://checkout.stripe.test/setup"}

        class _Checkout:
            sessions = _Sessions()

        class _SetupIntents:
            def retrieve(self, sid, params=None):
                return {
                    "id": sid,
                    "payment_method": {
                        "id": "pm_test",
                        "card": {
                            "brand": "visa",
                            "last4": "4242",
                            "exp_month": 12,
                            "exp_year": 2030,
                        },
                    },
                }

        class _PaymentMethods:
            def detach(self, pm):
                outer.detached = pm

            def retrieve(self, pm):
                outer.retrieved_pm = pm
                return {
                    "id": pm,
                    "type": "card",
                    "card": {
                        "brand": "mastercard",
                        "last4": "4444",
                        "exp_month": 3,
                        "exp_year": 2031,
                    },
                }

        class _Items:
            def create(self, params, options=None):
                outer._items.append(params)
                return {"id": f"ii_{len(outer._items)}"}

        class _Invoices:
            def create(self, params, options=None):
                outer._open = {"id": f"in_{uuid.uuid4().hex[:8]}", "metadata": params["metadata"]}
                return outer._open

            def finalize_invoice(self, iid):
                return {"id": iid}

            def retrieve(self, iid, params=None):
                return {"id": iid, "hosted_invoice_url": f"https://invoice.stripe.test/{iid}"}

            def search(self, params):
                outer.searched = params["query"]
                found = {
                    "id": "in_found",
                    "hosted_invoice_url": "https://invoice.stripe.test/in_found",
                }
                return {"data": [found] if getattr(outer, "searchable", False) else []}

            def pay(self, iid, params=None):
                if outer.sca:
                    err = RuntimeError("This payment requires authentication.")
                    err.code = "authentication_required"  # type: ignore[attr-defined]
                    raise err
                if outer.decline:
                    err = RuntimeError("Your card was declined.")
                    err.code = "card_declined"  # type: ignore[attr-defined]
                    raise err
                amount = outer._items[-1]["amount"]
                paid = {
                    "id": iid,
                    "status": "paid",
                    "amount_paid": amount,
                    "metadata": outer._open["metadata"],
                }
                outer.invoices_paid.append(paid)
                return paid

        self.customers = _Customers()
        self.checkout = _Checkout()
        self.setup_intents = _SetupIntents()
        self.payment_methods = _PaymentMethods()
        self.invoice_items = _Items()
        self.invoices = _Invoices()


async def _partner(partner_id: uuid.UUID) -> Partner:
    async with get_sessionmaker()() as s, s.begin():
        p = await s.get(Partner, partner_id)
        assert p is not None
        s.expunge(p)
        return p


async def _save_card(partner_id: uuid.UUID, fake: _FakeStripe) -> None:
    async with get_sessionmaker()() as s, s.begin():
        url = await pb.open_card_setup(s, await _partner(partner_id))
    assert url == "https://checkout.stripe.test/setup"
    assert fake.setup_params["mode"] == "setup"
    # Stripe refuses payment_method_types on Checkout now; setup mode needs currency.
    assert "payment_method_types" not in fake.setup_params
    assert fake.setup_params["currency"] == "usd"
    async with get_sessionmaker()() as s, s.begin():
        await pb.apply_card_saved(
            s,
            partner_id=partner_id,
            checkout={"setup_intent": "seti_1", "customer": "cus_test", "mode": "setup"},
        )


async def _balance(partner_id: uuid.UUID) -> int:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        w = await s.get(PartnerWallet, partner_id)
        return int(w.purchased_remaining) if w else 0


async def _set(partner_id: uuid.UUID, **values: Any) -> None:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        await s.execute(
            sa.update(PartnerWallet).where(PartnerWallet.partner_id == partner_id).values(**values)
        )


async def _charges(partner_id: uuid.UUID) -> list[PartnerCharge]:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        rows = (await s.execute(sa.select(PartnerCharge))).scalars().all()
        for r in rows:
            s.expunge(r)
        return list(rows)


async def test_card_then_automatic_recharge(console_world, monkeypatch) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    fake = _FakeStripe()
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    await _set(pid, purchased_remaining=0)

    # Without a card, nothing automatic.
    async with get_sessionmaker()() as s, s.begin():
        with pytest.raises(pb.BillingRuleError) as no_card:
            await pb.set_charging(
                s,
                partner_id=pid,
                mode="auto_recharge",
                threshold_cents=1000,
                amount_cents=2000,
                actor="t",
            )
    assert no_card.value.code == "card_required"

    await _save_card(pid, fake)
    assert fake.default_pm == "pm_test"
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        billing = await s.get(PartnerBilling, pid)
        assert billing is not None and billing.card_last4 == "4242"
        await pb.set_charging(
            s,
            partner_id=pid,
            mode="auto_recharge",
            threshold_cents=1000,
            amount_cents=2000,
            actor="t",
        )

    # US$5 bought by hand: below the US$10 threshold → one recharge of US$20.
    await add_purchased(
        pid, 500 * CREDITS_PER_CENT, kind="credit_admin", idempotency_key=f"t:{uuid.uuid4()}"
    )
    out = await pb.run_auto_recharges()
    assert [o.status for o in out] == ["paid"]
    assert await _balance(pid) == 2500 * CREDITS_PER_CENT

    # Above the threshold now: nothing more.
    assert await pb.run_auto_recharges() == []
    # The webhook arriving later credits nothing twice.
    assert await pb.settle_paid_invoice(pid, fake.invoices_paid[0]) is False
    assert await _balance(pid) == 2500 * CREDITS_PER_CENT

    rec = await reconcile_purchased(pid)
    assert rec is not None and rec.balanced


async def test_postpaid_credit_line_and_monthly_settlement(console_world, monkeypatch) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    fake = _FakeStripe()
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    await _set(pid, purchased_remaining=0)
    await _save_card(pid, fake)

    async with get_sessionmaker()() as s, s.begin():
        with pytest.raises(pb.BillingRuleError) as no_line:
            await pb.set_charging(
                s,
                partner_id=pid,
                mode="postpaid",
                threshold_cents=None,
                amount_cents=None,
                actor="t",
            )
    assert no_line.value.code == "no_credit_line"

    async with get_sessionmaker()() as s, s.begin():
        await pb.set_credit_limit(s, partner_id=pid, credit_limit_cents=5000, actor="operator:x")
        await pb.set_charging(
            s, partner_id=pid, mode="postpaid", threshold_cents=None, amount_cents=None, actor="t"
        )

    # Consumption beyond zero, inside the line: the client keeps being served.
    spent = await debit_wallet(
        partner_id=pid,
        tenant_id=None,
        qty=1234 * CREDITS_PER_CENT + 7,
        idempotency_key=f"t:{uuid.uuid4()}",
        allow_included=False,
    )
    assert spent.from_purchased == 1234 * CREDITS_PER_CENT + 7
    assert await _balance(pid) == -(1234 * CREDITS_PER_CENT + 7)

    # Never past the line: the debit takes only what is left of it.
    rest = await debit_wallet(
        partner_id=pid,
        tenant_id=None,
        qty=10_000 * CREDITS_PER_CENT,
        idempotency_key=f"t:{uuid.uuid4()}",
        allow_included=False,
    )
    assert await _balance(pid) == -5000 * CREDITS_PER_CENT
    assert rest.from_purchased == 5000 * CREDITS_PER_CENT - (1234 * CREDITS_PER_CENT + 7)

    # Withdrawing the line below the debt is refused.
    async with get_sessionmaker()() as s, s.begin():
        with pytest.raises(pb.BillingRuleError) as below:
            await pb.set_credit_limit(s, partner_id=pid, credit_limit_cents=100, actor="operator:x")
    assert below.value.code == "limit_below_debt"

    # The 1st: the debt is charged and the balance returns to zero.
    out = await pb.run_postpaid_settlement(datetime(2026, 11, 1, 6, tzinfo=UTC))
    assert [o.status for o in out] == ["paid"]
    assert fake._items[-1]["amount"] == 5000
    assert fake._items[-1]["description"] == "Consumo de 2026-10"
    assert await _balance(pid) == 0
    # The same month again charges nothing.
    again = await pb.run_postpaid_settlement(datetime(2026, 11, 1, 9, tzinfo=UTC))
    assert [o.status for o in again] == []

    rec = await reconcile_purchased(pid)
    assert rec is not None and rec.balanced


async def test_a_declined_card_stops_after_three_attempts(console_world, monkeypatch) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    fake = _FakeStripe(decline=True)
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    await _set(pid, purchased_remaining=0)
    await _save_card(pid, fake)
    async with get_sessionmaker()() as s, s.begin():
        await pb.set_charging(
            s,
            partner_id=pid,
            mode="auto_recharge",
            threshold_cents=1000,
            amount_cents=2000,
            actor="t",
        )
    for _ in range(3):
        out = await pb.run_auto_recharges()
        assert [o.status for o in out] == ["failed"]
    assert await pb.run_auto_recharges() == []  # paused
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        billing = await s.get(PartnerBilling, pid)
        assert billing is not None and billing.paused_reason == "card_declined"
    assert {c.status for c in await _charges(pid)} == {"failed"}
    assert await _balance(pid) == 0

    # A new card is a fresh start.
    fake.decline = False
    await _save_card(pid, fake)
    out = await pb.run_auto_recharges()
    assert [o.status for o in out] == ["paid"]


async def test_prepaid_partners_still_stop_at_zero(console_world) -> None:
    a = console_world["a"]
    await _set(a["partner_id"], purchased_remaining=0, credit_limit=0)
    assert await allow_channel_turn(a["tenant_id"]) is False


async def test_the_screens_read_and_set_it(
    client, console_world, admin_headers, db_session, monkeypatch
) -> None:
    from nexus_api.config import get_settings
    from nexus_api.services import operator_identity

    a, b = console_world["a"], console_world["b"]
    pid = a["partner_id"]
    await _set(pid, purchased_remaining=0)

    # Without Stripe keys the card page is a 503, not a 500.
    monkeypatch.setattr(get_settings(), "billing_api_key", "", raising=False)
    closed = await client.post("/console/billing/card", headers=a["headers"]())
    assert closed.status_code == 503
    assert closed.json()["detail"]["code"] == "billing_unavailable"

    view = await client.get("/console/billing/card", headers=a["headers"]())
    assert view.status_code == 200, view.text
    assert view.json()["card"] is None and view.json()["mode"] == "manual"
    refused = await client.put(
        "/console/billing/charging", headers=a["headers"](), json={"mode": "postpaid"}
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "card_required"

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    line = await client.put(
        f"/admin/partners/{pid}/credit-limit",
        headers={**admin_headers, "X-Operator-Id": str(account.id)},
        json={"credit_limit_cents": 20000},
    )
    assert line.status_code == 200, line.text
    assert line.json()["credit_limit_cents"] == 20000
    seen = await client.get(f"/admin/partners/{pid}/billing", headers=admin_headers)
    assert seen.json()["credit_limit_cents"] == 20000
    # Another partner's line is untouched.
    other = await client.get(f"/admin/partners/{b['partner_id']}/billing", headers=admin_headers)
    assert other.json()["credit_limit_cents"] == 0
    # The operator's line needs the operator.
    anon = await client.put(
        f"/admin/partners/{pid}/credit-limit", headers=admin_headers, json={"credit_limit_cents": 1}
    )
    assert anon.status_code == 400


async def test_the_operator_sets_charging_and_sees_the_card(
    client, console_world, admin_headers, db_session, monkeypatch
) -> None:
    from nexus_api.services import operator_identity

    a = console_world["a"]
    pid = a["partner_id"]
    fake = _FakeStripe()
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    op = {**admin_headers, "X-Operator-Id": str(account.id)}
    body = {
        "mode": "auto_recharge",
        "recharge_threshold_cents": 1000,
        "recharge_amount_cents": 2000,
    }

    # Before the partner saves a card, only manual.
    early = await client.put(f"/admin/partners/{pid}/charging", headers=op, json=body)
    assert early.status_code == 422
    assert early.json()["detail"]["code"] == "card_required"

    await _save_card(pid, fake)
    done = await client.put(f"/admin/partners/{pid}/charging", headers=op, json=body)
    assert done.status_code == 200, done.text
    assert done.json()["mode"] == "auto_recharge"
    assert done.json()["card"]["last4"] == "4242"
    assert done.json()["card"]["saved_at"] is not None

    # The list of partners says it, and the Panel shows the new card.
    listed = await client.get("/admin/partners", headers=admin_headers)
    row = next(r for r in listed.json() if r["id"] == str(pid))
    assert row["card_last4"] == "4242"
    assert row["billing_mode"] == "auto_recharge"
    assert row["charges_paused"] is False
    overview = await client.get("/admin/overview", headers=admin_headers)
    assert str(pid) in {c["partner_id"] for c in overview.json()["cards_added"]}

    # Without the operator it is refused.
    anon = await client.put(f"/admin/partners/{pid}/charging", headers=admin_headers, json=body)
    assert anon.status_code == 400


async def test_a_card_that_asks_for_3d_secure_waits_for_the_partner(
    console_world, monkeypatch
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    fake = _FakeStripe(sca=True)
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    sent: list[dict] = []

    async def capture(**kw):
        sent.append(kw)

    monkeypatch.setattr(pb, "_send_action_email", capture)
    async with get_sessionmaker()() as s, s.begin():
        await s.execute(
            sa.update(Partner)
            .where(Partner.id == pid)
            .values(billing_email="facturas@partner-a.example")
        )
    await _set(pid, purchased_remaining=0)
    await _save_card(pid, fake)
    async with get_sessionmaker()() as s, s.begin():
        await pb.set_charging(
            s,
            partner_id=pid,
            mode="auto_recharge",
            threshold_cents=1000,
            amount_cents=2000,
            actor="t",
        )

    out = await pb.run_auto_recharges()
    assert [o.status for o in out] == ["action_required"]
    charge = (await _charges(pid))[0]
    assert charge.status == "action_required"
    assert charge.action_url and charge.action_url.startswith("https://invoice.stripe.test/")
    assert sent and sent[0]["url"] == charge.action_url
    assert sent[0]["to"] == "facturas@partner-a.example"
    # Not a decline: no attempt counted, and no second charge while it waits.
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        billing = await s.get(PartnerBilling, pid)
        assert billing is not None and billing.failed_attempts == 0
    assert await pb.run_auto_recharges() == []

    # The partner confirms on Stripe's page; invoice.paid settles it.
    paid = {
        "id": charge.stripe_invoice_id,
        "status": "paid",
        "amount_paid": 2000,
        "metadata": {"partner_id": str(pid), "kind": "auto_recharge", "charge_id": str(charge.id)},
    }
    assert await pb.settle_paid_invoice(pid, paid) is True
    assert await _balance(pid) == 2000 * CREDITS_PER_CENT
    assert (await _charges(pid))[0].status == "paid"


async def test_a_failed_postpaid_charge_freezes_the_line_until_paid(
    console_world, monkeypatch
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    fake = _FakeStripe(decline=True)
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    await _set(pid, purchased_remaining=0)
    await _save_card(pid, fake)
    async with get_sessionmaker()() as s, s.begin():
        await pb.set_credit_limit(s, partner_id=pid, credit_limit_cents=5000, actor="operator:x")
        await pb.set_charging(
            s, partner_id=pid, mode="postpaid", threshold_cents=None, amount_cents=None, actor="t"
        )
    await debit_wallet(
        partner_id=pid,
        tenant_id=None,
        qty=1000 * CREDITS_PER_CENT,
        idempotency_key=f"t:{uuid.uuid4()}",
        allow_included=False,
    )

    out = await pb.run_postpaid_settlement(datetime(2026, 11, 1, 6, tzinfo=UTC))
    assert [o.status for o in out] == ["failed"]
    # Frozen at what is owed: nothing more on credit.
    more = await debit_wallet(
        partner_id=pid,
        tenant_id=None,
        qty=10 * CREDITS_PER_CENT,
        idempotency_key=f"t:{uuid.uuid4()}",
        allow_included=False,
    )
    assert more.spent == 0
    view = await pb.billing_view(pid)
    assert view.credit_frozen is True
    assert view.credit_limit_cents == 5000  # what Auphere granted, kept

    # Not again the same day; once the next day.
    assert await pb.run_postpaid_settlement(datetime(2026, 11, 1, 9, tzinfo=UTC)) == []
    fake.decline = False
    out = await pb.run_postpaid_settlement(datetime(2026, 11, 2, 6, tzinfo=UTC))
    assert [o.status for o in out] == ["paid"]
    assert await _balance(pid) == 0
    view = await pb.billing_view(pid)
    assert view.credit_frozen is False
    # The line is back: consumption on credit works again.
    again = await debit_wallet(
        partner_id=pid,
        tenant_id=None,
        qty=10 * CREDITS_PER_CENT,
        idempotency_key=f"t:{uuid.uuid4()}",
        allow_included=False,
    )
    assert again.spent == 10 * CREDITS_PER_CENT
    rec = await reconcile_purchased(pid)
    assert rec is not None and rec.balanced


async def test_a_stripe_refusal_reaches_the_screen_with_its_reason(
    client, console_world, monkeypatch
) -> None:
    """In staging «Añadir tarjeta» answered a bare 500 and nobody could tell
    why. A refused call is a 502 that names Stripe's code and message."""
    import stripe

    a = console_world["a"]

    class _Refusing(_FakeStripe):
        def __init__(self) -> None:
            super().__init__()

            def refuse(*_a: Any, **_k: Any) -> Any:
                raise stripe.InvalidRequestError(
                    "No such price", param="currency", code="parameter_invalid_empty"
                )

            self.customers.create = refuse

    monkeypatch.setattr(pb, "get_client", lambda: _Refusing())
    res = await client.post("/console/billing/card", headers=a["headers"]())
    assert res.status_code == 502, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "billing_provider_error"
    assert detail["provider_code"] == "parameter_invalid_empty"
    assert detail["message"] == "No such price"
    # Nothing was half-saved: no customer id without a card page.
    view = await client.get("/console/billing/card", headers=a["headers"]())
    assert view.json()["card"] is None


async def _billing(partner_id: uuid.UUID) -> PartnerBilling:
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, partner_id)
        row = await s.get(PartnerBilling, partner_id)
        assert row is not None
        s.expunge(row)
        return row


async def test_a_saved_method_without_card_details_is_read_again(
    console_world, monkeypatch
) -> None:
    """Staging saved a method and showed «terminada en · caduca 00/»: the
    details were not in what Checkout handed back."""
    pid = console_world["a"]["partner_id"]
    fake = _FakeStripe()
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    async with get_sessionmaker()() as s, s.begin():
        await pb.apply_card_saved(
            s,
            partner_id=pid,
            checkout={
                "customer": "cus_test",
                "setup_intent": {"id": "seti_2", "payment_method": {"id": "pm_bare"}},
            },
        )
    assert fake.retrieved_pm == "pm_bare"
    row = await _billing(pid)
    assert (row.card_brand, row.card_last4, row.card_exp_month) == ("mastercard", "4444", 3)


async def test_a_link_method_is_named_not_left_blank(console_world, monkeypatch) -> None:
    pid = console_world["a"]["partner_id"]
    fake = _FakeStripe()
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    async with get_sessionmaker()() as s, s.begin():
        await pb.apply_card_saved(
            s,
            partner_id=pid,
            checkout={
                "customer": "cus_test",
                "setup_intent": {
                    "id": "seti_3",
                    "payment_method": {"id": "pm_link", "type": "link", "link": {}},
                },
            },
        )
    assert not hasattr(fake, "retrieved_pm")
    row = await _billing(pid)
    assert row.card_brand == "link" and row.card_last4 is None
    assert row.payment_method_id == "pm_link"


async def test_each_card_charge_opens_its_stripe_invoice(
    client, console_world, admin_headers, monkeypatch
) -> None:
    """The owner asked to see the invoices of the automatic top-ups
    (2026-10-20): paid and declined alike, never another partner's."""
    a, b = console_world["a"], console_world["b"]
    pid = a["partner_id"]
    fake = _FakeStripe(decline=True)
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    await _set(pid, purchased_remaining=0)
    await _save_card(pid, fake)
    async with get_sessionmaker()() as s, s.begin():
        await pb.set_charging(
            s,
            partner_id=pid,
            mode="auto_recharge",
            threshold_cents=1000,
            amount_cents=2000,
            actor="t",
        )
    await pb.run_auto_recharges()
    declined = (await _charges(pid))[0]
    assert declined.status == "failed"
    # The declined invoice is kept: the partner can see (and pay) it in Stripe.
    assert declined.stripe_invoice_id

    view = await client.get("/console/billing/card", headers=a["headers"]())
    assert view.json()["charges"][0]["has_invoice"] is True
    res = await client.get(
        f"/console/billing/charges/{declined.id}/invoice", headers=a["headers"]()
    )
    assert res.status_code == 200, res.text
    assert res.json()["url"] == f"https://invoice.stripe.test/{declined.stripe_invoice_id}"

    # Auphere sees the same page from the Admin.
    op = await client.get(
        f"/admin/partners/{pid}/charges/{declined.id}/invoice", headers=admin_headers
    )
    assert op.status_code == 200, op.text
    assert op.json()["url"] == res.json()["url"]

    # Partner B cannot open A's invoice, and the answer does not say it exists.
    other = await client.get(
        f"/console/billing/charges/{declined.id}/invoice", headers=b["headers"]()
    )
    assert other.status_code == 404
    assert other.json()["detail"]["code"] == "unknown_charge"
    wrong = await client.get(
        f"/admin/partners/{b['partner_id']}/charges/{declined.id}/invoice", headers=admin_headers
    )
    assert wrong.status_code == 404


async def test_an_old_charge_without_the_id_is_found_by_its_metadata(
    client, console_world, monkeypatch
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    fake = _FakeStripe(decline=True)
    monkeypatch.setattr(pb, "get_client", lambda: fake)
    await _set(pid, purchased_remaining=0)
    await _save_card(pid, fake)
    async with get_sessionmaker()() as s, s.begin():
        await pb.set_charging(
            s,
            partner_id=pid,
            mode="auto_recharge",
            threshold_cents=1000,
            amount_cents=2000,
            actor="t",
        )
    await pb.run_auto_recharges()
    charge = (await _charges(pid))[0]
    # As the declined charges recorded before this change were.
    async with get_sessionmaker()() as s, s.begin():
        await apply_partner_to_session(s, pid)
        row = await s.get(PartnerCharge, charge.id)
        assert row is not None
        row.stripe_invoice_id = None

    missing = await client.get(
        f"/console/billing/charges/{charge.id}/invoice", headers=a["headers"]()
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "no_invoice"

    fake.searchable = True
    found = await client.get(
        f"/console/billing/charges/{charge.id}/invoice", headers=a["headers"]()
    )
    assert found.status_code == 200, found.text
    assert found.json()["url"] == "https://invoice.stripe.test/in_found"
    assert fake.searched == f"metadata['charge_id']:'{charge.id}'"
    # Found once, kept: the next click goes straight to it.
    assert (await _charges(pid))[0].stripe_invoice_id == "in_found"
