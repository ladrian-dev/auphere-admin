"""The turn must tell the model what day it is, in the BUSINESS's timezone.

Regression cover for a production incident (Muna, 2026-08-19/20): nothing in
the message thread carried the current date, so the model answered from its
training prior. It offered "(ejemplo: 2025-08-30)" as the due-date format, the
admin copied the example, and a real accounts-receivable row was created dated
a year in the past — which also put its reminder windows permanently behind.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.pipeline import _build_handler_messages, _now_note

pytestmark = [pytest.mark.unit]

_NOW = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)  # 21:00 del 20-ago en Caracas


def _bundle(timezone: str = "America/Caracas") -> AgentBundle:
    return AgentBundle(
        tenant_id=uuid.uuid4(),
        version=1,
        version_id=uuid.uuid4(),
        system_prompt="Eres Sofía.",
        tools=frozenset(),
        timezone=timezone,
    )


def _state() -> dict[str, Any]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "channel_type": "whatsapp",
        "user_message": "cuánto debe Juan",
        "history": [],
    }


class TestNowNote:
    def test_renders_the_business_local_date_not_utc(self) -> None:
        note = _now_note("America/Caracas", now=_NOW)
        # 01:00 UTC on the 21st is still the 20th at 21:00 in Caracas.
        assert "20/08/2026" in note
        assert "2026-08-20" in note
        assert "21:00" in note
        assert "America/Caracas" in note

    def test_utc_tenant_sees_the_utc_date(self) -> None:
        note = _now_note("UTC", now=_NOW)
        assert "21/08/2026" in note
        assert "2026-08-21" in note

    def test_names_the_weekday_in_spanish(self) -> None:
        # 2026-08-20 was a Thursday.
        assert "jueves" in _now_note("America/Caracas", now=_NOW)

    def test_forbids_guessing(self) -> None:
        note = _now_note("America/Caracas", now=_NOW)
        assert "NUNCA" in note

    def test_unknown_timezone_degrades_to_utc_visibly(self) -> None:
        """A malformed tenant timezone must not kill the turn, and must not
        quietly claim a local date we did not compute."""
        note = _now_note("Mars/Olympus_Mons", now=_NOW)
        assert "21/08/2026" in note
        assert "UTC" in note
        assert "Mars" not in note


class TestInjectedIntoEveryTurn:
    def test_date_block_is_present_before_the_user_message(self) -> None:
        msgs = _build_handler_messages(
            _state(),  # type: ignore[arg-type]
            _bundle(),
            intent="info",
            kg_snapshot="",
        )
        systems = [m["content"] for m in msgs if m["role"] == "system"]
        assert any("zona horaria del negocio" in c for c in systems)
        assert msgs[-1]["role"] == "user"

    def test_uses_the_tenants_timezone_not_a_constant(self) -> None:
        caracas = _build_handler_messages(
            _state(),  # type: ignore[arg-type]
            _bundle("America/Caracas"),
            intent="info",
            kg_snapshot="",
        )
        santiago = _build_handler_messages(
            _state(),  # type: ignore[arg-type]
            _bundle("America/Santiago"),
            intent="info",
            kg_snapshot="",
        )
        note_of = lambda msgs: next(  # noqa: E731
            m["content"] for m in msgs if "zona horaria del negocio" in m["content"]
        )
        assert "America/Caracas" in note_of(caracas)
        assert "America/Santiago" in note_of(santiago)


class TestBundleCarriesTimezone:
    def test_defaults_to_utc_when_the_tenant_has_none(self) -> None:
        bundle = AgentBundle(
            tenant_id=uuid.uuid4(),
            version=1,
            version_id=uuid.uuid4(),
            system_prompt="",
            tools=frozenset(),
        )
        assert bundle.timezone == "UTC"
