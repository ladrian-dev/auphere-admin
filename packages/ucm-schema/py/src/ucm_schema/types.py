"""UCM (Universal Channel Message) v1.0.0 — Python mirror of the TS schema.

Every fixture under `packages/ucm-schema/fixtures/valid.json` must parse cleanly
through `parse_ucm` here AND through the Zod schema in `ts/src/types.ts`.
That cross-language contract is enforced by the test suite.

Reference: ADR-020.
"""

from __future__ import annotations

from typing import Annotated, Any, Final, Literal, Union

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
)

UCM_VERSION: Final[Literal["1.0.0"]] = "1.0.0"

CapabilityKey = Literal[
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
]

MediaKind = Literal["image", "video", "document", "audio"]

UCMType = Literal[
    "text",
    "quick_replies",
    "list",
    "cta_url",
    "media",
    "location",
    "flow",
    "composite",
]


# ---------- content schemas ----------


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)


class TextContent(_StrictModel):
    body: str = Field(min_length=1, max_length=1024)
    format: Literal["plain", "markdown"] = "plain"


class QuickReplyButton(_StrictModel):
    id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=20)


class QuickRepliesContent(_StrictModel):
    body: str = Field(min_length=1, max_length=1024)
    buttons: list[QuickReplyButton] = Field(min_length=1, max_length=10)


class ListRow(_StrictModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=24)
    description: str | None = Field(default=None, max_length=72)


class ListSection(_StrictModel):
    title: str = Field(min_length=1, max_length=24)
    rows: list[ListRow] = Field(min_length=1, max_length=10)


class ListContent(_StrictModel):
    body: str = Field(min_length=1, max_length=1024)
    header: str | None = Field(default=None, max_length=60)
    footer: str | None = Field(default=None, max_length=60)
    button_text: str = Field(min_length=1, max_length=20)
    sections: list[ListSection] = Field(min_length=1, max_length=10)


class CtaUrlContent(_StrictModel):
    body: str = Field(min_length=1, max_length=1024)
    button_title: str = Field(min_length=1, max_length=20)
    url: AnyHttpUrl


class MediaContent(_StrictModel):
    kind: MediaKind
    url: AnyHttpUrl
    caption: str | None = Field(default=None, max_length=1024)
    filename: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=127)


class LocationContent(_StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=255)


class FlowContent(_StrictModel):
    flow_id: str = Field(min_length=1, max_length=255)
    body: str | None = Field(default=None, max_length=1024)
    header_text: str | None = Field(default=None, max_length=60)
    footer_text: str | None = Field(default=None, max_length=60)
    button_text: str = Field(min_length=1, max_length=20)
    screen: str | None = Field(default=None, max_length=60)
    data: dict[str, Any] | None = None


# ---------- UCM message variants ----------


class _BaseUCM(_StrictModel):
    ucm_version: Literal["1.0.0"]
    message_id: str = Field(min_length=1, max_length=128)
    capabilities_required: list[CapabilityKey] = Field(default_factory=list)
    fallback_text: str = Field(min_length=1, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ucm_version")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if v != UCM_VERSION:
            raise ValueError(f"unsupported ucm_version {v!r}; expected {UCM_VERSION!r}")
        return v


class TextUCM(_BaseUCM):
    type: Literal["text"]
    content: TextContent


class QuickRepliesUCM(_BaseUCM):
    type: Literal["quick_replies"]
    content: QuickRepliesContent


class ListUCM(_BaseUCM):
    type: Literal["list"]
    content: ListContent


class CtaUrlUCM(_BaseUCM):
    type: Literal["cta_url"]
    content: CtaUrlContent


class MediaUCM(_BaseUCM):
    type: Literal["media"]
    content: MediaContent


class LocationUCM(_BaseUCM):
    type: Literal["location"]
    content: LocationContent


class FlowUCM(_BaseUCM):
    type: Literal["flow"]
    content: FlowContent


class _CompositeContent(_StrictModel):
    # Recursive ref via forward declaration; rebuilt at the bottom of the module.
    children: list["UCMMessage"] = Field(min_length=1, max_length=20)  # type: ignore[name-defined]


class CompositeUCM(_BaseUCM):
    type: Literal["composite"]
    content: _CompositeContent


UCMMessage = Annotated[
    Union[
        TextUCM,
        QuickRepliesUCM,
        ListUCM,
        CtaUrlUCM,
        MediaUCM,
        LocationUCM,
        FlowUCM,
        CompositeUCM,
    ],
    Field(discriminator="type"),
]


_CompositeContent.model_rebuild(_types_namespace={"UCMMessage": UCMMessage})
CompositeUCM.model_rebuild(_types_namespace={"UCMMessage": UCMMessage})


UCM_TYPES: Final[tuple[UCMType, ...]] = (
    "text",
    "quick_replies",
    "list",
    "cta_url",
    "media",
    "location",
    "flow",
    "composite",
)


_UCMAdapter: TypeAdapter[UCMMessage] = TypeAdapter(UCMMessage)


def parse_ucm(raw: Any) -> UCMMessage:
    """Parse `raw` (dict / JSON-decoded) into a UCMMessage, raising on shape errors."""
    return _UCMAdapter.validate_python(raw)
