"""Spec 047, T010 — el estado visible del agente y del canal (requisitos 25.3 y 25.5).

La tabla de ``contracts/events.md`` §1.3 (agente) y §1.2 (canal), fila a fila,
y las reglas que la tabla deja dichas en una línea:

- **en orden, la primera que se cumple**: un agente archivado o en pausa lo dice
  aunque tenga un canal «A todos»;
- **un canal en pausa o con problemas no cuenta** como «A todos» ni como «Solo
  mi equipo»: el agente no atiende por él;
- **un solo cálculo** (25.5): el código, el tono y el motivo salen de aquí; la
  consola, la consola lite, la app y el Panel solo los pintan.

Los textos («Atendiendo», «Pausado · {motivo}») son de la interfaz; aquí se fijan
los códigos, los tonos y los motivos.
"""

from __future__ import annotations

import pytest

from nexus_api.services.agent_lifecycle import (
    AGENT_LIFE_STATES,
    AGENT_VISIBLE_STATES,
    CHANNEL_VISIBLE_STATES,
    PAUSE_REASONS,
    PROBLEM_REASONS,
    AgentFacts,
    ChannelFacts,
    VisibleState,
    agent_visible_state,
    channel_visible_state,
    visible_state,
)

EVERYONE = ChannelFacts(status="active", audience_mode="everyone")
TEAM = ChannelFacts(status="active", audience_mode="team_only")
UNSET = ChannelFacts(status="active", audience_mode="unset")


# ── §1.2 · el canal ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            ChannelFacts(owner_link_pending=True, has_number=False),
            VisibleState("pending_link", "info"),
        ),
        (ChannelFacts(status="disconnected"), VisibleState("disconnected", "muted")),
        (
            ChannelFacts(status="degraded", problem_reason="auth_expired"),
            VisibleState("problem", "danger", "auth_expired"),
        ),
        (ChannelFacts(status="paused", audience_mode="everyone"), VisibleState("paused", "warn")),
        (UNSET, VisibleState("unconfigured", "muted")),
        (TEAM, VisibleState("team_only", "info")),
        (EVERYONE, VisibleState("everyone", "positive")),
    ],
    ids=["pending_link", "disconnected", "problem", "paused", "unconfigured", "team", "everyone"],
)
def test_each_row_of_the_channel_table(facts: ChannelFacts, expected: VisibleState) -> None:
    assert channel_visible_state(facts) == expected


def test_the_channel_codes_are_the_table_in_its_order() -> None:
    assert CHANNEL_VISIBLE_STATES == (
        "pending_link",
        "disconnected",
        "problem",
        "paused",
        "unconfigured",
        "team_only",
        "everyone",
    )


def test_a_pending_link_wins_while_there_is_no_number() -> None:
    # Pending and still without a number: whatever else the row says.
    pending = ChannelFacts(
        status="disconnected", audience_mode="everyone", owner_link_pending=True, has_number=False
    )
    assert channel_visible_state(pending).code == "pending_link"
    # Once the number exists, the link is history: the channel speaks for itself.
    linked = ChannelFacts(audience_mode="everyone", owner_link_pending=True, has_number=True)
    assert channel_visible_state(linked).code == "everyone"


def test_the_order_of_the_stored_status_over_the_audience() -> None:
    # The audience is kept while the channel is paused, degraded or
    # disconnected (25.4); the status says it does not answer.
    assert channel_visible_state(ChannelFacts("disconnected", "everyone")).code == "disconnected"
    assert channel_visible_state(ChannelFacts("degraded", "team_only")).code == "problem"
    assert channel_visible_state(ChannelFacts("paused", "team_only")).code == "paused"


@pytest.mark.parametrize("reason", PROBLEM_REASONS)
def test_a_problem_carries_its_reason(reason: str) -> None:
    state = channel_visible_state(ChannelFacts(status="degraded", problem_reason=reason))
    assert state == VisibleState("problem", "danger", reason)


def test_the_problem_reasons_are_the_closed_list() -> None:
    assert PROBLEM_REASONS == ("quality", "auth_expired", "coexistence_inactive", "meta_error")


def test_only_a_problem_carries_a_reason() -> None:
    # A stale reason left on a channel that recovered does not leak.
    state = channel_visible_state(ChannelFacts(audience_mode="everyone", problem_reason="quality"))
    assert state.reason is None


@pytest.mark.parametrize(
    "facts",
    [
        ChannelFacts(status="broken"),
        ChannelFacts(audience_mode="some"),
        ChannelFacts(status="degraded", problem_reason="it_rained"),
    ],
    ids=["status", "audience", "problem_reason"],
)
def test_a_value_outside_the_vocabulary_is_refused(facts: ChannelFacts) -> None:
    with pytest.raises(ValueError):
        channel_visible_state(facts)


