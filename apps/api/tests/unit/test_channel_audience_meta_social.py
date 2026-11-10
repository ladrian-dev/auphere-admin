"""QA 2026-10-30 (INC-08): the channel page's audience also rules Instagram
and Messenger.

Before, ``strict`` was WhatsApp only, so an Instagram or Messenger channel
showed «Sin configurar» or «A todos» while the agent kept answering by the
version's ``admin_access``. «Solo mi equipo» is phone numbers, which never
match an IGSID or a PSID, so it is refused there.
"""

from __future__ import annotations

import pytest

from nexus_api.core.admin_gate import audience_suppresses
from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.services.channel_config import (
    ChannelConfigError,
    ConfigIn,
    _audience_applies,
    validate,
)

pytestmark = pytest.mark.asyncio


def _channel(kind: ChannelType) -> Channel:
    return Channel(
        type=kind,
        provider="meta_instagram" if kind is ChannelType.INSTAGRAM else "meta",
        provider_identifier="17841400000000555",
        status=ChannelStatus.ACTIVE,
        config={},
    )


def test_the_audience_applies_to_the_three_meta_channels() -> None:
    assert _audience_applies(_channel(ChannelType.WHATSAPP))
    assert _audience_applies(_channel(ChannelType.INSTAGRAM))
    assert _audience_applies(_channel(ChannelType.MESSENGER))


def test_a_strict_instagram_channel_answers_everyone_and_nobody_while_unset() -> None:
    igsid = "998877665544"
    unset = {"mode": "unset", "test": [], "exception": [], "strict": True}
    everyone = {"mode": "everyone", "test": [], "exception": [], "strict": True}
    admin_only = {"admin_access": {"mode": "admins_only", "admins": ["+34600000001"]}}
    assert audience_suppresses(unset, admin_only, igsid) is True
    assert audience_suppresses(everyone, admin_only, igsid) is False


async def test_only_my_team_is_refused_off_whatsapp() -> None:
    with pytest.raises(ChannelConfigError) as info:
        await validate(
            None,  # type: ignore[arg-type]  # refused before any query
            _channel(ChannelType.INSTAGRAM),
            ConfigIn(mode="team_only", test_numbers=["+34600000001"]),
        )
    assert info.value.code == "team_only_needs_whatsapp"
    assert info.value.status == 422
