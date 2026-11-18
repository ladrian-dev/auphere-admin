"""Spec 063, requisito 2.6 — «Listo · sin canal» no es verdad si tiene un número.

En prod (2026-11-18), Ana tenía un número «Sin configurar» y su cabecera decía
«Listo · sin canal». El código sigue siendo ``ready_no_channel``, porque ningún
número responde, y los recuentos no cambian. Pero lleva ``reason="unconfigured"``
para que la consola diga «Listo · número sin configurar».
"""

from __future__ import annotations

from nexus_api.services.agent_lifecycle import ChannelFacts, visible_state


def test_a_published_agent_with_only_an_unconfigured_number_says_so() -> None:
    state = visible_state(
        "published", channels=[ChannelFacts(status="active", audience_mode="unset")]
    )
    assert state.code == "ready_no_channel"
    assert state.reason == "unconfigured"


def test_without_numbers_there_is_no_reason() -> None:
    state = visible_state("published", channels=[])
    assert state.code == "ready_no_channel"
    assert state.reason is None


def test_a_number_that_answers_is_still_what_counts() -> None:
    channels = [ChannelFacts(audience_mode="unset"), ChannelFacts(audience_mode="team_only")]
    state = visible_state("published", channels=channels)
    assert state.code == "testing"
    assert state.reason is None


def test_a_paused_or_disconnected_number_is_not_an_unconfigured_one() -> None:
    for facts in (ChannelFacts(status="paused"), ChannelFacts(status="disconnected")):
        state = visible_state("published", channels=[facts])
        assert state.code == "ready_no_channel"
        assert state.reason is None