# ── §1.3 · el agente ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("life", "pause_reason", "channels", "expected"),
    [
        ("archived", None, (EVERYONE,), VisibleState("archived", "muted")),
        ("paused", "manual", (EVERYONE,), VisibleState("paused", "warn", "manual")),
        ("draft", None, (EVERYONE,), VisibleState("draft", "muted")),
        ("published", None, (TEAM, EVERYONE), VisibleState("serving", "positive")),
        ("published", None, (TEAM, UNSET), VisibleState("testing", "info")),
        ("published", None, (), VisibleState("ready_no_channel", "info")),
        ("published", None, (UNSET,), VisibleState("ready_no_channel", "info")),
    ],
    ids=["archived", "paused", "draft", "serving", "testing", "no_channel", "unconfigured"],
)
def test_each_row_of_the_agent_table(
    life: str,
    pause_reason: str | None,
    channels: tuple[ChannelFacts, ...],
    expected: VisibleState,
) -> None:
    assert visible_state(life, pause_reason=pause_reason, channels=channels) == expected


def test_the_agent_codes_are_the_table_in_its_order() -> None:
    assert AGENT_VISIBLE_STATES == (
        "archived",
        "paused",
        "draft",
        "serving",
        "testing",
        "ready_no_channel",
    )


def test_the_stored_life_states_and_pause_reasons_are_the_closed_lists() -> None:
    assert AGENT_LIFE_STATES == ("draft", "published", "paused", "archived")
    assert PAUSE_REASONS == (
        "manual",
        "no_balance",
        "agent_cap",
        "client_paused",
        "client_archived",
    )


@pytest.mark.parametrize("reason", PAUSE_REASONS)
def test_a_paused_agent_says_why(reason: str) -> None:
    assert visible_state("paused", pause_reason=reason) == VisibleState("paused", "warn", reason)


def test_only_a_paused_agent_carries_a_reason() -> None:
    state = visible_state("published", pause_reason="manual", channels=(EVERYONE,))
    assert state == VisibleState("serving", "positive")


@pytest.mark.parametrize(
    "channel",
    [
        ChannelFacts(status="paused", audience_mode="everyone"),
        ChannelFacts(status="degraded", audience_mode="everyone", problem_reason="quality"),
        ChannelFacts(status="disconnected", audience_mode="everyone"),
    ],
    ids=["paused", "problem", "disconnected"],
)
def test_a_channel_that_does_not_answer_never_counts_as_everyone(channel: ChannelFacts) -> None:
    assert visible_state("published", channels=(channel,)).code == "ready_no_channel"
    # …nor hides the team channel that does answer.
    assert visible_state("published", channels=(channel, TEAM)).code == "testing"


@pytest.mark.parametrize(
    "channel",
    [
        ChannelFacts(status="paused", audience_mode="team_only"),
        ChannelFacts(status="degraded", audience_mode="team_only", problem_reason="meta_error"),
    ],
    ids=["paused", "problem"],
)
def test_a_channel_that_does_not_answer_never_counts_as_team_only(channel: ChannelFacts) -> None:
    assert visible_state("published", channels=(channel,)).code == "ready_no_channel"


def test_pausing_does_not_need_the_channels_to_change() -> None:
    # 25.4: the channels keep their audience; the agent's life decides.
    for life in ("paused", "archived", "draft"):
        assert visible_state(life, channels=(EVERYONE,)).code != "serving"


def test_agent_facts_compose_the_same_calculation() -> None:
    facts = AgentFacts(life="published", channels=(TEAM,))
    assert agent_visible_state(facts) == visible_state("published", channels=(TEAM,))
    paused = AgentFacts(life="paused", pause_reason="agent_cap", channels=(EVERYONE,))
    assert agent_visible_state(paused) == VisibleState("paused", "warn", "agent_cap")


@pytest.mark.parametrize(
    ("life", "pause_reason"),
    [("live", None), ("paused", "because")],
    ids=["life", "pause_reason"],
)
def test_an_agent_value_outside_the_vocabulary_is_refused(
    life: str, pause_reason: str | None
) -> None:
    with pytest.raises(ValueError):
        visible_state(life, pause_reason=pause_reason)


def test_every_code_has_one_tone_from_the_badge_palette() -> None:
    tones = {"positive", "info", "warn", "danger", "muted"}
    states = [channel_visible_state(f) for f in (EVERYONE, TEAM, UNSET)] + [
        visible_state(life, pause_reason="manual" if life == "paused" else None)
        for life in AGENT_LIFE_STATES
    ]
    assert {s.tone for s in states} <= tones
