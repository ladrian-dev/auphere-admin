"""Lane D (``home-usage``) — home (CP-08), usage series/projection/cap/CSV
(CP-22), usage alerts (CP-24), receipts download (CP-25), audit vocabulary
+ CSV (CP-28).

Isolation is pinned structurally in ``tests/isolation``; this file pins
BEHAVIOUR and the plan's measurable acceptance criteria:

- the console's channel total equals ``SELECT SUM(billable_qty) … source='channel'``
  over the seeded rows (to the unit);
- crossing 80 % creates exactly one notification and never a second one;
- every ``console.*`` action written in ``api/console/**`` is in the seeded
  vocabulary (a lane that adds an action without vocabulary breaks this);
- a foreign receipt id is an opaque 404.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest
import sqlalchemy as sa

from nexus_api.api.console import audit as audit_module
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    ConsoleNotification,
    Conversation,
    ConversationStatus,
    Customer,
    Invoice,
    InvoiceLine,
    Message,
    MessageDirection,
    MessageStatus,
    Partner,
    PartnerTenant,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_api.services import usage_alerts
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio

_CONSOLE_DIR = Path(__file__).resolve().parents[2] / "src" / "nexus_api" / "api" / "console"


async def _seed_usage(
    db_session, tenant_id: uuid.UUID, rows: list[tuple[str, str, float, float | None]]
) -> None:
    """rows: (meter, source, qty, cost_usd|None) at ``now`` (inside the month)."""
    for meter, source, qty, cost in rows:
        await db_session.execute(
            sa.text(
                "INSERT INTO usage_records (tenant_id, occurred_at, meter, quantity, cost_usd, "
                "billable_qty, idempotency_key, source) "
                "VALUES (:t, now(), :m, :q, :c, :q, :k, :s)"
            ),
            {
                "t": str(tenant_id),
                "m": meter,
                "q": qty,
                "c": cost,
                "k": f"k:{uuid.uuid4()}",
                "s": source,
            },
        )
    await db_session.commit()


async def _add_client(
    db_session, partner_id: uuid.UUID, ref: str, status: TenantStatus
) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name=f"Client {ref}",
            slug=f"t-{ref}-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            status=status,
            partner_id=partner_id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=partner_id,
            external_client_ref=ref,
            tenant_id=tid,
            client_name=f"Client {ref}",
        )
    )
    await db_session.commit()
    return tid


# ── CP-08 home ─────────────────────────────────────────────────────────


async def test_home_returns_five_blocks_from_one_call(client, console_world, db_session) -> None:
    a = console_world["a"]
    # Second client, provisioning; the first one gets a degraded WhatsApp
    # channel + an active agent + one failed message in the last 24 h.
    await _add_client(db_session, a["partner_id"], "prov-1", TenantStatus.PROVISIONING)
    ch = Channel(
        id=uuid.uuid4(),
        tenant_id=a["tenant_id"],
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
        config={},
        status=ChannelStatus.DEGRADED,
    )
    db_session.add(ch)
    db_session.add(
        AgentConfig(
            tenant_id=a["tenant_id"],
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="x",
            tools=[],
        )
    )
    cust = Customer(
        id=uuid.uuid4(), tenant_id=a["tenant_id"], identifier="+34600111222", preferences={}
    )
    db_session.add(cust)
    await db_session.flush()
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=a["tenant_id"],
        channel_id=ch.id,
        customer_id=cust.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        Message(
            tenant_id=a["tenant_id"],
            conversation_id=conv.id,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.FAILED,
            content="x",
        )
    )
    await db_session.commit()
    await _seed_usage(
        db_session,
        a["tenant_id"],
        [("channel.message", "channel", 30, 0.01), ("channel.message", "qa", 5, 0.01)],
    )
    await db_session.execute(
        sa.update(Partner).where(Partner.id == a["partner_id"]).values(usage_cap_messages_month=100)
    )
    await db_session.commit()

    r = await client.get("/console/home", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["errors"] == []
    assert body["clients"] == {"active": 1, "total": 2, "provisioning": 1, "paused": 0}
    assert body["conversations_period"]["count"] == 1
    usage = body["usage_units"]
    assert usage["units"] == 30.0 and usage["cap"] == 100 and usage["percent"] == 30.0
    assert usage["projected_month_units"] >= 30.0 and usage["basis_days"] >= 1
    inc = body["agents_with_incidents"]
    assert inc["count"] == 1
    assert inc["refs"][0]["external_client_ref"] == a["ref"]
    assert set(inc["refs"][0]["issues"]) == {"whatsapp_degraded", "failed_messages_24h"}
    assert inc["refs"][0]["href"] == f"/clients/{a['ref']}"
    pend = body["pending_actions"]
    kinds = {i["kind"] for i in pend["items"]}
    assert "client_provisioning" in kinds
    assert "cost" not in r.text.lower()
    assert "tenant_id" not in r.text

    # A billing member sees no client blocks (permission-gated), still 200.
    billing = await add_console_member(db_session, partner_id=a["partner_id"], role="billing")
    rb = await client.get("/console/home", headers=billing["headers"]())
    assert rb.status_code == 200
    assert rb.json()["clients"] is None and rb.json()["usage_units"] is not None

    # Partner B sees none of A's figures.
    b = console_world["b"]
    rb2 = (await client.get("/console/home", headers=b["headers"]())).json()
    assert rb2["clients"]["total"] == 1 and rb2["usage_units"]["units"] == 0.0


# ── CP-22 usage: totals match SQL, series, projection, CSV ─────────────


async def test_usage_total_matches_sql_sum_and_flags_unpriced(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    tid2 = await _add_client(db_session, a["partner_id"], "c-2", TenantStatus.ACTIVE)
    await _seed_usage(
        db_session,
        a["tenant_id"],
        [
            ("channel.message", "channel", 12, 0.02),
            ("channel.message", "channel", 3, None),
            ("llm.input_tokens", "channel", 1200, 0.003),
            ("channel.message", "qa", 7, 0.01),
        ],
    )
    await _seed_usage(
        db_session,
        tid2,
        [("channel.message", "channel", 5, 0.01), ("media.image", "channel", 2, None)],
    )

    r = await client.get("/console/usage?days=7", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    expected = await db_session.scalar(
        sa.text(
            "SELECT coalesce(sum(billable_qty),0) FROM usage_records "
            "WHERE tenant_id = ANY(:ids) AND source='channel' AND meter='channel.message' "
            "AND occurred_at >= now() - interval '7 days'"
        ),
        {"ids": [a["tenant_id"], tid2]},
    )
    assert body["totals_by_meter"]["channel.message"] == float(expected) == 20.0
    assert body["totals_by_meter"]["media.image"] == 2.0
    assert body["unpriced_records"] == 2
    assert body["month"]["units"] == 20.0 and body["month"]["cap"] is None
    assert body["month"]["basis_days"] >= 1 and body["month"]["days_in_month"] in (28, 29, 30, 31)
    assert "cost_usd" not in r.text and "cost" not in r.text.lower()

    only_c2 = (await client.get("/console/usage?days=7&client=c-2", headers=a["headers"]())).json()
    assert only_c2["totals_by_meter"] == {"channel.message": 5.0, "media.image": 2.0}

    # Series: one dense point per day, today carries the channel units.
    s = await client.get("/console/usage/series?days=3", headers=a["headers"]())
    assert s.status_code == 200, s.text
    series = s.json()
    assert len(series["points"]) in (4, 5)
    today = datetime.now(UTC).date().isoformat()
    last = next(p for p in series["points"] if p["day"] == today)
    assert last["by_meter"]["channel.message"] == 20.0
    assert "channel.message" in series["meters"] and series["source"] == "channel"
    qa = (await client.get("/console/usage/series?days=3&source=qa", headers=a["headers"]())).json()
    assert next(p for p in qa["points"] if p["day"] == today)["by_meter"] == {
        "channel.message": 7.0
    }

    # CSV, localized header, streaming attachment.
    csv_es = await client.get("/console/usage/export.csv?days=7&lang=es", headers=a["headers"]())
    assert csv_es.status_code == 200
    assert csv_es.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_es.headers["content-disposition"]
    lines = csv_es.text.lstrip("﻿").splitlines()
    assert (
        lines[0] == "ref_cliente,cliente,dia,medidor,origen,cantidad,unidades_facturables,registros"
    )
    assert any(",channel.message,channel,15,15,2" in ln for ln in lines), lines
    csv_en = await client.get("/console/usage/export.csv?days=7", headers=a["headers"]())
    assert csv_en.text.lstrip("﻿").splitlines()[0].startswith("client_ref,")


# ── CP-24 alerts ───────────────────────────────────────────────────────


async def test_usage_alerts_settings_and_permissions(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    g = await client.get("/console/usage/alerts", headers=h())
    assert g.status_code == 200 and g.json()["cap_messages_month"] is None
    p = await client.put(
        "/console/usage/alerts",
        headers=h(),
        json={
            "cap_messages_month": 1000,
            "recipients": ["Ops@Example.com", "ops@example.com"],
            "enabled": True,
        },
    )
    assert p.status_code == 200, p.text
    assert p.json()["cap_messages_month"] == 1000
    assert p.json()["recipients"] == ["ops@example.com"]
    row = (
        await db_session.execute(
            sa.select(AuditLog.action).where(AuditLog.action == "console.usage.alerts_update")
        )
    ).all()
    assert row
    bad = await client.put("/console/usage/alerts", headers=h(), json={"recipients": ["nope"]})
    assert bad.status_code == 422
    # analyst may read, not write
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    assert (
        await client.get("/console/usage/alerts", headers=analyst["headers"]())
    ).status_code == 200
    forbidden = await client.put(
        "/console/usage/alerts", headers=analyst["headers"](), json={"cap_messages_month": 5}
    )
    assert forbidden.status_code == 403


async def test_crossing_80_percent_notifies_once_and_emails(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sent: list[dict] = []

    async def _fake_send(**kwargs):
        sent.append(kwargs)
        return True

    monkeypatch.setattr(usage_alerts, "send_email", _fake_send)
    await db_session.execute(
        sa.update(Partner)
        .where(Partner.id == a["partner_id"])
        .values(usage_cap_messages_month=100, usage_alert_recipients=["ops@example.com"])
    )
    await db_session.commit()
    await _seed_usage(db_session, a["tenant_id"], [("channel.message", "channel", 85, 0.01)])

    partner = await db_session.get(Partner, a["partner_id"])
    await db_session.commit()  # the service manages its own short transactions
    ev = await usage_alerts.evaluate_partner_usage_alerts(db_session, partner)
    assert ev.percent == 85.0 and ev.created == [80] and ev.emailed is True
    assert len(sent) == 1 and sent[0]["to"] == ["ops@example.com"] and "80" in sent[0]["subject"]

    # Re-evaluating (cron tick, or opening /console/home) never duplicates.
    ev2 = await usage_alerts.evaluate_partner_usage_alerts(db_session, partner)
    assert ev2.created == [] and len(sent) == 1
    r = await client.get("/console/home", headers=a["headers"]())
    assert r.status_code == 200
    n = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(ConsoleNotification.partner_id == a["partner_id"])
    )
    assert n == 1
    kinds = (
        await db_session.execute(
            sa.select(ConsoleNotification.kind, ConsoleNotification.dedupe_key).where(
                ConsoleNotification.partner_id == a["partner_id"]
            )
        )
    ).all()
    assert kinds[0][0] == "usage.threshold"
    assert kinds[0][1] == f"partner:{a['partner_id']}:usage:80:{datetime.now(UTC):%Y-%m}"
    # The home page lists the unread alert as a pending action.
    pend = r.json()["pending_actions"]["items"]
    assert any(i["kind"] == "usage_alerts_unread" and i["href"] == "/usage/alerts" for i in pend)

    # Crossing 100 % adds the cap_reached one (and only that one).
    await _seed_usage(db_session, a["tenant_id"], [("channel.message", "channel", 20, 0.01)])
    ev3 = await usage_alerts.evaluate_partner_usage_alerts(db_session, partner)
    assert ev3.created == [100] and len(sent) == 2
    # Service is NOT cut: nothing changes on the partner/tenants.
    await db_session.refresh(partner)
    assert partner.status == "active"


# ── CP-25 receipts download ────────────────────────────────────────────


async def test_receipt_download_is_html_attachment_and_foreign_is_404(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    inv = Invoice(
        partner_id=a["partner_id"],
        period_year=2026,
        period_month=7,
        total_cents=12345,
        status="issued",
    )
    db_session.add(inv)
    await db_session.flush()
    db_session.add(
        InvoiceLine(
            invoice_id=inv.id,
            tenant_id=a["tenant_id"],
            description="Suscripción julio",
            amount_cents=12345,
        )
    )
    await db_session.commit()
    r = await client.get(f"/console/billing/receipts/{inv.id}/download", headers=a["headers"]())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert "attachment" in r.headers["content-disposition"]
    assert "$123.45" in r.text and "Suscripción julio" in r.text
    # Foreign / unknown → opaque 404 with the same body.
    foreign = await client.get(
        f"/console/billing/receipts/{inv.id}/download", headers=b["headers"]()
    )
    missing = await client.get(
        f"/console/billing/receipts/{uuid.uuid4()}/download", headers=a["headers"]()
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    # Analyst has no billing:read.
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    assert (
        await client.get(
            f"/console/billing/receipts/{inv.id}/download", headers=analyst["headers"]()
        )
    ).status_code == 403


# ── CP-28 audit vocabulary + CSV + dates ───────────────────────────────


def _actions_written_in_console_code() -> set[str]:
    """Every ``console.*`` literal used as an audit ``action`` in
    ``api/console/**`` — plus the ``agent_config.*`` ones the agent service
    writes with a ``console:`` actor."""
    found: set[str] = set()
    pattern = re.compile(r"""(?:audit_)?action\s*=\s*["'](console\.[a-z_.]+)["']""")
    inline = re.compile(r"""["'](console\.[a-z_.]+)["']""")
    for path in _CONSOLE_DIR.rglob("*.py"):
        if path.name in {"audit.py"}:  # renderer, not a writer
            continue
        text = path.read_text()
        found.update(pattern.findall(text))
        # ``AuditLog(..., action="console.x")`` and ``_audit(principal, "console.x", …)``
        for m in inline.findall(text):
            if m.count(".") >= 2 and not m.endswith("_failed"):
                found.add(m)
    found.update({"agent_config.stage", "agent_config.promote", "agent_config.rollback"})
    return found


async def test_every_console_action_written_has_vocabulary(db_session) -> None:
    seeded = {
        r[0]
        for r in (
            await db_session.execute(sa.text("SELECT action FROM console_audit_vocabulary"))
        ).all()
    }
    written = _actions_written_in_console_code()
    missing = sorted(written - seeded)
    assert not missing, (
        f"console actions without vocabulary (add to migration 0084 seed): {missing}"
    )


async def test_audit_renders_from_vocabulary_in_both_languages_with_dates_and_csv(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    audit_module.reset_vocabulary_cache_for_tests()
    old = datetime.now(UTC) - timedelta(days=10)
    db_session.add_all(
        [
            AuditLog(
                tenant_id=None,
                actor="console:owner-a@example.com",
                action="console.member.invite",
                target=f"partner:{a['partner_id']}",
                after_json={"email": "new@example.com", "role": "builder"},
            ),
            AuditLog(
                tenant_id=a["tenant_id"],
                actor="console:owner-a@example.com",
                action="agent_config.promote",
                target="agent_config:1",
                after_json={"version": 3},
            ),
            AuditLog(
                tenant_id=a["tenant_id"],
                actor="console:owner-a@example.com",
                action="something.unknown",
                target="x:1",
                created_at=old,
            ),
        ]
    )
    await db_session.commit()

    _r = await client.get("/console/audit", headers=h())
    assert _r.status_code == 200, _r.text
    en = _r.json()["items"]
    by_action = {i["action"]: i for i in en}
    assert (
        by_action["console.member.invite"]["summary"]
        == "owner-a@example.com invited new@example.com as builder"
    )
    assert (
        by_action["agent_config.promote"]["summary"]
        == "owner-a@example.com published agent version 3 for Client A One"
    )
    assert (
        by_action["something.unknown"]["summary"] == "owner-a@example.com · something.unknown · x:1"
    )
    es = (await client.get("/console/audit?lang=es", headers=h())).json()["items"]
    assert {i["action"]: i["summary"] for i in es}["console.member.invite"] == (
        "owner-a@example.com invitó a new@example.com como builder"
    )
    # Date filters.
    since = quote((datetime.now(UTC) - timedelta(days=1)).isoformat())
    recent = (await client.get(f"/console/audit?after={since}", headers=h())).json()["items"]
    assert {i["action"] for i in recent} == {"console.member.invite", "agent_config.promote"}
    older = (await client.get(f"/console/audit?before={since}", headers=h())).json()["items"]
    assert {i["action"] for i in older} == {"something.unknown"}
    # Vocabulary endpoint.
    vocab = (await client.get("/console/audit/vocabulary?lang=es", headers=h())).json()
    assert vocab["lang"] == "es" and any(
        e["action"] == "console.key.create" for e in vocab["entries"]
    )
    # CSV.
    csv_r = await client.get("/console/audit/export.csv?lang=es", headers=h())
    assert csv_r.status_code == 200 and csv_r.headers["content-type"].startswith("text/csv")
    lines = csv_r.text.lstrip("﻿").splitlines()
    assert lines[0] == "fecha,actor,accion,ref_cliente,cliente,objetivo,resumen"
    assert len(lines) == 4
    assert any("invitó a new@example.com" in ln for ln in lines)
    # Partner B sees nothing of A.
    b = console_world["b"]
    assert (await client.get("/console/audit", headers=b["headers"]())).json()["items"] == []
