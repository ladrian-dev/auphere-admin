"""Unit tests for ``SkillRef`` — the per-skill entry in
``agent_config.runtime_skills``.

The schema gained an optional ``channels`` field in PR "channel-gated
skills" (2026-05-24). The runtime filter that consumes it lives in
``apps/worker/.../pipeline.py::_filter_skills_for_channel`` — these
tests cover the schema side: defaults, accepted values, and validation
of unknown channel names. The handler-side filtering is covered by
``apps/worker/tests/unit/test_skills_pipeline.py::TestChannelGating*``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexus_api.schemas.agent_config import SkillRef


class TestSkillRefChannels:
    def test_channels_defaults_to_none(self) -> None:
        ref = SkillRef(skill_id="skill_abc")
        assert ref.channels is None
        # When dumped, the absence travels as ``None``; the runtime
        # treats that as 'load for every channel' (back-compat).
        assert ref.model_dump()["channels"] is None

    def test_channels_accepts_known_values(self) -> None:
        ref = SkillRef(
            skill_id="skill_wa",
            channels=["whatsapp", "instagram"],
        )
        assert ref.channels == ["whatsapp", "instagram"]

    def test_channels_accepts_empty_list(self) -> None:
        """An empty list is semantically equivalent to None — the runtime
        treats both as 'load everywhere'. The schema must not reject it
        so admin UIs that send an unselected multi-select round-trip
        cleanly."""
        ref = SkillRef(skill_id="skill_x", channels=[])
        assert ref.channels == []

    def test_channels_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SkillRef(skill_id="skill_x", channels=["sms"])
        # The error must name the bad channel so the admin sees what to fix.
        assert "sms" in str(exc.value)

    def test_channels_rejects_mixed_known_and_unknown(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SkillRef(
                skill_id="skill_x",
                channels=["whatsapp", "telegrama"],
            )
        assert "telegrama" in str(exc.value)
