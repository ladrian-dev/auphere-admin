"""Spec 047, T011 — la regla única de atención (requisitos 7.2 y 7.3).

Una sola regla dice si un cliente «necesita atención» y por qué, la misma en la
lista de clientes, en el Panel del partner y en ⌘K. Aquí se fija:

- **los 7 motivos** del requisito 7.2, cada uno con su caso;
- **su orden**, de más a menos grave (es el orden de «Necesita tu atención» del
  Panel, requisito 48.2);
- **el orden de la lista** (7.3): primero los que necesitan algo y, dentro de
  cada grupo, de menos a más días de saldo; con bolsas de monedas distintas se
  compara por días y porcentaje, nunca por importe (7.5).

Los escenarios de la historia 15 van con su número.
"""

from __future__ import annotations

import dataclasses

import pytest

from nexus_api.services.agent_lifecycle import AgentFacts, ChannelFacts
from nexus_api.services.attention import (
    ATTENTION_REASONS,
    LOW_BALANCE_DAYS,
    LOW_BALANCE_PCT,
    AttentionReason,
    ClientFacts,
    attention,
    list_order,
)

EVERYONE = ChannelFacts(audience_mode="everyone")
TEAM = ChannelFacts(audience_mode="team_only")
SERVING = AgentFacts(life="published", channels=(EVERYONE,))


def _client(ref: str = "c", **overrides: object) -> ClientFacts:
    """A client in order: a serving agent and a healthy bag."""
    base: dict[str, object] = {
        "ref": ref,
        "pct_left": 80.0,
        "days_left": 25.0,
        "agents": (SERVING,),
    }
    base.update(overrides)
    return ClientFacts(**base)  # type: ignore[arg-type]


def _codes(facts: ClientFacts) -> list[str]:
    return [r.code for r in attention(facts).reasons]


# ── los motivos ────────────────────────────────────────────────────────────


def test_the_reasons_are_the_seven_in_order_of_gravity() -> None:
    assert ATTENTION_REASONS == (
        "no_balance",
        "channel_problem",
        "integration_reauth",
        "agent_cap",
        "agent_without_channel",
        "low_balance",
        "no_agents",
    )


def test_a_client_in_order_needs_nothing() -> None:
    result = attention(_client())
    assert result.reasons == ()
    assert result.needs_attention is False
    assert result.top is None


def test_1_no_balance() -> None:
    # Historia 15, escenario 1: the bag at zero.
    assert _codes(_client(bag_empty=True, pct_left=0.0, days_left=0.0)) == ["no_balance"]


def test_no_balance_is_not_also_low_balance() -> None:
    # Zero is below 20 % too; the list says the worse one once.
    assert "low_balance" not in _codes(_client(bag_empty=True, pct_left=0.0, days_left=0.0))


@pytest.mark.parametrize(
    "channel",
    [
        ChannelFacts(status="degraded", audience_mode="everyone", problem_reason="quality"),
        ChannelFacts(status="degraded", problem_reason="coexistence_inactive"),
        ChannelFacts(status="disconnected", audience_mode="everyone"),
    ],
    ids=["degraded", "coexistence", "disconnected_unasked"],
)
def test_2_a_channel_with_problems_or_disconnected_unasked(channel: ChannelFacts) -> None:
    agent = AgentFacts(life="published", channels=(EVERYONE, channel))
    result = attention(_client(agents=(agent,)))
    assert result.reasons == (AttentionReason("channel_problem", 1),)


def test_a_disconnection_someone_asked_for_is_not_a_problem() -> None:
    asked = ChannelFacts(status="disconnected", disconnected_on_request=True)
    agent = AgentFacts(life="published", channels=(EVERYONE, asked))
    assert _codes(_client(agents=(agent,))) == []


def test_a_paused_channel_is_not_a_problem() -> None:
    paused = ChannelFacts(status="paused", audience_mode="everyone")
    agent = AgentFacts(life="published", channels=(EVERYONE, paused))
    assert _codes(_client(agents=(agent,))) == []


def test_channel_problems_are_counted_across_agents() -> None:
    bad = ChannelFacts(status="degraded", audience_mode="everyone", problem_reason="meta_error")
    agents = (
        AgentFacts(life="published", channels=(EVERYONE, bad)),
        AgentFacts(life="paused", pause_reason="manual", channels=(bad,)),
    )
    assert attention(_client(agents=agents)).reasons[0] == AttentionReason("channel_problem", 2)


def test_3_an_integration_to_reauthorize() -> None:
    result = attention(_client(reauth_integrations=2))
    assert result.reasons == (AttentionReason("integration_reauth", 2),)


def test_4_an_agent_paused_by_its_cap() -> None:
    capped = AgentFacts(life="paused", pause_reason="agent_cap", channels=(EVERYONE,))
    result = attention(_client(agents=(SERVING, capped)))
    assert result.reasons == (AttentionReason("agent_cap", 1),)


def test_a_manual_pause_is_not_a_cap() -> None:
    paused = AgentFacts(life="paused", pause_reason="manual", channels=(EVERYONE,))
    assert _codes(_client(agents=(SERVING, paused))) == []


