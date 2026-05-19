"""Per-channel capability + structural-limits matrix.

Adding a new channel = entry here + a renderer somewhere else + (optionally)
a stricter validator. Nothing else in `ucm_schema` needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from ..types import CapabilityKey

ChannelName = Literal["web", "whatsapp", "instagram", "messenger", "voice"]


@dataclass(frozen=True)
class ChannelLimits:
    quick_replies_max_buttons: int | None = None
    quick_replies_title_max_chars: int | None = None
    list_max_rows_total: int | None = None
    list_row_title_max_chars: int | None = None
    list_row_description_max_chars: int | None = None
    list_button_text_max_chars: int | None = None
    cta_url_button_title_max_chars: int | None = None
    text_body_max_chars: int | None = None
    composite_max_depth: int | None = None


@dataclass(frozen=True)
class ChannelProfile:
    name: ChannelName
    capabilities: frozenset[CapabilityKey]
    limits: ChannelLimits = field(default_factory=ChannelLimits)


WEB: Final[ChannelProfile] = ChannelProfile(
    name="web",
    capabilities=frozenset(
        {
            "text",
            "text.markdown",
            "interactive.buttons",
            "interactive.list",
            "interactive.cta_url",
            "media.image",
            "media.video",
            "media.document",
            "media.audio",
            "location",
            "flow",
        }
    ),
    limits=ChannelLimits(text_body_max_chars=4096, composite_max_depth=3),
)

WHATSAPP: Final[ChannelProfile] = ChannelProfile(
    name="whatsapp",
    capabilities=frozenset(
        {
            "text",
            "interactive.buttons",
            "interactive.list",
            "interactive.cta_url",
            "media.image",
            "media.video",
            "media.document",
            "media.audio",
            "location",
            "flow",
        }
    ),
    limits=ChannelLimits(
        quick_replies_max_buttons=3,
        quick_replies_title_max_chars=20,
        list_max_rows_total=10,
        list_row_title_max_chars=24,
        list_row_description_max_chars=72,
        list_button_text_max_chars=20,
        cta_url_button_title_max_chars=20,
        text_body_max_chars=1024,
        composite_max_depth=1,
    ),
)

INSTAGRAM: Final[ChannelProfile] = ChannelProfile(
    name="instagram",
    capabilities=frozenset(
        {"text", "interactive.buttons", "media.image", "media.video"}
    ),
    limits=ChannelLimits(
        quick_replies_max_buttons=13,
        quick_replies_title_max_chars=20,
        text_body_max_chars=1000,
        composite_max_depth=1,
    ),
)

MESSENGER: Final[ChannelProfile] = ChannelProfile(
    name="messenger",
    capabilities=frozenset(
        {
            "text",
            "interactive.buttons",
            "interactive.cta_url",
            "media.image",
            "media.video",
            "media.audio",
            "media.document",
        }
    ),
    limits=ChannelLimits(
        quick_replies_max_buttons=13,
        quick_replies_title_max_chars=20,
        cta_url_button_title_max_chars=20,
        text_body_max_chars=2000,
        composite_max_depth=1,
    ),
)

VOICE: Final[ChannelProfile] = ChannelProfile(
    name="voice",
    capabilities=frozenset({"text"}),
    limits=ChannelLimits(text_body_max_chars=600, composite_max_depth=1),
)

CHANNELS: Final[dict[ChannelName, ChannelProfile]] = {
    "web": WEB,
    "whatsapp": WHATSAPP,
    "instagram": INSTAGRAM,
    "messenger": MESSENGER,
    "voice": VOICE,
}


def get_channel(name: ChannelName) -> ChannelProfile:
    try:
        return CHANNELS[name]
    except KeyError as exc:
        raise ValueError(f"unknown channel: {name!r}") from exc


def channel_supports(channel: ChannelProfile, capability: CapabilityKey) -> bool:
    return capability in channel.capabilities


def infer_capabilities(type_: str, content: dict) -> list[CapabilityKey]:
    """Compute the capability keys a UCM payload requires, independent of channel."""
    if type_ == "text":
        fmt = content.get("format", "plain")
        return ["text", "text.markdown"] if fmt == "markdown" else ["text"]
    if type_ == "quick_replies":
        return ["interactive.buttons"]
    if type_ == "list":
        return ["interactive.list"]
    if type_ == "cta_url":
        return ["interactive.cta_url"]
    if type_ == "media":
        kind = content.get("kind", "image")
        return [f"media.{kind}"]  # type: ignore[list-item]
    if type_ == "location":
        return ["location"]
    if type_ == "flow":
        return ["flow"]
    if type_ == "composite":
        return []
    return []
