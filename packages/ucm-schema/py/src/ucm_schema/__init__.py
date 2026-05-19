"""Public API of `nexus-ucm-schema`.

Cheat sheet:
    from ucm_schema import UCMMessage, UCM_VERSION
    from ucm_schema import validate
    from ucm_schema import degrade
    from ucm_schema import CHANNELS, get_channel
"""

from .types import (
    UCM_VERSION,
    UCM_TYPES,
    CapabilityKey,
    MediaKind,
    UCMType,
    TextUCM,
    QuickRepliesUCM,
    ListUCM,
    CtaUrlUCM,
    MediaUCM,
    LocationUCM,
    FlowUCM,
    CompositeUCM,
    UCMMessage,
    parse_ucm,
)
from .channels.capabilities import (
    CHANNELS,
    WEB,
    WHATSAPP,
    INSTAGRAM,
    MESSENGER,
    VOICE,
    ChannelLimits,
    ChannelName,
    ChannelProfile,
    channel_supports,
    get_channel,
    infer_capabilities,
)
from .validators import (
    ValidationIssue,
    ValidationResult,
    validate,
)
from .degrade import (
    DegradationStep,
    DegradeResult,
    degrade,
)
from .json_schema import (
    UCM_JSON_SCHEMA,
    SUPPORTED_UCM_VERSIONS,
    is_supported_ucm_version,
)

__all__ = [
    "UCM_VERSION",
    "UCM_TYPES",
    "CapabilityKey",
    "MediaKind",
    "UCMType",
    "TextUCM",
    "QuickRepliesUCM",
    "ListUCM",
    "CtaUrlUCM",
    "MediaUCM",
    "LocationUCM",
    "FlowUCM",
    "CompositeUCM",
    "UCMMessage",
    "parse_ucm",
    "CHANNELS",
    "WEB",
    "WHATSAPP",
    "INSTAGRAM",
    "MESSENGER",
    "VOICE",
    "ChannelLimits",
    "ChannelName",
    "ChannelProfile",
    "channel_supports",
    "get_channel",
    "infer_capabilities",
    "ValidationIssue",
    "ValidationResult",
    "validate",
    "DegradationStep",
    "DegradeResult",
    "degrade",
    "UCM_JSON_SCHEMA",
    "SUPPORTED_UCM_VERSIONS",
    "is_supported_ucm_version",
]
