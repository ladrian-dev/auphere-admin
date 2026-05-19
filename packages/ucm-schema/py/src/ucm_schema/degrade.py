"""Channel-aware UCM degradation engine.

See `ts/src/degrade.ts` for the algorithm. The Python implementation is a
behavioural mirror; the cross-language test asserts equivalent outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .channels.capabilities import (
    ChannelName,
    ChannelProfile,
    channel_supports,
    get_channel,
    infer_capabilities,
)
from .types import (
    UCM_VERSION,
    CompositeUCM,
    ListContent,
    ListSection,
    ListRow,
    ListUCM,
    TextContent,
    TextUCM,
    UCMMessage,
)
from .validators import validate

Reason = Literal["capability", "limit", "depth"]


@dataclass(frozen=True)
class DegradationStep:
    reason: Reason
    from_type: str
    to_type: str
    detail: str


@dataclass(frozen=True)
class DegradeResult:
    ucm: UCMMessage
    changed: bool
    steps: list[DegradationStep] = field(default_factory=list)


def degrade(ucm: UCMMessage, channel_name: ChannelName) -> DegradeResult:
    channel = get_channel(channel_name)
    steps: list[DegradationStep] = []
    result = _degrade_inner(ucm, channel, steps)
    return DegradeResult(ucm=result, changed=bool(steps), steps=steps)


def _content_dict(ucm: UCMMessage) -> dict[str, Any]:
    return ucm.content.model_dump() if hasattr(ucm.content, "model_dump") else {}


def _degrade_inner(
    ucm: UCMMessage,
    channel: ChannelProfile,
    steps: list[DegradationStep],
) -> UCMMessage:
    caps = infer_capabilities(ucm.type, _content_dict(ucm))
    unsupported = [c for c in caps if not channel_supports(channel, c)]
    if unsupported:
        steps.append(
            DegradationStep(
                reason="capability",
                from_type=ucm.type,
                to_type="text",
                detail=f'channel "{channel.name}" lacks {", ".join(unsupported)}',
            )
        )
        return _to_text_fallback(ucm)

    if ucm.type == "composite":
        limit = channel.limits.composite_max_depth
        if limit is not None and _composite_depth(ucm) > limit:
            steps.append(
                DegradationStep(
                    reason="depth",
                    from_type="composite",
                    to_type="composite (flattened)",
                    detail=f"depth > {limit}",
                )
            )
            flat_children = _flatten_composite_children(ucm)
            children = [_degrade_inner(c, channel, steps) for c in flat_children]
            return CompositeUCM(
                ucm_version=ucm.ucm_version,
                message_id=ucm.message_id,
                type="composite",
                capabilities_required=ucm.capabilities_required,
                fallback_text=ucm.fallback_text,
                metadata=ucm.metadata,
                content={"children": children},
            )
        children = [_degrade_inner(c, channel, steps) for c in ucm.content.children]
        return CompositeUCM(
            ucm_version=ucm.ucm_version,
            message_id=ucm.message_id,
            type="composite",
            capabilities_required=ucm.capabilities_required,
            fallback_text=ucm.fallback_text,
            metadata=ucm.metadata,
            content={"children": children},
        )

    verdict = validate(ucm.model_dump(mode="json"), channel.name)
    if verdict.ok:
        return ucm

    only_limits = all(i.kind == "limit" for i in verdict.issues)
    if not only_limits:
        steps.append(
            DegradationStep(
                reason="capability",
                from_type=ucm.type,
                to_type="text",
                detail="; ".join(
                    f"{i.kind}@{i.path}: {i.message}" for i in verdict.issues
                ),
            )
        )
        return _to_text_fallback(ucm)

    if ucm.type == "quick_replies":
        return _degrade_quick_replies(ucm, channel, steps)
    if ucm.type == "list":
        return _degrade_list(ucm, channel, steps)
    if ucm.type == "cta_url":
        return _degrade_cta_url(ucm, channel, steps)
    if ucm.type in ("text", "media"):
        return _degrade_text_or_media(ucm, channel, steps)
    return ucm


def _degrade_quick_replies(
    ucm: UCMMessage,
    channel: ChannelProfile,
    steps: list[DegradationStep],
) -> UCMMessage:
    max_btns = channel.limits.quick_replies_max_buttons or 10**9
    title_max = channel.limits.quick_replies_title_max_chars or 10**9

    buttons = [
        {"id": b.id, "title": _truncate(b.title, title_max)}
        for b in ucm.content.buttons
    ]

    if len(buttons) > max_btns:
        if "interactive.list" in channel.capabilities:
            steps.append(
                DegradationStep(
                    reason="limit",
                    from_type="quick_replies",
                    to_type="list",
                    detail=f"{len(buttons)} buttons > {max_btns} — converted to list",
                )
            )
            row_title_max = channel.limits.list_row_title_max_chars or 24
            return ListUCM(
                ucm_version=UCM_VERSION,
                message_id=f"{ucm.message_id}::degraded",
                type="list",
                capabilities_required=["interactive.list"],
                fallback_text=ucm.fallback_text,
                metadata={**ucm.metadata, "degraded_from": "quick_replies"},
                content=ListContent(
                    body=ucm.content.body,
                    button_text=_truncate(
                        "Ver opciones", channel.limits.list_button_text_max_chars or 20
                    ),
                    sections=[
                        ListSection(
                            title=_truncate(
                                "Opciones", row_title_max
                            ),
                            rows=[
                                ListRow(
                                    id=b["id"],
                                    title=_truncate(b["title"], row_title_max),
                                )
                                for b in buttons[
                                    : channel.limits.list_max_rows_total
                                    or len(buttons)
                                ]
                            ],
                        )
                    ],
                ),
            )
        steps.append(
            DegradationStep(
                reason="limit",
                from_type="quick_replies",
                to_type="text",
                detail=(
                    f"{len(buttons)} buttons > {max_btns} — channel cannot list, "
                    "falling back to text"
                ),
            )
        )
        return _to_text_fallback(ucm)

    truncated = any(buttons[i]["title"] != ucm.content.buttons[i].title for i in range(len(buttons)))
    if truncated:
        steps.append(
            DegradationStep(
                reason="limit",
                from_type="quick_replies",
                to_type="quick_replies (truncated)",
                detail=f"button titles truncated to {title_max} chars",
            )
        )
        return ucm.model_copy(
            update={
                "content": ucm.content.model_copy(
                    update={
                        "buttons": [
                            ucm.content.buttons[i].model_copy(update={"title": buttons[i]["title"]})
                            for i in range(len(buttons))
                        ]
                    }
                )
            }
        )
    return ucm


def _degrade_list(
    ucm: UCMMessage,
    channel: ChannelProfile,
    steps: list[DegradationStep],
) -> UCMMessage:
    max_rows = channel.limits.list_max_rows_total or 10**9
    title_max = channel.limits.list_row_title_max_chars or 10**9
    desc_max = channel.limits.list_row_description_max_chars or 10**9
    btn_max = channel.limits.list_button_text_max_chars or 10**9

    new_sections: list[ListSection] = []
    count = 0
    for s in ucm.content.sections:
        new_rows: list[ListRow] = []
        for r in s.rows:
            if count >= max_rows:
                break
            new_rows.append(
                r.model_copy(
                    update={
                        "title": _truncate(r.title, title_max),
                        "description": (
                            _truncate(r.description, desc_max)
                            if r.description is not None
                            else None
                        ),
                    }
                )
            )
            count += 1
        if new_rows:
            new_sections.append(
                s.model_copy(update={"title": _truncate(s.title, title_max), "rows": new_rows})
            )

    total_rows_orig = sum(len(s.rows) for s in ucm.content.sections)
    if total_rows_orig > max_rows:
        steps.append(
            DegradationStep(
                reason="limit",
                from_type="list",
                to_type="list (truncated)",
                detail=f"{total_rows_orig} rows > {max_rows} — truncated",
            )
        )

    new_button = _truncate(ucm.content.button_text, btn_max)
    if new_button != ucm.content.button_text:
        steps.append(
            DegradationStep(
                reason="limit",
                from_type="list",
                to_type="list (truncated button_text)",
                detail=f"button_text truncated to {btn_max} chars",
            )
        )

    return ucm.model_copy(
        update={
            "content": ucm.content.model_copy(
                update={"button_text": new_button, "sections": new_sections}
            )
        }
    )


def _degrade_cta_url(
    ucm: UCMMessage,
    channel: ChannelProfile,
    steps: list[DegradationStep],
) -> UCMMessage:
    max_ = channel.limits.cta_url_button_title_max_chars or 10**9
    new_title = _truncate(ucm.content.button_title, max_)
    if new_title != ucm.content.button_title:
        steps.append(
            DegradationStep(
                reason="limit",
                from_type="cta_url",
                to_type="cta_url (truncated button_title)",
                detail=f"button_title truncated to {max_} chars",
            )
        )
    return ucm.model_copy(
        update={"content": ucm.content.model_copy(update={"button_title": new_title})}
    )


def _degrade_text_or_media(
    ucm: UCMMessage,
    channel: ChannelProfile,
    steps: list[DegradationStep],
) -> UCMMessage:
    max_ = channel.limits.text_body_max_chars or 10**9
    if ucm.type == "text":
        new_body = _truncate(ucm.content.body, max_)
        if new_body != ucm.content.body:
            steps.append(
                DegradationStep(
                    reason="limit",
                    from_type="text",
                    to_type="text (truncated)",
                    detail=f"body truncated to {max_} chars",
                )
            )
        return ucm.model_copy(
            update={"content": ucm.content.model_copy(update={"body": new_body})}
        )
    # media
    if ucm.content.caption is not None:
        new_caption = _truncate(ucm.content.caption, max_)
        if new_caption != ucm.content.caption:
            steps.append(
                DegradationStep(
                    reason="limit",
                    from_type="media",
                    to_type="media (truncated caption)",
                    detail=f"caption truncated to {max_} chars",
                )
            )
        return ucm.model_copy(
            update={"content": ucm.content.model_copy(update={"caption": new_caption})}
        )
    return ucm


def _to_text_fallback(ucm: UCMMessage) -> TextUCM:
    return TextUCM(
        ucm_version=UCM_VERSION,
        message_id=f"{ucm.message_id}::fallback",
        type="text",
        capabilities_required=["text"],
        fallback_text=ucm.fallback_text,
        metadata={**ucm.metadata, "degraded_from": ucm.type},
        content=TextContent(body=ucm.fallback_text, format="plain"),
    )


def _composite_depth(ucm: UCMMessage) -> int:
    if ucm.type != "composite":
        return 0
    m = 0
    for c in ucm.content.children:
        m = max(m, _composite_depth(c))
    return 1 + m


def _flatten_composite_children(ucm: UCMMessage) -> list[UCMMessage]:
    if ucm.type != "composite":
        raise ValueError("flatten on non-composite")
    out: list[UCMMessage] = []
    for child in ucm.content.children:
        if child.type == "composite":
            out.extend(_flatten_composite_children(child))
        else:
            out.append(child)
    return out


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return s[:max_len]
    return s[: max(1, max_len - 1)] + "…"
