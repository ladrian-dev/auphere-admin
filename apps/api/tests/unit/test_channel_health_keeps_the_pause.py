"""QA 2026-10-30 (INC-06): a problem never undoes a partner's pause.

The health crons, the account events and the outbound dispatcher used to
write ``status`` straight away, so a paused number became DEGRADED and then
ACTIVE and the agent answered again. ``set_health`` changes what resuming
returns instead.
"""

from __future__ import annotations

from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.services.channel_config import health_degraded, set_health
from nexus_api.services.whatsapp_account_events import _clear_problem, _set_problem


def _channel(status: ChannelStatus, **cfg: object) -> Channel:
    return Channel(
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier="+34600000001",
        status=status,
        config={"phone_number_id": "PN", **cfg},
    )


def test_set_health_moves_status_when_not_paused() -> None:
    ch = _channel(ChannelStatus.ACTIVE)
    set_health(ch, degraded=True)
    assert ch.status is ChannelStatus.DEGRADED and health_degraded(ch)
    set_health(ch, degraded=False)
    assert ch.status is ChannelStatus.ACTIVE and not health_degraded(ch)


def test_set_health_on_a_paused_number_changes_what_resuming_returns() -> None:
    ch = _channel(ChannelStatus.PAUSED, before_pause="active")
    set_health(ch, degraded=True)
    assert ch.status is ChannelStatus.PAUSED
    assert ch.config["before_pause"] == "degraded" and health_degraded(ch)


def test_an_account_problem_on_a_paused_number_keeps_the_pause() -> None:
    ch = _channel(ChannelStatus.PAUSED, before_pause="active")
    assert _set_problem(ch, "account_alert")
    assert ch.status is ChannelStatus.PAUSED
    assert ch.problem_reason == "account_alert"
    assert ch.config["before_pause"] == "degraded"
    assert ch.config["problem_source"] == "account"

    assert _clear_problem(ch, frozenset({"account_alert"}))
    assert ch.status is ChannelStatus.PAUSED
    assert ch.problem_reason is None
    assert ch.config["before_pause"] == "active"
    assert "problem_source" not in ch.config
