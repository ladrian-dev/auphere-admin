"""Spec 026: the home blocks as pure rules (no database)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from nexus_api.db.models import TenantStatus
from nexus_api.services.console_home import TenantSnapshot
from nexus_api.services.console_home_blocks import (
    ClientRow,
    attention_items,
    credit_block,
    portfolio_rows,
    review_block,
    trend_block,
    window,
)

TODAY = date(2026, 10, 2)


def _client(ref: str, status: TenantStatus = TenantStatus.ACTIVE) -> ClientRow:
    return ClientRow(uuid.uuid4(), ref, ref.title(), status)


def _snap(c: ClientRow, **kw: object) -> TenantSnapshot:
    base: dict[str, object] = {
        "tenant_id": c.tenant_id,
        "conversations_month": 0,
        "failed_messages_24h": 0,
        "agent_version": 1,
        "whatsapp_channels": 1,
        "whatsapp_bad": 0,
    }
    base.update(kw)
    return TenantSnapshot(**base)  # type: ignore[arg-type]


def test_problems_come_worst_first_each_with_its_fix() -> None:
    flor, demo, nuevo = (
        _client("flor"),
        _client("demo"),
        _client("nuevo", TenantStatus.PROVISIONING),
    )
    snaps = {
        flor.tenant_id: _snap(flor, stale_drafts=1, failed_messages_24h=3),
        demo.tenant_id: _snap(demo, whatsapp_bad=1, needs_reauth=1, whatsapp_quality_red=1),
    }
    items = attention_items([flor, demo, nuevo], snaps, {flor.tenant_id: True}, {demo.tenant_id: 2})
    assert [(i.external_client_ref, i.kind) for i in items] == [
        ("flor", "out_of_quota"),
        ("demo", "whatsapp_disconnected"),
        ("demo", "needs_reauth"),
        ("demo", "quality_red"),
        ("flor", "failed_messages"),
        ("demo", "template_rejected"),
        ("flor", "draft_unpublished"),
        ("nuevo", "provisioning"),
    ]
    hrefs = {(i.external_client_ref, i.kind): i.href for i in items}
    assert hrefs[("flor", "out_of_quota")] == "/usage?client=flor"
    assert hrefs[("demo", "whatsapp_disconnected")] == "/clients/demo/channels"
    assert hrefs[("flor", "draft_unpublished")] == "/clients/flor/agent"
    assert hrefs[("flor", "failed_messages")] == "/clients/flor/conversations"


def test_a_paused_client_is_not_a_problem_and_a_healthy_one_adds_nothing() -> None:
    sano, pausado = _client("sano"), _client("pausado", TenantStatus.PAUSED)
    snaps = {sano.tenant_id: _snap(sano)}
    assert attention_items([sano, pausado], snaps, {}, {}) == []


def test_what_waits_for_a_person_is_summed_across_the_portfolio() -> None:
    a, b, c = _client("a"), _client("b"), _client("c")
    snaps = {
        a.tenant_id: _snap(a, escalated_recent=2, unanswered_7d=4),
        b.tenant_id: _snap(b, payments_pending=1),
        c.tenant_id: _snap(c),
    }
    block = review_block([a, b, c], snaps)
    assert (block.escalated, block.payments, block.unanswered) == (2, 1, 4)
    assert [r.external_client_ref for r in block.clients] == ["a", "b"]
    assert block.clients[0].href == "/clients/a/conversations"


def test_the_trend_compares_seven_days_with_the_seven_before() -> None:
    a, b = _client("a"), _client("b")
    shown = window(TODAY)
    before = window(TODAY - timedelta(days=7))
    snaps = {
        a.tenant_id: _snap(a, daily={shown[-1]: 5, shown[0]: 1, before[3]: 4}),
        b.tenant_id: _snap(b, daily={shown[-1]: 2}),
    }
    block = trend_block([a, b], snaps, TODAY)
    assert block.days == shown and block.days[-1] == TODAY
    assert block.series[-1] == 7 and block.series[0] == 1
    assert (block.current, block.previous) == (8, 4)
    assert [c.external_client_ref for c in block.by_client] == ["a", "b"]


def test_no_previous_activity_means_no_invented_change() -> None:
    a = _client("a")
    block = trend_block([a], {a.tenant_id: _snap(a, daily={TODAY: 3})}, TODAY)
    assert block.previous is None


def test_beyond_five_clients_the_rest_are_drawn_together() -> None:
    clients = [_client(f"c{i}") for i in range(7)]
    snaps = {c.tenant_id: _snap(c, daily={TODAY: 10 - i}) for i, c in enumerate(clients)}
    block = trend_block(clients, snaps, TODAY)
    assert len(block.by_client) == 6
    rest = block.by_client[-1]
    assert rest.external_client_ref is None and rest.series[-1] == 5 + 4


def test_credit_says_how_many_days_it_lasts_and_who_runs_out_first() -> None:
    rapido, lento, quieto = _client("rapido"), _client("lento"), _client("quieto")
    burn = {rapido.tenant_id: 7000, lento.tenant_id: 700, None: 700}
    allocations = {
        rapido.tenant_id: (10_000, 2_000),  # 1 000 a day: 2 days
        lento.tenant_id: (10_000, 9_000),  # 100 a day: 90 days
        quieto.tenant_id: (10_000, 5_000),  # no spend: not at risk
    }
    block = credit_block([rapido, lento, quieto], 84_000, burn, allocations, days_to_month_end=20)
    assert block.spent_7d == 8_400 and block.daily_average == 1_200
    assert block.days_left == 70
    assert [r.external_client_ref for r in block.at_risk] == ["rapido"]
    assert block.at_risk[0].days_left == 2


def test_without_spend_there_are_no_days_of_autonomy() -> None:
    block = credit_block([], 5_000, {}, {}, days_to_month_end=10)
    assert block.days_left is None and block.at_risk == []


def test_the_portfolio_has_one_row_per_client_with_its_problems_counted() -> None:
    a, b = _client("a"), _client("b", TenantStatus.PROVISIONING)
    last = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
    snaps = {a.tenant_id: _snap(a, daily={TODAY: 3}, last_activity_at=last, failed_messages_24h=1)}
    problems = attention_items([a, b], snaps, {}, {})
    rows = portfolio_rows([a, b], snaps, {a.tenant_id: (1000, 400)}, problems, TODAY)
    by_ref = {r.external_client_ref: r for r in rows}
    assert by_ref["a"].conversations_7d == 3 and by_ref["a"].series_7d[-1] == 3
    assert (by_ref["a"].credit_cap, by_ref["a"].credit_remaining) == (1000, 400)
    assert by_ref["a"].attention == 1 and by_ref["a"].last_activity_at == last
    assert by_ref["b"].status == "provisioning" and by_ref["b"].credit_cap is None
