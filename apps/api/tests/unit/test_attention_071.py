"""Spec 071, T001 — la regla única, entera: lo del partner, la gravedad y el orden
(requisitos 1.1, 1.2 y 2.1; ``contracts/api.md``).

A los siete motivos de cada cliente (spec 047) se suman los del partner:

- el tope de «Construcción y pruebas» al 80 % o agotado (el estado de la partida);
- la cuenta baja o vacía: menos del 20 % de lo cargado en el mes o menos de 7 días al
  ritmo de los últimos 7 (D2), y nunca menos de lo que ya avisa ``wallet_alerts``
  (research.md §R3);
- un cobro fallido.

Cada fila lleva su gravedad y su arreglo, y la lista va de peor a mejor: dentro de cada
gravedad, primero lo del partner y luego los clientes por ``ATTENTION_REASONS`` y ``ref``.
"""

from __future__ import annotations

from nexus_api.services.attention import (
    ATTENTION_REASONS,
    CONDITION_CODES,
    COVERED_BY,
    PARTNER_CONDITION_KINDS,
    PARTNER_REASONS,
    AccountFacts,
    AttentionItem,
    BuildFacts,
    PartnerFacts,
    buy_first_when_empty,
    order_items,
    partner_attention,
    partner_items,
    severity_of,
)


def _build(spent: int, cap: int = 100, state: str | None = None) -> BuildFacts:
    if state is None:
        state = "exhausted" if spent >= cap else "warning" if spent >= 0.8 * cap else "ok"
    return BuildFacts(cap_micros=cap, spent_micros=spent, state=state, currency="USD")


def _account(**kw: object) -> AccountFacts:
    base: dict[str, object] = {
        "available_micros": 50,
        "currency": "USD",
        "pct_left": 50.0,
        "days_left": 30,
        "notice_pct_used": 10.0,
    }
    base.update(kw)
    return AccountFacts(**base)  # type: ignore[arg-type]


def _codes(facts: PartnerFacts) -> list[str]:
    return [r.code for r in partner_attention(facts)]


# ── los motivos del partner ─────────────────────────────────────────────────


def test_the_partner_reasons_are_the_five_of_the_contract_in_order() -> None:
    assert PARTNER_REASONS == (
        "build_cap_exhausted",
        "build_cap_warning",
        "account_empty",
        "account_low",
        "billing_payment_failed",
    )


def test_a_healthy_partner_needs_nothing() -> None:
    assert _codes(PartnerFacts(build=_build(10), account=_account())) == []
    assert _codes(PartnerFacts()) == [], "sin datos de nada, nada que decir"


def test_the_build_cap_warns_at_80_and_is_exhausted_at_100() -> None:
    assert _codes(PartnerFacts(build=_build(79))) == []
    assert _codes(PartnerFacts(build=_build(80))) == ["build_cap_warning"]
    assert _codes(PartnerFacts(build=_build(100))) == ["build_cap_exhausted"]
    assert _codes(PartnerFacts(build=_build(140))) == ["build_cap_exhausted"], "una vez, la peor"


def test_the_build_state_is_the_budgets_own() -> None:
    """La regla no recalcula la partida: lee su estado (``build_budget._state``)."""
    from datetime import date

    from nexus_api.db.models import PartnerBuildBudget
    from nexus_api.services.wallet.build_budget import _state

    for spent in (0, 79, 80, 99, 100, 120):
        row = PartnerBuildBudget(cap_micros=100, spent_micros=spent, month=date(2026, 11, 1))
        state = _state(row).state
        expected = {"ok": [], "warning": ["build_cap_warning"]}.get(state, ["build_cap_exhausted"])
        assert _codes(PartnerFacts(build=_build(spent, state=state))) == expected


def test_the_account_is_low_under_20_percent_of_what_was_loaded() -> None:
    assert _codes(PartnerFacts(account=_account(pct_left=20.0))) == []
    assert _codes(PartnerFacts(account=_account(pct_left=19.9))) == ["account_low"]