@pytest.mark.parametrize(
    "agent",
    [
        AgentFacts(life="published"),  # «Listo · sin canal»
        AgentFacts(life="published", channels=(ChannelFacts(audience_mode="unset"),)),
        AgentFacts(life="published", channels=(TEAM,)),  # «En prueba»
    ],
    ids=["no_channel", "unconfigured", "testing"],
)
def test_5_an_agent_saved_or_testing_without_a_channel(agent: AgentFacts) -> None:
    # Historia 15, escenario 3: «1 agente sin canal», with the Panel's rule.
    result = attention(_client(agents=(SERVING, agent)))
    assert result.reasons == (AttentionReason("agent_without_channel", 1),)


def test_a_draft_is_not_an_agent_without_a_channel() -> None:
    assert _codes(_client(agents=(SERVING, AgentFacts(life="draft")))) == []


@pytest.mark.parametrize(
    ("pct_left", "days_left"),
    [(19.9, 25.0), (80.0, 6.5), (10.0, 3.0)],
    ids=["below_20_pct", "under_7_days", "both"],
)
def test_6_low_balance(pct_left: float, days_left: float) -> None:
    # Historia 15, escenario 2: «Saldo bajo · quedan 4 días».
    assert _codes(_client(pct_left=pct_left, days_left=days_left)) == ["low_balance"]


def test_the_low_balance_thresholds() -> None:
    assert (LOW_BALANCE_PCT, LOW_BALANCE_DAYS) == (20, 7)
    # The limits themselves are not low.
    assert _codes(_client(pct_left=20.0, days_left=7.0)) == []


def test_without_data_to_estimate_days_only_the_percentage_counts() -> None:
    # Fewer than 3 days of spend: ``days_left`` is unknown, not zero.
    assert _codes(_client(pct_left=80.0, days_left=None)) == []
    assert _codes(_client(pct_left=15.0, days_left=None)) == ["low_balance"]


def test_7_no_agents() -> None:
    assert _codes(_client(agents=())) == ["no_agents"]


def test_archived_agents_do_not_count_as_agents() -> None:
    gone = AgentFacts(life="archived", channels=(EVERYONE,))
    assert _codes(_client(agents=(gone,))) == ["no_agents"]


def test_every_reason_at_once_comes_in_order_of_gravity() -> None:
    bad = ChannelFacts(status="degraded", problem_reason="auth_expired")
    agents = (
        AgentFacts(life="published", channels=(bad,)),
        AgentFacts(life="paused", pause_reason="agent_cap"),
    )
    facts = _client(
        bag_empty=True, pct_left=0.0, days_left=0.0, reauth_integrations=1, agents=agents
    )
    assert _codes(facts) == [
        "no_balance",
        "channel_problem",
        "integration_reauth",
        "agent_cap",
        "agent_without_channel",
    ]
    assert attention(facts).top == AttentionReason("no_balance", 1)


def test_low_balance_and_no_agents_keep_their_place() -> None:
    assert _codes(_client(pct_left=5.0, days_left=2.0, agents=())) == ["low_balance", "no_agents"]


def test_an_archived_client_needs_nothing() -> None:
    # Archiving parks the client on purpose: its agents are paused and its bag
    # does not run. It is listed under «Archivados», never under «Necesitan atención».
    facts = _client(archived=True, bag_empty=True, pct_left=0.0, days_left=0.0, agents=())
    assert attention(facts).needs_attention is False


# ── el orden de la lista ───────────────────────────────────────────────────


def _refs(clients: list[ClientFacts]) -> list[str]:
    return [c.ref for c in list_order(clients)]


def test_attention_first_then_fewer_days_within_each_group() -> None:
    clients = [
        _client("ok-long", days_left=40.0),
        _client("low-9d", pct_left=10.0, days_left=9.0),
        _client("ok-short", days_left=12.0),
        _client("low-3d", pct_left=50.0, days_left=3.0),
        _client("reauth-30d", days_left=30.0, reauth_integrations=1),
    ]
    assert _refs(clients) == ["low-3d", "low-9d", "reauth-30d", "ok-short", "ok-long"]


def test_an_empty_bag_comes_first() -> None:
    # Historia 15, escenario 1: with no spend data its days are unknown, and it
    # still goes first — an empty bag has no days left.
    clients = [
        _client("low", pct_left=5.0, days_left=1.0),
        _client("empty", bag_empty=True, pct_left=0.0, days_left=None),
    ]
    assert _refs(clients) == ["empty", "low"]


def test_unknown_days_go_last_within_their_group() -> None:
    clients = [_client("unknown", days_left=None), _client("known", days_left=60.0)]
    assert _refs(clients) == ["known", "unknown"]


def test_equal_days_break_on_the_percentage_then_the_ref() -> None:
    clients = [
        _client("b", pct_left=60.0, days_left=20.0),
        _client("c", pct_left=40.0, days_left=20.0),
        _client("a", pct_left=60.0, days_left=20.0),
    ]
    assert _refs(clients) == ["c", "a", "b"]


def test_bags_in_different_currencies_compare_by_days_never_by_amount() -> None:
    # Historia 15, escenario 4. The rule cannot even see an amount.
    names = {f.name for f in dataclasses.fields(ClientFacts)}
    assert not names & {"balance", "amount", "amount_micros", "currency"}
    eur_big = _client("eur-big", pct_left=50.0, days_left=10.0)
    usd_small = _client("usd-small", pct_left=50.0, days_left=4.0)
    assert _refs([eur_big, usd_small]) == ["usd-small", "eur-big"]
