"""INC-61: when the model is down, the fixed lines follow the customer's language."""

from __future__ import annotations

from typing import Any, cast

import pytest

from nexus_worker.runtime import pipeline


def _state(text: str | None) -> Any:
    return cast(Any, {"user_message": text})


@pytest.mark.parametrize(
    "text",
    ["Can I book a demo?", "How much does it cost?", "I'd like to talk to a person, please."],
)
def test_english_gets_english(text: str) -> None:
    assert pipeline._apology(_state(text)) == pipeline._EMPTY_RESPONSE_FALLBACK_EN
    assert pipeline._handoff_line(_state(text)) == pipeline._HANDOFF_RESPONSE_EN


@pytest.mark.parametrize(
    "text",
    ["¿A qué hora abrís mañana?", "Quiero una cita", "Hola, ¿cuánto cuesta?"],
)
def test_spanish_stays_spanish(text: str) -> None:
    assert pipeline._apology(_state(text)) == pipeline._EMPTY_RESPONSE_FALLBACK
    assert pipeline._handoff_line(_state(text)) == pipeline._HANDOFF_RESPONSE


@pytest.mark.parametrize("text", [None, "", "👍", "12345", "Bonjour"])
def test_what_cannot_be_told_keeps_the_default(text: str | None) -> None:
    assert pipeline._apology(_state(text)) == pipeline._EMPTY_RESPONSE_FALLBACK
