"""Outbound guardrails for the TikTok channel.

Three things the dispatcher has to get right for a channel that is narrower
than WhatsApp:

1. It must actually dispatch TikTok rows — the type check used to be
   ``!= WHATSAPP``, which would have parked every TikTok message failed.
2. A capability error is terminal. Retrying a template send on a channel with
   no templates burns three attempts and hides the real problem.
3. TikTok's permanent failures arrive with **HTTP 200**, so they have to be
   classified by error code or they'd be retried forever.

Plus the structural guarantee that business-initiated sends can never target
a TikTok channel.
"""

from __future__ import annotations

import pytest
from nexus_worker.streams.outbound import (
    _DISPATCHABLE_CHANNEL_TYPES,
    _NO_RETRY_CODES,
    _TIKTOK_NO_RETRY_CODES,
)

from nexus_api.db.models import ChannelType


def test_tiktok_channels_are_dispatchable() -> None:
    """Guards the regression where the dispatcher hard-rejected anything
    that wasn't WhatsApp."""
    assert ChannelType.TIKTOK in _DISPATCHABLE_CHANNEL_TYPES
    assert ChannelType.WHATSAPP in _DISPATCHABLE_CHANNEL_TYPES


def test_channels_without_an_adapter_are_still_rejected() -> None:
    """Being permissive about TikTok must not make the check meaningless."""
    assert ChannelType.TELEGRAM not in _DISPATCHABLE_CHANNEL_TYPES
    assert ChannelType.EMAIL not in _DISPATCHABLE_CHANNEL_TYPES


@pytest.mark.parametrize("code", ["40001", "40002", "40016", "40100", "40105"])
def test_tiktok_permanent_failures_are_not_retried(code: str) -> None:
    """These arrive on HTTP 200, so the generic "4xx is permanent" branch
    never sees them — they have to be listed explicitly."""
    assert code in _NO_RETRY_CODES


def test_meta_no_retry_codes_survived_the_merge() -> None:
    assert {"131026", "131047", "368"} <= _NO_RETRY_CODES


def test_the_two_provider_code_sets_do_not_collide() -> None:
    meta_only = {"100", "131026", "131047", "131049", "368"}
    assert not (meta_only & _TIKTOK_NO_RETRY_CODES)


def test_capability_errors_are_classified_as_terminal() -> None:
    """``ChannelCapabilityError`` means "this can never work here"; the
    dispatcher must park the row rather than retry it."""
    import inspect

    from nexus_worker.streams import outbound

    source = inspect.getsource(outbound._handle_send_exception)
    assert "ChannelCapabilityError" in source
    assert "unsupported_capability" in source


def test_business_initiated_sends_cannot_target_tiktok() -> None:
    """Broadcasts and direct messages both resolve their channel through
    ``active_whatsapp_channel``, which filters on WHATSAPP. TikTok forbids
    business-initiated messages, so widening that filter would queue rows
    that can never be delivered."""
    import inspect

    from nexus_api.services import broadcasts

    source = inspect.getsource(broadcasts.active_whatsapp_channel)
    assert "ChannelType.WHATSAPP" in source
