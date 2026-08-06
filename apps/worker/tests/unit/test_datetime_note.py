"""The per-turn 'current date/time' system note (business timezone).

Injected so the agent can resolve relative dates (hoy/mañana/el viernes) and
know WHEN a change is made — it doesn't otherwise receive 'now'.
"""

from __future__ import annotations

import pytest

from nexus_worker.runtime.pipeline import _current_datetime_note

pytestmark = [pytest.mark.unit]

_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def test_spanish_format_and_iso() -> None:
    note = _current_datetime_note("America/Caracas")
    assert note.startswith("FECHA Y HORA ACTUAL:")
    assert "zona horaria America/Caracas" in note
    assert "ISO " in note
    assert any(d in note for d in _DAYS), note


def test_invalid_timezone_falls_back_to_utc() -> None:
    note = _current_datetime_note("Not/AReal_Zone")
    assert "zona horaria UTC" in note
