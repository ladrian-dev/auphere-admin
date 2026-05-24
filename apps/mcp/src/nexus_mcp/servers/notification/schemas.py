from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field, model_validator

from nexus_mcp.base import InputModel, OutputModel


class SendTemplateInput(InputModel):
    conversation_id: uuid.UUID
    template_name: str = Field(
        min_length=1,
        max_length=120,
        description="Meta-approved WhatsApp template name (e.g. 'reminder_24h').",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Template parameter map.",
    )
    # Block N: optional language override for templates approved in
    # multiple locales. Defaults to es (Auphere is LATAM).
    language: str = Field(default="es", min_length=2, max_length=10)


class SendTemplateOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendTextInput(InputModel):
    conversation_id: uuid.UUID
    body: str = Field(min_length=1, max_length=4096)
    # Block N: optional wamid to quote. When set the recipient sees this
    # text as a reply attached to the cited message bubble. Useful for
    # booking confirmations that quote the original question.
    context_message_id: str | None = Field(default=None, max_length=160)


class SendTextOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class ScheduleReminderInput(InputModel):
    conversation_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    run_at: datetime = Field(
        description="When to fire the reminder. Tenant-TZ aware on the caller side; stored as UTC.",
    )
    template_name: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ScheduleReminderOutput(OutputModel):
    reminder_id: uuid.UUID
    run_at: datetime
    status: str


class CancelScheduledInput(InputModel):
    reminder_id: uuid.UUID


class CancelScheduledOutput(OutputModel):
    reminder_id: uuid.UUID
    status: str


# ── Block N: media + reaction + location schemas ────────────────────────────


class SendImageInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "S3 key (within the platform's media bucket) of an image previously "
            "uploaded via the operator's catalog or generated from a tool output. "
            "The outbound dispatcher resolves this to a presigned URL the Cloud "
            "API can fetch."
        ),
    )
    caption: str | None = Field(default=None, max_length=1024)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendImageOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendAudioInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(min_length=1, max_length=500)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendAudioOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendVideoInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(min_length=1, max_length=500)
    caption: str | None = Field(default=None, max_length=1024)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendVideoOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendDocumentInput(InputModel):
    conversation_id: uuid.UUID
    media_s3_key: str = Field(min_length=1, max_length=500)
    filename: str | None = Field(default=None, max_length=255)
    caption: str | None = Field(default=None, max_length=1024)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendDocumentOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendLocationInput(InputModel):
    conversation_id: uuid.UUID
    latitude: float
    longitude: float
    name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    context_message_id: str | None = Field(default=None, max_length=160)


class SendLocationOutput(OutputModel):
    message_id: uuid.UUID
    status: str


class SendReactionInput(InputModel):
    conversation_id: uuid.UUID
    target_message_id: str = Field(
        min_length=1,
        max_length=160,
        description="wamid of the message to react to. Required.",
    )
    emoji: str = Field(
        default="",
        max_length=20,
        description="Single emoji. Empty string removes a previous reaction.",
    )


class SendReactionOutput(OutputModel):
    message_id: uuid.UUID
    status: str


# ── response.send_interactive — native WhatsApp interactive components ──
#
# Shape mirrors the UCM v1.0.0 schemas (``ucm_schema.types``) so the
# ucm_formatter can wrap the validated payload without re-validating
# field-by-field. Limits match Meta Cloud API's documented maxima — the
# tool refuses payloads Cloud API would reject (e.g. >3 buttons, >10
# list rows total) instead of letting the dispatcher fail at send time.


class InteractiveButton(BaseModel):
    """One reply button. Up to 3 per ``send_interactive`` call."""

    id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=20)


class InteractiveListRow(BaseModel):
    """One selectable row inside a list. WhatsApp shows ``title`` as the
    primary line and ``description`` (optional) as a second muted line.
    """

    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=24)
    description: str | None = Field(default=None, max_length=72)


