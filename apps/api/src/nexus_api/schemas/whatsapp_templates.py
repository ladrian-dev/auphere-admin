"""The content of a WhatsApp template, as the editor sees it (spec 075).

One shape for creating and editing, in the console and in the operator
panel (075, 9.3): header text, body, footer, up to three buttons and one
example per body variable. ``to_components`` is the only place that turns
it into Meta's ``components`` array.

``TemplateCreateIn`` is the one shape to create, in both screens (075,
requisito 10, 2026-11-25): an AUTHENTICATION template carries ``otp_*``
instead of a body (077).

It lives here, not in ``api/console/schemas_channels``, because the edit
service needs it too, and importing anything under ``api.console`` runs
that package's ``__init__``, which imports the routers, which import the
service.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nexus_api.schemas.whatsapp_authentication import (
    DEFAULT_OTP_BUTTON_TEXT,
    authentication_components,
)

TemplateCategory = Literal["MARKETING", "UTILITY", "AUTHENTICATION"]

BODY_VAR_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
VAR_NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")


class TemplateButtonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["QUICK_REPLY", "URL", "PHONE_NUMBER"]
    label: str = Field(min_length=1, max_length=25)
    url: str | None = Field(default=None, max_length=2000)
    phone_number: str | None = Field(default=None, max_length=20)


class TemplateContentIn(BaseModel):
    """What the editor sends. ``category`` is optional so an edit can say
    "keep it"; creating gives it a default (``TemplateCreateIn``)."""

    model_config = ConfigDict(extra="forbid")

    category: TemplateCategory | None = None
    header_text: str | None = Field(default=None, max_length=60)
    body_text: str = Field(min_length=1, max_length=1024)
    footer_text: str | None = Field(default=None, max_length=60)
    buttons: list[TemplateButtonIn] = Field(default_factory=list, max_length=3)
    #: Example value per body variable (``{"nombre": "Camila"}`` or
    #: ``{"1": "Camila"}``). Meta needs one for every variable to review it.
    examples: dict[str, str] = Field(default_factory=dict, max_length=20)

    @field_validator("examples")
    @classmethod
    def _validate_examples(cls, v: dict[str, str]) -> dict[str, str]:
        for key, value in v.items():
            if not VAR_NAME_RE.match(key) or not value.strip() or len(value) > 200:
                raise ValueError(f"invalid example for {key!r}")
        return v

    def variables(self) -> list[str]:
        """Body variables in order of first appearance, without repeats."""
        out: list[str] = []
        for match in BODY_VAR_RE.finditer(self.body_text):
            name = match.group(1)
            if name not in out:
                out.append(name)
        return out

    def missing_examples(self) -> list[str]:
        return [n for n in self.variables() if not self.examples.get(n, "").strip()]

    def parameter_format(self) -> str | None:
        names = self.variables()
        if names and not all(n.isdigit() for n in names):
            return "NAMED"
        return None

    def to_components(self) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []
        if self.header_text:
            components.append({"type": "HEADER", "format": "TEXT", "text": self.header_text})
        body: dict[str, Any] = {"type": "BODY", "text": self.body_text}
        names = self.variables()
        if names and all(n in self.examples for n in names):
            if self.parameter_format() == "NAMED":
                body["example"] = {
                    "body_text_named_params": [
                        {"param_name": n, "example": self.examples[n]} for n in names
                    ]
                }
            else:
                ordered = sorted(names, key=int)
                body["example"] = {"body_text": [[self.examples[n] for n in ordered]]}
        components.append(body)
        if self.footer_text:
            components.append({"type": "FOOTER", "text": self.footer_text})
        if self.buttons:
            buttons: list[dict[str, Any]] = []
            for b in self.buttons:
                btn: dict[str, Any] = {"type": b.type, "text": b.label}
                if b.type == "URL" and b.url:
                    btn["url"] = b.url
                if b.type == "PHONE_NUMBER" and b.phone_number:
                    btn["phone_number"] = b.phone_number
                buttons.append(btn)
            components.append({"type": "BUTTONS", "buttons": buttons})
        return components


class TemplateCreateIn(TemplateContentIn):
    """What the editor sends to create, in the console and in the panel
    (075, 10.5): header/body/footer text + up to 3 buttons, or ``otp_*``
    for AUTHENTICATION. The server builds the Cloud API ``components``
    array (``to_components``, shared with editing since spec 075)."""

    name: str = Field(min_length=1, max_length=512)
    language: str = Field(default="es", min_length=2, max_length=15)
    category: TemplateCategory = "UTILITY"
    #: Required except for AUTHENTICATION, whose body Meta fixes (spec 077).
    body_text: str = Field(default="", max_length=1024)
    #: Spec 077: what an AUTHENTICATION template lets us choose.
    otp_button_text: str = Field(default=DEFAULT_OTP_BUTTON_TEXT, min_length=1, max_length=25)
    otp_expiration_minutes: int | None = Field(default=None, ge=1, le=90)
    otp_security_recommendation: bool = True

    @model_validator(mode="after")
    def _body_unless_authentication(self) -> TemplateCreateIn:
        if self.category != "AUTHENTICATION" and not self.body_text.strip():
            raise ValueError("body_text is required")
        return self

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not TEMPLATE_NAME_RE.match(v):
            raise ValueError(
                "name must be lowercase letters, digits and underscores (e.g. reminder_24h)"
            )
        return v

    def parameter_format(self) -> str | None:
        if self.category == "AUTHENTICATION":
            return None
        return super().parameter_format()

    def to_components(self) -> list[dict[str, Any]]:
        if self.category == "AUTHENTICATION":
            # Spec 077: Meta's shape, never free text (it rejects that).
            return authentication_components(
                button_text=self.otp_button_text,
                code_expiration_minutes=self.otp_expiration_minutes,
                add_security_recommendation=self.otp_security_recommendation,
            )
        return super().to_components()


class TemplateButtonOut(BaseModel):
    type: str
    label: str
    url: str | None = None
    phone_number: str | None = None


class TemplateContentOut(BaseModel):
    """A template's content split into the editor's parts (075, 9.3): the
    console and the panel open the editor with this, they never parse
    Meta's ``components`` themselves."""

    category: str | None = None
    header_text: str | None = None
    body_text: str
    footer_text: str | None = None
    buttons: list[TemplateButtonOut] = Field(default_factory=list)
    examples: dict[str, str] = Field(default_factory=dict)
