"""Spec 077 · R7.2 a R7.7 — el pago de Tecfin activa su membresía sin nadie.

El camino de verdad, de punta a punta, salvo Stripe:

- el webhook recibe un aviso firmado de la membresía de un cliente, sin
  ``client_reference_id``, y lo encola con el partner vacío;
- el worker (``process_event.handle_entry``) lo resuelve por la rama de la
  membresía y responde ``processed``, sin pasar por el camino de los partners;
- recontratar tras cancelar: el pago del enlace nuevo se encuentra aunque el
  aviso se pierda.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from nexus_api.billing import tenant_membership as stripe_membership
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ServiceMembership, Tenant, TenantPlan
from nexus_api.services import service_memberships as memberships

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SECRET = "whsec_test_spec077"


@pytest.fixture(autouse=True)
def _billing_keys(monkeypatch: pytest.MonkeyPatch):
    from nexus_api.config import get_settings

    monkeypatch.setenv("NEXUS_BILLING_API_KEY", "sk_test_spec077")
    monkeypatch.setenv("NEXUS_BILLING_PUBLIC_KEY", "pk_test_spec077")
    monkeypatch.setenv("NEXUS_BILLING_WEBHOOK_SECRET", _SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def api():
    from nexus_api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def _sign(payload: bytes) -> str:
    ts = int(time.time())
    mac = hmac.new(_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


async def _tenant(db_session: Any) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(Tenant(id=tid, name="Tecfin", slug=f"tf-{tid.hex[:6]}", plan=TenantPlan.PRO))
    await db_session.commit()
    return tid


async def _row(tenant_id: uuid.UUID) -> ServiceMembership:
    import sqlalchemy as sa

    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        row = await s.scalar(
            sa.select(ServiceMembership).where(ServiceMembership.archived_at.is_(None))
        )
        assert row is not None
        return row


def _mark(tenant_id: uuid.UUID) -> dict[str, str]:
    return {"kind": "tenant_membership", "tenant_id": str(tenant_id)}


def _subscription(tenant_id: uuid.UUID, sub_id: str, status: str) -> dict[str, Any]:
    now = int(datetime.now(UTC).timestamp())
    return {
        "id": sub_id,
        "status": status,
        "customer": f"cus_{tenant_id.hex[:8]}",
        "metadata": _mark(tenant_id),
        "items": {"data": [{"current_period_start": now, "current_period_end": now + 2_592_000}]},
    }


async def test_the_webhook_queues_a_membership_notice_with_no_partner(api, db_session) -> None:
    from nexus_api.api.webhooks.billing import BILLING_EVENT_STREAM
    from nexus_api.core.redis_client import get_redis

    tid = await _tenant(db_session)
    event = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{uuid.uuid4().hex[:10]}",
                "object": "checkout.session",
                "mode": "subscription",
                "metadata": _mark(tid),
                "subscription": "sub_1",
            }
        },
    }
    body = json.dumps(event).encode()
    resp = await api.post(
        "/webhook/billing", content=body, headers={"Stripe-Signature": _sign(body)}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    entries = await get_redis().xrevrange(BILLING_EVENT_STREAM, count=20)
    mine = [
        {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in fields.items()
        }
        for _id, fields in entries
    ]
    entry = next(e for e in mine if e["provider_event_id"] == event["id"])
    assert entry["partner_id"] == ""
    assert entry["checkout_session_id"] == event["data"]["object"]["id"]


class _Client:
    """The provider objects the worker re-fetches."""

    def __init__(self, session_obj: dict[str, Any], sub: dict[str, Any]) -> None:
        self._session, self._sub = session_obj, sub
        self.checkout = self
        self.sessions = self
        self.subscriptions = _Subs(sub)
        self.invoices = self

    def retrieve(self, _id: str) -> dict[str, Any]:
        return self._session


class _Subs:
    def __init__(self, sub: dict[str, Any]) -> None:
        self._sub = sub

    def retrieve(self, _id: str) -> dict[str, Any]:
        return self._sub


async def _handle(client: Any, fields: dict[str, str]) -> str:
    from nexus_worker.billing.process_event import handle_entry

    async with get_sessionmaker()() as session:
        status = await handle_entry(session, client, fields)
        await session.commit()
    return status


async def test_the_worker_activates_the_membership_from_a_partnerless_notice(db_session) -> None:
    tid = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(
            ServiceMembership(
                tenant_id=tid,
                payer="stripe",
                amount_cents=4000,
                stripe_customer_id=f"cus_{tid.hex[:8]}",
                stripe_checkout_session_id="cs_link",
            )
        )
    client = _Client(
        {"id": "cs_link", "metadata": _mark(tid), "subscription": "sub_1"},
        _subscription(tid, "sub_1", "active"),
    )
    status = await _handle(
        client,
        {
            "event_type": "checkout.session.completed",
            "partner_id": "",
            "provider_event_id": "evt_x",
            "object_id": "cs_link",
            "checkout_session_id": "cs_link",
        },
    )
    assert status == "processed"
    row = await _row(tid)
    assert (row.status, row.stripe_subscription_id) == ("active", "sub_1")


async def test_a_partnerless_notice_that_is_not_ours_stays_an_orphan(db_session) -> None:
    client = _Client(
        {"id": "cs_other", "metadata": {}, "subscription": None},
        {"id": "sub_p", "status": "active", "metadata": {}},
    )
    status = await _handle(
        client,
        {
            "event_type": "checkout.session.completed",
            "partner_id": "",
            "provider_event_id": "evt_y",
            "object_id": "cs_other",
            "checkout_session_id": "cs_other",
        },
    )
    assert status == "failed"  # the partners' orphan path, as before


async def test_resubscribing_after_a_cancel_is_found_even_without_the_notice(
    db_session, monkeypatch
) -> None:
    """Advisor: cancel, new link, pay; the notice is lost; the refresh finds
    the new subscription through the current link and reactivates."""
    tid = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(
            ServiceMembership(
                tenant_id=tid,
                payer="stripe",
                amount_cents=4000,
                status="canceled",
                stripe_customer_id=f"cus_{tid.hex[:8]}",
                stripe_subscription_id="sub_1",
                stripe_checkout_session_id="cs_1",
            )
        )
    monkeypatch.setattr(
        stripe_membership,
        "open_tenant_membership_session",
        lambda **_kw: stripe_membership.OpenedCheckout(
            url="https://checkout.stripe.test/cs_2", session_id="cs_2", expires_at=None
        ),
    )
    # The old link was paid by the subscription we already know (and that was
    # cancelled): that is not «already paid», a new link opens.
    monkeypatch.setattr(stripe_membership, "expire_checkout_session", lambda _sid: "sub_1")
    await memberships.create_checkout(tid, actor="operator:luis@auphere.test")
    assert (await _row(tid)).status == "pending"

    monkeypatch.setattr(
        stripe_membership,
        "retrieve_checkout_session",
        lambda sid: {"id": sid, "subscription": "sub_2"},
    )
    monkeypatch.setattr(
        stripe_membership,
        "retrieve_subscription",
        lambda sid: _subscription(tid, sid, "active"),
    )
    view = await memberships.refresh_from_stripe(tid)
    assert view.status == "active"
    assert (await _row(tid)).stripe_subscription_id == "sub_2"
