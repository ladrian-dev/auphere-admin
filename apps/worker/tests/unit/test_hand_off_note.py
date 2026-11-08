"""QA de staging del 2026-11-08 (H-02): el agente decía «te paso con alguien del equipo» y no
llamaba a la herramienta, así que nadie se enteraba. Con la herramienta en el turno, una nota del
sistema le recuerda que pasar la conversación es llamarla, no decirlo."""

from __future__ import annotations

from nexus_worker.runtime.pipeline import _HAND_OFF_NOTE, _hand_off_note_applies

TOOL = "escalate.escalate_to_human"


def test_the_note_names_the_tool_it_asks_for() -> None:
    assert TOOL in _HAND_OFF_NOTE


def test_the_note_forbids_saying_it_without_calling_it() -> None:
    folded = _HAND_OFF_NOTE.lower()
    assert "nunca" in folded and "sin" in folded


def test_only_when_the_turn_offers_the_tool() -> None:
    assert _hand_off_note_applies((TOOL, "reservas.create"))
    assert not _hand_off_note_applies(("reservas.create", "reservas.find_slots"))
    assert not _hand_off_note_applies(())