def test_the_account_is_low_under_7_days_at_the_last_7_days_pace() -> None:
    assert _codes(PartnerFacts(account=_account(days_left=7))) == []
    assert _codes(PartnerFacts(account=_account(days_left=6))) == ["account_low"]
    assert _codes(PartnerFacts(account=_account(days_left=None))) == [], "sin ritmo, no estima"


def test_the_account_is_never_less_than_what_the_notice_already_says() -> None:
    """research.md §R3: si ``wallet_alerts`` avisa al 80 % y la regla no lo listara,
    soltar la clave haría volver el aviso en cada tick."""
    assert _codes(PartnerFacts(account=_account(notice_pct_used=79.99))) == []
    assert _codes(PartnerFacts(account=_account(notice_pct_used=80.0))) == ["account_low"]
    assert _codes(PartnerFacts(account=_account(notice_pct_used=100.0))) == ["account_empty"]


def test_an_empty_account_is_said_once_the_worst() -> None:
    assert _codes(PartnerFacts(account=_account(available_micros=0, pct_left=0.0))) == [
        "account_empty"
    ]


def test_a_failed_payment() -> None:
    assert _codes(PartnerFacts(billing_failed=True)) == ["billing_payment_failed"]


def test_all_of_them_in_order() -> None:
    facts = PartnerFacts(
        build=_build(90), account=_account(available_micros=0), billing_failed=True
    )
    assert _codes(facts) == ["build_cap_warning", "account_empty", "billing_payment_failed"]


# ── las filas: gravedad, arreglo y datos ────────────────────────────────────


def test_the_severity_is_the_contracts() -> None:
    critical = {
        "build_cap_exhausted",
        "account_empty",
        "no_balance",
        "channel_problem",
        "billing_payment_failed",
    }
    for code in (*ATTENTION_REASONS, *PARTNER_REASONS):
        assert severity_of(code) == ("critical" if code in critical else "warning"), code


def test_the_partner_rows_carry_their_fix_and_their_figures() -> None:
    items = partner_items(
        PartnerFacts(
            build=_build(84, cap=100),
            account=_account(available_micros=7, pct_left=5.0, days_left=3),
            billing_failed=True,
        )
    )
    by_code = {i.code: i for i in items}
    build = by_code["build_cap_warning"]
    assert (build.scope, build.severity, build.ref, build.name) == (
        "partner",
        "warning",
        None,
        None,
    )
    assert (build.action, build.href) == ("request_build_extension", "/usage")
    assert build.data == {
        "pct": 84,
        "spent": {"amount_micros": 84, "currency": "USD"},
        "cap": {"amount_micros": 100, "currency": "USD"},
    }
    low = by_code["account_low"]
    assert (low.action, low.href, low.severity) == ("buy_balance", "/billing", "warning")
    assert low.data == {"available": {"amount_micros": 7, "currency": "USD"}, "days_left": 3}
    billing = by_code["billing_payment_failed"]
    assert (billing.action, billing.href, billing.severity) == (
        "fix_billing",
        "/billing",
        "critical",
    )


# ── el orden ────────────────────────────────────────────────────────────────


def _item(code: str, ref: str | None = None) -> AttentionItem:
    return AttentionItem(
        scope="client" if ref else "partner",
        severity=severity_of(code),
        code=code,
        ref=ref,
        name=None,
        count=1,
        action="x",
        href="/",
        data={},
    )


def test_worst_first_then_the_partner_then_the_reasons_and_the_ref() -> None:
    shuffled = [
        _item("low_balance", "b"),
        _item("account_low"),
        _item("no_agents", "a"),
        _item("channel_problem", "a"),
        _item("no_balance", "b"),
        _item("no_balance", "a"),
        _item("billing_payment_failed"),
        _item("build_cap_exhausted"),
        _item("agent_cap", "a"),
        _item("build_cap_warning"),
    ]
    assert [(i.code, i.ref) for i in order_items(shuffled)] == [
        ("build_cap_exhausted", None),
        ("billing_payment_failed", None),
        ("no_balance", "a"),
        ("no_balance", "b"),
        ("channel_problem", "a"),
        ("build_cap_warning", None),
        ("account_low", None),
        ("agent_cap", "a"),
        ("low_balance", "b"),
        ("no_agents", "a"),
    ]


