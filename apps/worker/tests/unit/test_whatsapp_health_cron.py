"""Spec 050 (4.2, 8.4): the health cron clears only the problems it set.

``apply_phone_snapshot`` is the cron's decision on one number, given what
``GET /{phone_number_id}`` answered. A problem an account event set
(``problem_source = "account"``) outlives a GREEN reading; one the cron set
for quality (``"quality"``) does not.
"""

from __future__ import annotations

from nexus_api.db.models import Channel, ChannelStatus, ChannelType

from nexus_worker.streams.whatsapp_health_cron import apply_phone_snapshot


def _channel(**kw: object) -> Channel:
    return Channel(
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier="+34600000001",
        status=kw.pop("status", ChannelStatus.ACTIVE),
        problem_reason=kw.pop("problem_reason", None),
        config={"phone_number_id": "PN", "waba_id": "W", **kw},
    )


def test_an_account_problem_survives_a_green_reading() -> None:
    ch = _channel(
        status=ChannelStatus.DEGRADED, problem_reason="auth_expired", problem_source="account"
    )
    apply_phone_snapshot(ch, {"quality_rating": "GREEN"})
    assert (ch.status, ch.problem_reason) == (ChannelStatus.DEGRADED, "auth_expired")
    assert ch.config["problem_source"] == "account"


def test_a_quality_problem_is_cleared_by_green() -> None:
    ch = _channel()
    apply_phone_snapshot(ch, {"quality_rating": "RED"})
    assert (ch.status, ch.problem_reason) == (ChannelStatus.DEGRADED, "quality")
    assert ch.config["problem_source"] == "quality"
    apply_phone_snapshot(ch, {"quality_rating": "GREEN"})
    assert (ch.status, ch.problem_reason) == (ChannelStatus.ACTIVE, None)
    assert "problem_source" not in ch.config


def test_a_low_quality_reading_does_not_hide_an_account_problem() -> None:
    ch = _channel(
        status=ChannelStatus.DEGRADED, problem_reason="account_alert", problem_source="account"
    )
    apply_phone_snapshot(ch, {"quality_rating": "YELLOW"})
    assert (ch.problem_reason, ch.config["problem_source"]) == ("account_alert", "account")
    assert ch.config["quality_rating"] == "YELLOW"


def test_a_legacy_degraded_row_without_source_is_still_cleared() -> None:
    # Before spec 050 the cron degraded without a reason or a source.
    ch = _channel(status=ChannelStatus.DEGRADED)
    apply_phone_snapshot(ch, {"quality_rating": "GREEN"})
    assert ch.status is ChannelStatus.ACTIVE


def test_it_reads_the_messaging_limit_and_the_name_status() -> None:
    ch = _channel()
    apply_phone_snapshot(
        ch,
        {
            "quality_rating": "GREEN",
            "whatsapp_business_manager_messaging_limit": "TIER_10K",
            "name_status": "APPROVED",
            "verified_name": "Barbería Cultor",
        },
    )
    assert ch.config["messaging_limit"] == "TIER_10K"
    assert ch.config["name_status"] == "APPROVED"
    assert ch.config["verified_name"] == "Barbería Cultor"


def test_the_limit_may_come_as_an_object() -> None:
    ch = _channel()
    apply_phone_snapshot(
        ch, {"whatsapp_business_manager_messaging_limit": {"current_limit": "TIER_2K"}}
    )
    assert ch.config["messaging_limit"] == "TIER_2K"
