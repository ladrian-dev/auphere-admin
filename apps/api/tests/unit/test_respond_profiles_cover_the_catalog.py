"""Spec 065, T006 (requisitos 1.3, 4.1, 4.2, 4.7, 11.1): un perfil de llamada por modelo.

``nexus_api.core.respond_profiles`` es la única fuente de cómo se llama a cada modelo que
puede responder: parámetros, razonamiento, ``max_tokens``, plazo, reserva y lo que nunca se
manda (research.md §D12). Un modelo sin perfil no se ofrece, no se habilita y no es reserva.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa

from nexus_api.core.respond_profiles import PROFILES, RespondProfile, profile_for

SIX = (
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
    "anthropic/claude-opus-5-5",
    "anthropic/claude-sonnet-5-5",
    "anthropic/claude-haiku-5-5",
)
_MIGRATIONS = Path(__file__).resolve().parents[2] / "alembic/versions"


def test_there_is_a_profile_for_each_of_the_six() -> None:
    assert set(SIX) <= set(PROFILES)
    for model_id in SIX:
        profile = profile_for(model_id)
        assert isinstance(profile, RespondProfile)
        assert profile.model_id == model_id
        assert profile.family in {"openai", "anthropic"}
        assert profile.timeout_s > 0
        assert profile.estimate_factor > 0


@pytest.mark.parametrize("model_id", SIX)
def test_the_reserve_is_of_the_other_family_and_has_a_profile(model_id: str) -> None:
    profile = profile_for(model_id)
    reserve = profile_for(profile.reserve)
    assert reserve is not None, f"la reserva de {model_id} no tiene perfil"
    assert reserve.family != profile.family


def test_openai_goes_to_sonnet_and_anthropic_to_terra() -> None:
    for model_id in SIX:
        expected = (
            "anthropic/claude-sonnet-5-5"
            if model_id.startswith("openai/")
            else "openai/gpt-5.6-terra"
        )
        assert profile_for(model_id).reserve == expected  # type: ignore[union-attr]


def test_nothing_anthropic_only_goes_to_openai_nor_the_reverse() -> None:
    for model_id in SIX:
        profile = profile_for(model_id)
        assert profile is not None
        if profile.family == "openai":
            assert {"thinking", "output_config", "context_management"} <= profile.forbidden
            assert not profile.keeps_reasoning
            assert profile.block_binding is None
        else:
            assert {"temperature", "top_p", "top_k", "reasoning_effort"} <= profile.forbidden
            assert profile.keeps_reasoning
            assert profile.max_tokens == 8192
            assert profile.request.get("output_config") == {"effort": "low"}
            assert profile.block_binding == {"prefix_mismatch_behavior": "drop_block"}


def test_opus_and_sonnet_never_get_a_forced_tool_choice() -> None:
    for model_id in ("anthropic/claude-opus-5-5", "anthropic/claude-sonnet-5-5"):
        assert "tool_choice_forced" in profile_for(model_id).forbidden  # type: ignore[union-attr]


def test_the_cross_of_sonnet_is_between_tools_and_nothing_else() -> None:
    sonnet = profile_for("anthropic/claude-sonnet-5-5")
    assert sonnet is not None
    assert sonnet.cross_in_request == {"thinking": {"type": "between_tools"}}
    for model_id in SIX:
        profile = profile_for(model_id)
        assert profile is not None
        if profile.cross_in_request is not None:
            assert "block_binding" not in str(profile.cross_in_request)


def test_the_timeouts_are_the_plans() -> None:
    assert profile_for("anthropic/claude-opus-5-5").timeout_s == 90  # type: ignore[union-attr]
    assert profile_for("anthropic/claude-sonnet-5-5").timeout_s == 60  # type: ignore[union-attr]
    assert profile_for("anthropic/claude-haiku-5-5").timeout_s == 45  # type: ignore[union-attr]
    assert profile_for("openai/gpt-5.6-sol").timeout_s == 30  # type: ignore[union-attr]


def test_only_anthropic_runs_skills_and_its_mcp_connector() -> None:
    for model_id in SIX:
        profile = profile_for(model_id)
        assert profile is not None
        if profile.family == "anthropic":
            assert {"anthropic_skills", "anthropic_mcp"} <= profile.supports
        else:
            assert not profile.supports


def test_a_model_without_profile_has_none() -> None:
    assert profile_for("anthropic/claude-sonnet-4-6") is None


def test_every_model_with_an_offer_label_in_the_migrations_has_a_profile() -> None:
    labelled: set[str] = set()
    for path in _MIGRATIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "offer_label" not in text:
            continue
        labelled.update(re.findall(r'"((?:openai|anthropic)/[a-z0-9._-]+)":\s*"', text))
    assert labelled, "no encontré etiquetas de oferta en las migraciones"
    missing = sorted(m for m in labelled if profile_for(m) is None)
    assert missing == [], f"con etiqueta de oferta y sin perfil: {missing}"


@pytest.mark.asyncio
async def test_the_seeded_capabilities_do_not_contradict_the_profiles(db_session) -> None:
    rows = (
        await db_session.execute(
            sa.text("SELECT model_id, capabilities FROM model_profiles WHERE model_id = ANY(:ids)"),
            {"ids": list(SIX)},
        )
    ).all()
    assert {r[0] for r in rows} == set(SIX), "las migraciones no siembran los seis"
    for model_id, capabilities in rows:
        profile = profile_for(model_id)
        assert profile is not None
        control = (capabilities or {}).get("reasoning_control")
        if control == "none":
            assert not profile.keeps_reasoning, f"{model_id}: la base dice que no razona"
        managed = (capabilities or {}).get("context_management")
        if managed is True:
            assert profile.family == "anthropic", f"{model_id}: context_management fuera de Claude"