class InteractiveList(BaseModel):
    """Flat list payload — the agent passes ``items`` and we wrap them
    in a single section at serialisation time. Multi-section lists are
    a niche WhatsApp feature; if a tenant needs them later, we extend
    this model with an optional ``sections`` field. Keeping the LLM
    surface flat reduces the chance of malformed calls.
    """

    button: str = Field(
        min_length=1,
        max_length=20,
        description="Label of the button that opens the list (≤20 chars).",
    )
    items: list[InteractiveListRow] = Field(min_length=1, max_length=10)


class InteractiveCtaUrl(BaseModel):
    """A single 'call to action URL' button that opens the URL in the
    customer's browser. WhatsApp renders the button below the body.
    """

    text: str = Field(min_length=1, max_length=20)
    url: AnyHttpUrl


class SendInteractiveInput(InputModel):
    """Emit a native WhatsApp interactive component.

    The agent calls this INSTEAD of returning plain text when the
    response is best served by buttons / list / CTA URL. Exactly one of
    ``buttons``, ``list``, or ``cta_url`` must be set. The runtime
    captures the validated payload, breaks the ReAct loop, and either
    queues it as a single interactive message (when no preceding text)
    or as the second of two outbound rows (text first, then
    interactive) when the same turn also produced a text answer.

    See the ``whatsapp-native-components`` skill for the decision tree
    of which component to use when.
    """

    conversation_id: uuid.UUID
    body: str = Field(
        min_length=1,
        max_length=1024,
        description=(
            "Main text shown above / inside the component (e.g. the "
            "question). ≤1024 chars per Meta Cloud API."
        ),
    )
    footer: str | None = Field(
        default=None,
        max_length=60,
        description="Optional faint text below the component (≤60).",
    )
    header: str | None = Field(
        default=None,
        max_length=60,
        description="Optional bold header above the body (≤60).",
    )
    buttons: list[InteractiveButton] | None = Field(
        default=None,
        description="1–3 reply buttons. Use for ≤3 closed-choice questions.",
    )
    # The JSON-facing name is ``list`` (matches the SKILL.md guidance
    # the LLM sees) but the Python attribute is ``list_block`` because
    # ``list`` collides with the Python builtin inside this class body
    # — Pydantic's forward-ref evaluator would resolve ``list[...]`` in
    # the ``buttons`` annotation against the field's ``FieldInfo``
    # instead of the builtin. The alias keeps the LLM contract clean
    # without renaming the JSON key.
    list_block: InteractiveList | None = Field(
        default=None,
        alias="list",
        description="A 1–10 item selectable list. Use for 4–10 options.",
    )
    cta_url: InteractiveCtaUrl | None = Field(
        default=None,
        description="A single URL-opening button. Use for checkout / external link.",
    )
    context_message_id: str | None = Field(
        default=None,
        max_length=160,
        description="Optional wamid to quote as a reply.",
    )

    model_config = {
        # Accept both the JSON alias (``list``) and the Python name
        # (``list_block``) on input so tests can construct the model
        # either way. Output still defaults to the Python name; the
        # pipeline captures ``call.arguments`` which carries the JSON
        # alias the LLM emitted.
        "populate_by_name": True,
    }

    @model_validator(mode="after")
    def _exactly_one_component(self) -> "SendInteractiveInput":
        set_components: list[str] = []
        if self.buttons is not None:
            set_components.append("buttons")
        if self.list_block is not None:
            set_components.append("list")
        if self.cta_url is not None:
            set_components.append("cta_url")
        if len(set_components) != 1:
            raise ValueError(
                "send_interactive requires EXACTLY ONE of buttons / list "
                f"/ cta_url; got: {set_components or 'none'}"
            )
        # Buttons-specific length checks — Pydantic Field min/max_length
        # on Optional[list[...]] trips a forward-ref bug in this scope,
        # so enforce here instead.
        if self.buttons is not None and not (1 <= len(self.buttons) <= 3):
            raise ValueError(
                "buttons must have between 1 and 3 entries; "
                f"got {len(self.buttons)}"
            )
        return self


class SendInteractiveOutput(OutputModel):
    message_id: uuid.UUID
    status: str
