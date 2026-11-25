"""Spec 077 · lo que se le pide a Stripe para la membresía de un cliente.

Se ejecuta ``billing/tenant_membership`` de verdad contra un cliente que graba
las llamadas: los parámetros son el contrato con Stripe (sin
``client_reference_id``, la marca en la sesión y en la suscripción, precio
mensual en línea, claves de idempotencia por cliente). La primera llamada real
a Stripe se hace en staging.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.billing import tenant_membership as tm


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, dict[str, Any]]] = []
        self.customers = self._Endpoint(self, "customers.create", {"id": "cus_1"})
        self.checkout = type("C", (), {})()
        self.checkout.sessions = self._Sessions(self)
        self.invoices = self._Endpoint(
            self, "invoices.list", {"data": [{"hosted_invoice_url": "https://inv/1"}]}
        )

    class _Endpoint:
        def __init__(self, rec: _Recorder, name: str, answer: dict[str, Any]) -> None:
            self.rec, self.name, self.answer = rec, name, answer

        def create(self, params: Any, options: dict[str, Any] | None = None) -> Any:
            self.rec.calls.append((self.name, params, options or {}))
            return self.answer

        def list(self, params: Any) -> Any:
            self.rec.calls.append((self.name, params, {}))
            return self.answer

    class _Sessions:
        def __init__(self, rec: _Recorder) -> None:
            self.rec = rec
            self.status = "open"
            self.subscription: str | None = None

        def create(self, params: Any, options: dict[str, Any] | None = None) -> Any:
            self.rec.calls.append(("checkout.sessions.create", params, options or {}))
            return {"id": "cs_1", "url": "https://checkout/cs_1", "expires_at": 1_800_000_000}

        def retrieve(self, sid: str) -> Any:
            self.rec.calls.append(("checkout.sessions.retrieve", sid, {}))
            return {"id": sid, "status": self.status, "subscription": self.subscription}

        def expire(self, sid: str) -> Any:
            self.rec.calls.append(("checkout.sessions.expire", sid, {}))
            return {"id": sid}


@pytest.fixture
def rec(monkeypatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(tm, "get_client", lambda: recorder)
    return recorder


def test_the_customer_is_the_clients_own_and_idempotent(rec) -> None:
    tid = uuid.uuid4()
    assert tm.ensure_tenant_customer(tenant_id=tid, name="Tecfin", email="p@t.test") == "cus_1"
    name, params, options = rec.calls[0]
    assert name == "customers.create"
    assert params["metadata"] == {"kind": "tenant_membership", "tenant_id": str(tid)}
    assert str(tid) in options["idempotency_key"]


def test_the_session_is_a_monthly_subscription_marked_on_both_sides(rec) -> None:
    tid = uuid.uuid4()
    opened = tm.open_tenant_membership_session(
        tenant_id=tid,
        customer_id="cus_1",
        amount_cents=4000,
        product_name="Membresía de envío · Tecfin",
        success_url="https://c/pago-recibido",
        cancel_url="https://c/pago-recibido?estado=cancelado",
        stamp="s1",
    )
    assert (opened.session_id, opened.url) == ("cs_1", "https://checkout/cs_1")
    assert opened.expires_at is not None
    _name, params, options = rec.calls[0]
    assert params["mode"] == "subscription"
    # Never a partner reference: the webhook would read it as a partner id.
    assert "client_reference_id" not in params
    mark = {"kind": "tenant_membership", "tenant_id": str(tid)}
    assert params["metadata"] == mark
    assert params["subscription_data"] == {"metadata": mark}
    price = params["line_items"][0]["price_data"]
    assert (price["currency"], price["unit_amount"], price["recurring"]) == (
        "usd",
        4000,
        {"interval": "month"},
    )
    # Each link its own key: a second link must not replay the first.
    second = tm.open_tenant_membership_session(
        tenant_id=tid,
        customer_id="cus_1",
        amount_cents=4000,
        product_name="x",
        success_url="s",
        cancel_url="c",
        stamp="s2",
    )
    assert second.session_id == "cs_1"
    assert rec.calls[1][2]["idempotency_key"] != options["idempotency_key"]


def test_only_an_open_session_is_expired_and_a_paid_one_says_so(rec) -> None:
    assert tm.expire_checkout_session("cs_open") is None
    rec.checkout.sessions.status = "complete"
    rec.checkout.sessions.subscription = "sub_9"
    # Paid without the notice arriving: the caller learns which subscription.
    assert tm.expire_checkout_session("cs_done") == "sub_9"
    rec.checkout.sessions.status = "expired"
    assert tm.expire_checkout_session("cs_old") is None
    names = [c[0] for c in rec.calls]
    assert names.count("checkout.sessions.expire") == 1


def test_a_failed_renewal_is_paid_on_its_open_invoice(rec) -> None:
    assert tm.open_invoice_url("sub_1") == "https://inv/1"
    _name, params, _ = rec.calls[0]
    assert params == {"subscription": "sub_1", "status": "open", "limit": 1}


def test_reading_period_invoice_and_mark() -> None:
    sub_new = {"items": {"data": [{"current_period_start": 1, "current_period_end": 2}]}}
    sub_old = {"current_period_start": 3, "current_period_end": 4, "items": {"data": []}}
    assert [d.timestamp() for d in tm.subscription_period(sub_new)] == [1, 2]
    assert [d.timestamp() for d in tm.subscription_period(sub_old)] == [3, 4]
    assert tm.subscription_of_invoice({"subscription": "sub_a"}) == "sub_a"
    nested = {"parent": {"subscription_details": {"subscription": "sub_b"}}}
    assert tm.subscription_of_invoice(nested) == "sub_b"
    tid = uuid.uuid4()
    ours = {"metadata": {"kind": "tenant_membership", "tenant_id": str(tid)}}
    assert tm.is_ours(ours) and tm.tenant_of(ours) == tid
    assert not tm.is_ours({"metadata": {"partner_id": "x"}})
    row = tm.invoice_row(
        {"status": "open", "attempt_count": 1, "amount_due": 4000, "hosted_invoice_url": "u"}
    )
    assert (row["status"], row["amount_cents"], row["url"]) == ("failed", 4000, "u")
