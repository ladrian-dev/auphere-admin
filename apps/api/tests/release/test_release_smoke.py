"""Release smoke. Manual-only — see conftest.py.

These tests verify a freshly-deployed Railway revision is healthy
end-to-end before Block J onboards Cultor Barber.

The suite covers what a user-visible HTTP probe can see; Langfuse
trace verification is documented as a manual step in the runbook
because it requires inspection of the Cloud workspace UI.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx
import pytest

pytestmark = pytest.mark.manual_only


def test_health_returns_ok(release_api_url: str) -> None:
    r = httpx.get(f"{release_api_url}/health", timeout=10.0)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok"}


def test_health_live_returns_alive(release_api_url: str) -> None:
    r = httpx.get(f"{release_api_url}/health/live", timeout=10.0)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "alive"


def test_admin_tenants_lists_canary(
    release_api_url: str, release_admin_token: str, canary_slug: str
) -> None:
    r = httpx.get(
        f"{release_api_url}/admin/tenants",
        headers={"Authorization": f"Bearer {release_admin_token}"},
        timeout=15.0,
    )
    assert r.status_code == 200, r.text
    tenants = r.json()
    slugs = [t["slug"] for t in tenants]
    assert canary_slug in slugs, (
        f"canary tenant {canary_slug!r} not found — did you run "
        f"apps/api/scripts/seed_canary_tenant.py against production? "
        f"got: {slugs}"
    )


def test_isolation_metrics_all_zero(
    release_api_url: str, release_admin_token: str, canary_slug: str
) -> None:
    r = httpx.get(
        f"{release_api_url}/admin/tenants",
        headers={"Authorization": f"Bearer {release_admin_token}"},
        timeout=15.0,
    )
    r.raise_for_status()
    tenants = r.json()
    canary = next(t for t in tenants if t["slug"] == canary_slug)
    tenant_id = canary["id"]

    r = httpx.get(
        f"{release_api_url}/admin/tenants/{tenant_id}/isolation/metrics",
        headers={"Authorization": f"Bearer {release_admin_token}"},
        timeout=15.0,
    )
    assert r.status_code == 200, r.text
    metrics = r.json()
    # Block H ships 7 canonical counters. None of them should fire on a
    # canary tenant that has not received traffic.
    expected = {
        "isolation.tool_whitelist_violation",
        "isolation.cross_tenant_query",
        "isolation.unscoped_query",
        "isolation.checkpointer_thread_leak",
        "isolation.kg_scope_violation",
        "isolation.llm_call_unscoped",
        "isolation.dispatch_caller_token_invalid",
    }
    seen = {m["metric"] for m in metrics["metrics"]}
    missing = expected - seen
    assert not missing, f"missing isolation metrics: {missing}"
    nonzero = [m for m in metrics["metrics"] if m["count_24h"] != 0]
    assert nonzero == [], f"canary tenant has nonzero counters: {nonzero}"


def test_webhook_ycloud_signature_required(release_api_url: str) -> None:
    """Without a valid signature the webhook must reject. Confirms the
    YCloud HMAC verifier is wired in production (Block F) before we
    flip the YCloud dashboard to point at this URL.
    """

    r = httpx.post(
        f"{release_api_url}/webhook/ycloud",
        json={"type": "whatsapp.inbound_message.received"},
        timeout=10.0,
    )
    # 401 (unauthenticated) or 400 (signature missing) are both
    # acceptable rejections — what we MUST NOT see is 200.
    assert r.status_code in (400, 401, 403), r.text


def test_webhook_ycloud_accepts_signed_payload(
    release_api_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Optional — only runs when ``NEXUS_RELEASE_YCLOUD_WEBHOOK_SECRET``
    is provided. Forces a turn through the dispatcher so the operator
    can verify a Langfuse trace lands in the Cloud workspace with
    ``user_id = canary_tenant_id``.

    The smoke ack does not assert the trace exists — that's a
    human-in-the-loop check documented in the runbook.
    """

    import os

    secret = os.environ.get("NEXUS_RELEASE_YCLOUD_WEBHOOK_SECRET")
    if not secret:
        pytest.skip("set NEXUS_RELEASE_YCLOUD_WEBHOOK_SECRET to exercise the dispatcher")

    business_phone = os.environ.get("NEXUS_RELEASE_CANARY_BUSINESS_PHONE")
    customer_phone = os.environ.get("NEXUS_RELEASE_CANARY_CUSTOMER_PHONE", "+56900000000")
    if not business_phone:
        pytest.skip("set NEXUS_RELEASE_CANARY_BUSINESS_PHONE (E.164 of the canary channel)")

    body = json.dumps(
        {
            "type": "whatsapp.inbound_message.received",
            "whatsappInboundMessage": {
                "to": business_phone,
                "from": customer_phone,
                "wamid": f"wamid.smoke.{int(time.time())}",
                "type": "text",
                "text": {"body": "release smoke"},
            },
        }
    ).encode()
    ts = str(int(time.time()))
    mac = hmac.new(secret.encode(), f"{ts}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    sig = f"t={ts},s={mac}"

    r = httpx.post(
        f"{release_api_url}/webhook/ycloud",
        content=body,
        headers={
            "Content-Type": "application/json",
            "YCloud-Signature": sig,
        },
        timeout=15.0,
    )
    assert r.status_code in (200, 202), r.text
