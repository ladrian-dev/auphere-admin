"""History only keeps the text of each message. A turn after a booking read its own
«your appointment is booked» with nothing behind it and told the customer it had not
been created (staging, Jemma's Hair, 2026-11-04). The turn is reminded of what its tools
did: the tool, its status and when, never what went in or came back.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from nexus_api.db.models import MessageDirection

from nexus_worker.runtime import pipeline
from nexus_worker.runtime.pipeline import _tools_already_used


def _call(tool: str, status: str = "ok", at: str = "2026-11-04T18:27:04+00:00") -> dict[str, Any]:
    return {
        "tool": tool,
        "status": status,
        "executed_at": at,
        "args": {"summary": "Corte de damas - Carla"},
        "result": {"data": {"id": "evt_secret"}},
    }


def test_no_tools_no_note() -> None:
    assert _tools_already_used([]) is None
    assert _tools_already_used([[], []]) is None


def test_the_note_says_what_ran_and_that_it_is_not_to_be_denied() -> None:
    note = _tools_already_used([[_call("GOOGLECALENDAR_CREATE_EVENT")]])

    assert note is not None
    assert note["role"] == "system"
    assert "2026-11-04 18:27 UTC · GOOGLECALENDAR_CREATE_EVENT: ok" in note["content"]
    assert "do not deny it" in note["content"]


def test_a_failed_tool_says_so() -> None:
    note = _tools_already_used([[_call("GOOGLECALENDAR_CREATE_EVENT", status="error")]])

    assert note is not None
    assert "GOOGLECALENDAR_CREATE_EVENT: error" in note["content"]


def test_what_went_in_and_came_back_stays_out() -> None:
    note = _tools_already_used([[_call("GOOGLECALENDAR_CREATE_EVENT")]])

    assert note is not None
    assert "Carla" not in note["content"]
    assert "evt_secret" not in note["content"]


def test_a_text_row_and_its_interactive_row_count_once() -> None:
    same = _call("GOOGLECALENDAR_CREATE_EVENT")
    note = _tools_already_used([[same], [same]])

    assert note is not None
    assert note["content"].count("GOOGLECALENDAR_CREATE_EVENT") == 1


def test_only_the_latest_ones_are_remembered() -> None:
    turns = [[_call(f"tool_{i}", at=f"2026-11-04T18:{i:02d}:00+00:00")] for i in range(15)]
    note = _tools_already_used(turns)

    assert note is not None
    assert "tool_14" in note["content"]
    assert "tool_4:" not in note["content"]


def test_malformed_rows_are_skipped() -> None:
    assert _tools_already_used([["nope", {"status": "ok"}]]) is None


async def test_the_note_goes_after_the_history_and_outside_the_cached_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [  # newest first, as the database gives them
        SimpleNamespace(
            id="now", direction=MessageDirection.INBOUND, content="Gracias", tool_calls=[]
        ),
        SimpleNamespace(
            id="reply",
            direction=MessageDirection.OUTBOUND,
            content="Cita confirmada",
            tool_calls=[_call("GOOGLECALENDAR_CREATE_EVENT")],
        ),
        SimpleNamespace(
            id="ask", direction=MessageDirection.INBOUND, content="Quiero cita", tool_calls=[]
        ),
    ]

    class _Session:
        async def execute(self, _query: Any) -> Any:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    @asynccontextmanager
    async def _sessions() -> AsyncIterator[_Session]:
        yield _Session()

    @asynccontextmanager
    async def _scoped(_session: Any, _tenant: Any) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(pipeline, "get_sessionmaker", lambda: _sessions)
    monkeypatch.setattr(pipeline, "tenant_scoped_session", _scoped)

    history = await pipeline._load_recent_history(
        uuid.uuid4(), str(uuid.uuid4()), exclude_message_id="now"
    )

    assert [m["role"] for m in history] == ["user", "assistant", "system"]
    assert history[1]["content"] == "Cita confirmada", "the text stays as it was"
    assert "GOOGLECALENDAR_CREATE_EVENT: ok" in history[2]["content"]