# ── los avisos de condición (§2.1) ──────────────────────────────────────────


def test_each_condition_notice_maps_to_its_code() -> None:
    assert CONDITION_CODES == {
        "client.wallet.low": "low_balance",
        "client.wallet.empty": "no_balance",
        "build.budget.warning": "build_cap_warning",
        "build.budget.exhausted": "build_cap_exhausted",
        "wallet.low": "account_low",
        "wallet.empty": "account_empty",
        "agent.cap.reached": "agent_cap",
        "channel.problem": "channel_problem",
        "integration.reauth_required": "integration_reauth",
        "billing.payment_failed": "billing_payment_failed",
    }
    assert set(CONDITION_CODES.values()) <= set(ATTENTION_REASONS) | set(PARTNER_REASONS)
    assert {CONDITION_CODES[k] for k in PARTNER_CONDITION_KINDS} == set(PARTNER_REASONS)


def test_the_notice_kinds_exist() -> None:
    from nexus_api.db.models import NotificationKind

    known = {k.value for k in NotificationKind}
    assert set(CONDITION_CODES) <= known


def test_low_is_covered_by_its_empty_sibling() -> None:
    """research.md §R4: «queda poco» sigue siendo cierto con la cuenta agotada."""
    assert COVERED_BY == {
        "account_low": "account_empty",
        "low_balance": "no_balance",
        "build_cap_warning": "build_cap_exhausted",
    }


def test_the_account_thresholds_are_the_notices() -> None:
    from nexus_api.services import attention, wallet_alerts

    assert (attention.ACCOUNT_LOW_NOTICE_PCT, attention.ACCOUNT_EMPTY_NOTICE_PCT) == (
        wallet_alerts.THRESHOLDS
    )


# ── la cuenta a 0: primero comprar (owner, 2026-11-22) ─────────────────────────


def _client_row(code: str, action: str = "assign_balance") -> AttentionItem:
    return AttentionItem(
        scope="client",
        severity=severity_of(code),
        code=code,
        ref="flor",
        name="Flor",
        count=1,
        action=action,
        href="/clients/flor?assign=1",
    )


def _account_row(code: str) -> AttentionItem:
    return AttentionItem(
        scope="partner",
        severity=severity_of(code),
        code=code,
        ref=None,
        name=None,
        count=1,
        action="buy_balance",
        href="/billing",
    )


def test_with_the_account_empty_a_client_without_balance_is_fixed_by_buying_first() -> None:
    """Con la cuenta a 0 no hay saldo que asignar: quien puede comprar ve «Comprar
    saldo» en las filas de saldo de sus clientes, y lleva a Facturación."""
    items = [
        _account_row("account_empty"),
        _client_row("no_balance"),
        _client_row("low_balance"),
        _client_row("channel_problem", "fix_channel"),
    ]
    out = buy_first_when_empty(items, can_buy=True)
    assert [(i.code, i.action, i.href) for i in out] == [
        ("account_empty", "buy_balance", "/billing"),
        ("no_balance", "buy_balance", "/billing"),
        ("low_balance", "buy_balance", "/billing"),
        ("channel_problem", "fix_channel", "/clients/flor?assign=1"),
    ]


def test_buying_first_only_with_the_account_empty_and_for_who_can_buy() -> None:
    low = [_account_row("account_low"), _client_row("no_balance")]
    assert buy_first_when_empty(low, can_buy=True) == low, "con saldo bajo aún se puede asignar"
    empty = [
        _account_row("account_empty"),
        _client_row("no_balance"),
        _client_row("low_balance", "request_balance"),
    ]
    assert buy_first_when_empty(empty, can_buy=False) == empty, "quien no compra sigue con lo suyo"
    # Quien pide saldo lo sigue pidiendo: no asigna, así que no le toca comprar.
    asked = buy_first_when_empty(empty, can_buy=True)
    assert asked[2].action == "request_balance"
