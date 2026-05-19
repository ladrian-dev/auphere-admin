"""Channel-pluggable UCM validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from ..channels.capabilities import (
    ChannelName,
    ChannelProfile,
    channel_supports,
    get_channel,
    infer_capabilities,
)
from ..types import UCMMessage, parse_ucm

IssueKind = Literal["capability", "limit", "shape"]


@dataclass(frozen=True)
class ValidationIssue:
    kind: IssueKind
    path: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    ucm: UCMMessage | None = None
    issues: list[ValidationIssue] = field(default_factory=list)


def validate(raw: Any, channel_name: ChannelName) -> ValidationResult:
    """Validate `raw` against UCM v1.0.0 AND the channel's structural limits."""
    try:
        ucm = parse_ucm(raw)
    except ValidationError as e:
        return ValidationResult(
            ok=False,
            issues=[
                ValidationIssue(
                    kind="shape",
                    path=".".join(str(p) for p in err.get("loc", ())) or "<root>",
                    message=err.get("msg", "invalid"),
                )
                for err in e.errors()
            ],
        )

    channel = get_channel(channel_name)
    issues: list[ValidationIssue] = []
    _walk(ucm, channel, "<root>", issues)
    return ValidationResult(
        ok=not issues,
        ucm=ucm if not issues else None,
        issues=issues,
    )


def _walk(
    ucm: UCMMessage,
    channel: ChannelProfile,
    path: str,
    out: list[ValidationIssue],
) -> None:
    content_dict = (
        ucm.content.model_dump() if hasattr(ucm.content, "model_dump") else {}
    )
    needed = infer_capabilities(ucm.type, content_dict)
    for cap in needed:
        if not channel_supports(channel, cap):
            out.append(
                ValidationIssue(
                    kind="capability",
                    path=path,
                    message=(
                        f'channel "{channel.name}" does not support '
                        f'capability "{cap}" required by type "{ucm.type}"'
                    ),
                )
            )

    _check_limits(ucm, channel, path, out)

    if ucm.type == "composite":
        limit = channel.limits.composite_max_depth
        if limit is not None:
            depth = _composite_depth(ucm)
            if depth > limit:
                out.append(
                    ValidationIssue(
                        kind="limit",
                        path=path,
                        message=f"composite depth {depth} exceeds channel limit {limit}",
                    )
                )
        for idx, child in enumerate(ucm.content.children):
            _walk(child, channel, f"{path}.children[{idx}]", out)


def _check_limits(
    ucm: UCMMessage,
    channel: ChannelProfile,
    path: str,
    out: list[ValidationIssue],
) -> None:
    L = channel.limits

    def issue(msg: str) -> None:
        out.append(ValidationIssue(kind="limit", path=path, message=msg))

    if ucm.type == "text":
        if L.text_body_max_chars is not None and len(ucm.content.body) > L.text_body_max_chars:
            issue(
                f"text body {len(ucm.content.body)} chars exceeds {L.text_body_max_chars}"
            )
        return

    if ucm.type == "quick_replies":
        c = ucm.content
        if L.text_body_max_chars is not None and len(c.body) > L.text_body_max_chars:
            issue(f"quick_replies body exceeds {L.text_body_max_chars} chars")
        if (
            L.quick_replies_max_buttons is not None
            and len(c.buttons) > L.quick_replies_max_buttons
        ):
            issue(
                f"quick_replies has {len(c.buttons)} buttons, "
                f"channel max {L.quick_replies_max_buttons}"
            )
        if L.quick_replies_title_max_chars is not None:
            for i, b in enumerate(c.buttons):
                if len(b.title) > L.quick_replies_title_max_chars:
                    issue(
                        f"quick_replies.buttons[{i}].title length "
                        f"{len(b.title)} > {L.quick_replies_title_max_chars}"
                    )
        return

    if ucm.type == "list":
        c = ucm.content
        if L.text_body_max_chars is not None and len(c.body) > L.text_body_max_chars:
            issue(f"list body exceeds {L.text_body_max_chars} chars")
        if (
            L.list_button_text_max_chars is not None
            and len(c.button_text) > L.list_button_text_max_chars
        ):
            issue(
                f"list.button_text exceeds {L.list_button_text_max_chars} chars"
            )
        total_rows = sum(len(s.rows) for s in c.sections)
        if L.list_max_rows_total is not None and total_rows > L.list_max_rows_total:
            issue(
                f"list has {total_rows} rows total, channel max {L.list_max_rows_total}"
            )
        for si, s in enumerate(c.sections):
            for ri, r in enumerate(s.rows):
                if (
                    L.list_row_title_max_chars is not None
                    and len(r.title) > L.list_row_title_max_chars
                ):
                    issue(
                        f"list.sections[{si}].rows[{ri}].title exceeds "
                        f"{L.list_row_title_max_chars} chars"
                    )
                if (
                    L.list_row_description_max_chars is not None
                    and r.description is not None
                    and len(r.description) > L.list_row_description_max_chars
                ):
                    issue(
                        f"list.sections[{si}].rows[{ri}].description exceeds "
                        f"{L.list_row_description_max_chars} chars"
                    )
        return

    if ucm.type == "cta_url":
        c = ucm.content
        if L.text_body_max_chars is not None and len(c.body) > L.text_body_max_chars:
            issue(f"cta_url body exceeds {L.text_body_max_chars} chars")
        if (
            L.cta_url_button_title_max_chars is not None
            and len(c.button_title) > L.cta_url_button_title_max_chars
        ):
            issue(
                f"cta_url.button_title exceeds "
                f"{L.cta_url_button_title_max_chars} chars"
            )
        return

    if ucm.type == "media":
        if (
            L.text_body_max_chars is not None
            and ucm.content.caption is not None
            and len(ucm.content.caption) > L.text_body_max_chars
        ):
            issue(f"media caption exceeds {L.text_body_max_chars} chars")
        return


def _composite_depth(ucm: UCMMessage) -> int:
    if ucm.type != "composite":
        return 0
    m = 0
    for child in ucm.content.children:
        m = max(m, _composite_depth(child))
    return 1 + m
