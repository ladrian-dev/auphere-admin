"""UCM formatter — converts the agent's final response into a Universal
Channel Message (UCM v1.0.0).

Inserted as a graph node between ``respond`` and ``checkpoint`` (see
``pipeline.py``). When ``NEXUS_USE_UCM_FORMATTER`` is enabled, the node:

1. Reads ``state["response"]`` (the assistant's reply, today always plain
   text), wraps it in a ``type:"text"`` UCM and stamps a stable message id.
2. Runs ``degrade(ucm, channel)`` for the channel the turn runs on
   (``state["channel_type"]``, default ``whatsapp``) so we can compare the
   channel-rendered form against the legacy text — shadow validation.
3. Writes both the UCM and the shadow-diff summary back into the state.

The node is a pure-Python helper plus a tiny LangGraph wrapper; the heavy
lifting (validation, degradation) lives in ``@nexus/ucm-schema``. This file
intentionally has no side-effects: persistence happens in the downstream
``checkpoint`` node, which can decide what to do with the UCM (e.g. attach
it as Langfuse trace metadata; in a later phase, also persist it).

See ADR-020 and ``Auphere/nexus/features/qa-playground-mvp.md`` (Phase 2).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from ucm_schema import (
    UCM_VERSION,
    UCMMessage,
    degrade,
    parse_ucm,
)

# Markdown the LLM tends to emit vs. WhatsApp's native micro-formatting.
# WhatsApp (and both UCM renderers) show the body verbatim, and WhatsApp bold
# is a SINGLE asterisk — so ``**bold**`` reaches the user as literal asterisks.
# The system prompt asks for WhatsApp syntax, but models slip into markdown;
# this normalises the output deterministically. Channel-safe: single-asterisk
# bold is what WhatsApp renders and what the web preview shows verbatim.
_MD_BOLD_STARS = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_MD_BOLD_UNDERSCORES = re.compile(r"__(?=\S)(.+?)(?<=\S)__", re.DOTALL)


def to_whatsapp_formatting(text: str) -> str:
    """Convert markdown bold (``**x**`` / ``__x__``) to WhatsApp bold (``*x*``)."""
    text = _MD_BOLD_STARS.sub(r"*\1*", text)
    return _MD_BOLD_UNDERSCORES.sub(r"*\1*", text)


def format_response_as_ucm(
    *,
    response_text: str,
    message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    interactive_payload: dict[str, Any] | None = None,
) -> UCMMessage:
    """Convert the agent's response into a UCM message.

    Three cases:

    1. ``interactive_payload`` is empty / unset → plain-text response.
       The UCM is a 1:1 ``text`` wrapper, identical to Phase 2 of
       ADR-020 (the formatter's original behaviour).

    2. ``interactive_payload`` is set and ``response_text`` is empty →
       the agent's reply IS the interactive component (no preceding
       prose). The formatter builds a single ``quick_replies`` /
       ``list`` / ``cta_url`` UCM and returns it directly.

    3. Both are set → the agent produced a short context paragraph AND
       a structured choice. The formatter returns a ``composite`` UCM
       with two children — text first, interactive second — so the
       channel adapter sends them in order (the dispatcher already
       drains rows by created order; this just preserves the same
       ordering in the UCM trace).

    The structured payload shape matches the ``response.send_interactive``
    tool args (see ``nexus_mcp.servers.notification.schemas``): a
    ``body`` plus exactly one of ``buttons`` / ``list`` / ``cta_url``,
    plus optional ``header`` / ``footer`` / ``context_message_id``.

    ``message_id`` defaults to a new UUIDv4 so each emission is uniquely
    addressable across channels. Children of a composite UCM derive
    their id from the parent's id (``<parent>::text``,
    ``<parent>::interactive``) so the trace stays joinable.
    """
    body = to_whatsapp_formatting(response_text or "")
    mid = message_id or str(uuid.uuid4())
    meta = metadata or {}

    if not interactive_payload:
        return _wrap_text(body, mid, meta)

    interactive_ucm = _build_interactive_ucm(interactive_payload, f"{mid}::interactive", meta)

    if not body.strip():
        # Agent answered with the component alone. Return it directly.
        return interactive_ucm

    # Both present → composite with text first, interactive second.
    text_child = _wrap_text(body, f"{mid}::text", meta)
    composite: dict[str, Any] = {
        "ucm_version": UCM_VERSION,
        "message_id": mid,
        "type": "composite",
        "capabilities_required": list(
            dict.fromkeys(text_child.capabilities_required + interactive_ucm.capabilities_required)
        ),
        "fallback_text": body
        if not interactive_ucm.fallback_text
        else f"{body}\n\n{interactive_ucm.fallback_text}",
        "metadata": meta,
        "content": {
            "children": [
                text_child.model_dump(mode="json"),
                interactive_ucm.model_dump(mode="json"),
            ]
        },
    }
    return parse_ucm(composite)


def _wrap_text(body: str, mid: str, metadata: dict[str, Any]) -> UCMMessage:
    payload: dict[str, Any] = {
        "ucm_version": UCM_VERSION,
        "message_id": mid,
        "type": "text",
        "capabilities_required": ["text"],
        "fallback_text": body,
        "metadata": metadata,
        "content": {"body": body, "format": "plain"},
    }
    return parse_ucm(payload)


def _build_interactive_ucm(
    payload: dict[str, Any],
    mid: str,
    metadata: dict[str, Any],
) -> UCMMessage:
    """Turn a validated ``response.send_interactive`` tool payload into
    a UCM message. Exactly one of ``buttons`` / ``list`` / ``cta_url``
    is expected to be set (the tool's own validator enforces it). The
    body / header / footer travel into the UCM unchanged; degrade() in
    ucm_schema handles per-channel limits at render time.
    """
    body = str(payload.get("body") or "")
    if payload.get("buttons"):
        buttons = [{"id": str(b["id"]), "title": str(b["title"])} for b in payload["buttons"]]
        # Composite captions / headers degrade per channel — keep them
        # in metadata for now since QuickRepliesContent doesn't model
        # header/footer (Meta supports them but the UCM schema scoped
        # them out of v1.0.0 for simplicity).
        return parse_ucm(
            {
                "ucm_version": UCM_VERSION,
                "message_id": mid,
                "type": "quick_replies",
                "capabilities_required": ["interactive.buttons"],
                "fallback_text": _fallback_buttons(body, buttons),
                "metadata": _meta_with_chrome(metadata, payload),
                "content": {"body": body, "buttons": buttons},
            }
        )
    if payload.get("list"):
        lst = payload["list"]
        sections: list[dict[str, Any]] = [
            {
                "title": "Opciones",
                "rows": [
                    {
                        "id": str(r["id"]),
                        "title": str(r["title"]),
                        **({"description": str(r["description"])} if r.get("description") else {}),
                    }
                    for r in lst["items"]
                ],
            }
        ]
        return parse_ucm(
            {
                "ucm_version": UCM_VERSION,
                "message_id": mid,
                "type": "list",
                "capabilities_required": ["interactive.list"],
                "fallback_text": _fallback_list(body, sections[0]["rows"]),
                "metadata": _meta_with_chrome(metadata, payload),
                "content": {
                    "body": body,
                    "button_text": str(lst["button"]),
                    "sections": sections,
                    **({"header": str(payload["header"])} if payload.get("header") else {}),
                    **({"footer": str(payload["footer"])} if payload.get("footer") else {}),
                },
            }
        )
    if payload.get("cta_url"):
        cta = payload["cta_url"]
        return parse_ucm(
            {
                "ucm_version": UCM_VERSION,
                "message_id": mid,
                "type": "cta_url",
                "capabilities_required": ["interactive.cta_url"],
                "fallback_text": f"{body}\n{cta['text']}: {cta['url']}",
                "metadata": _meta_with_chrome(metadata, payload),
                "content": {
                    "body": body,
                    "button_title": str(cta["text"]),
                    "url": str(cta["url"]),
                },
            }
        )

    if payload.get("products"):
        # Native catalog product cards are sent straight from
        # ``interactive_payload`` by the outbound dispatcher (product /
        # product_list Meta message). The UCM schema (v1.0.0) has no
        # product content type, so represent the turn as text for the
        # shadow/telemetry layer — the real product-card send is
        # unaffected. Without this the formatter would raise and fail the
        # whole turn (the customer gets no reply).
        n = len([p for p in payload["products"] if str(p).strip()])
        return _wrap_text(
            body or f"Te comparto {n} producto(s) del catálogo 👇", mid, metadata
        )

    if payload.get("catalog"):
        # Native Meta catalog message (interactive.type == "catalog_message").
        # Like products above, the real send happens straight from
        # ``interactive_payload`` in the outbound dispatcher; UCM v1.0.0 has
        # no catalog type, so shadow it as text so the formatter doesn't
        # raise and kill the turn.
        return _wrap_text(body or "Mira nuestro catálogo 👇", mid, metadata)

    # Unreachable if the tool's validator did its job, but stay loud
    # rather than silently downgrading: a missing component means the
    # agent emitted something malformed and the operator should see it
    # in traces.
    raise ValueError(
        "interactive_payload has no buttons / list / cta_url / products; "
        "tool validation should have caught this — refusing to "
        "fabricate a UCM"
    )


def _meta_with_chrome(base: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Carry header / footer / context_message_id on metadata so the
    outbound adapter can re-include them in the Meta interactive
    block. UCM v1.0.0 doesn't model these uniformly across types, but
    the adapter and ucm-schema's degrade() do not need them — only
    Meta does."""
    extras: dict[str, Any] = {}
    if payload.get("header"):
        extras["header"] = str(payload["header"])
    if payload.get("footer"):
        extras["footer"] = str(payload["footer"])
    if payload.get("context_message_id"):
        extras["context_message_id"] = str(payload["context_message_id"])
    return {**base, **extras} if extras else base


def _fallback_buttons(body: str, buttons: list[dict[str, str]]) -> str:
    """Plain-text rendering of buttons for non-WhatsApp channels and
    operator panels. WhatsApp degradation never uses this — the
    ucm-schema ``degrade`` keeps quick_replies native when supported."""
    enumerated = "\n".join(f"  {i + 1}) {b['title']}" for i, b in enumerate(buttons))
    return f"{body}\n{enumerated}" if body else enumerated


def _fallback_list(body: str, rows: list[dict[str, Any]]) -> str:
    enumerated = "\n".join(
        f"  {i + 1}) {r['title']}" + (f" — {r['description']}" if r.get("description") else "")
        for i, r in enumerate(rows)
    )
    return f"{body}\n{enumerated}" if body else enumerated


def shadow_diff_against_legacy(
    ucm: UCMMessage,
    legacy_response: str,
    *,
    channel: str = "whatsapp",
) -> dict[str, Any]:
    """Compare what the UCM would render to vs the agent's legacy reply.

    The legacy output for the WhatsApp channel today is just
    ``{"text": {"body": response}}``. We degrade the UCM to the channel and
    extract the body; both should be byte-identical while the formatter is
    a 1:1 wrapper. As soon as the formatter starts shaping richer content,
    this diff becomes the gate that proves the new path produces an
    equivalent surface before promoting it to source of truth.

    Returns a structured record with:
      - ``channel``        target channel name
      - ``degraded_type``  type of the degraded UCM
      - ``degraded_text``  text that would actually go out
      - ``diff_ratio``     0.0 == identical, 1.0 == fully divergent
      - ``equivalent``     bool: True iff ``degraded_text == legacy``
      - ``steps``          serialised degradation steps (empty if untouched)
    """
    result = degrade(ucm, channel)
    degraded = result.ucm
    degraded_text = ""
    if degraded.type == "text":
        degraded_text = degraded.content.body
    elif degraded.type == "media" and degraded.content.caption:
        degraded_text = degraded.content.caption

    legacy = legacy_response or ""
    diff_ratio = _crude_diff_ratio(legacy, degraded_text)

    return {
        "channel": channel,
        "degraded_type": degraded.type,
        "degraded_text": degraded_text,
        "legacy_length": len(legacy),
        "diff_ratio": diff_ratio,
        "equivalent": degraded_text == legacy,
        "steps": [
            {
                "reason": s.reason,
                "from": s.from_type,
                "to": s.to_type,
                "detail": s.detail,
            }
            for s in result.steps
        ],
    }


def _crude_diff_ratio(a: str, b: str) -> float:
    """Cheap symmetric similarity — 0.0 means identical, 1.0 totally different.

    Avoids pulling ``difflib.SequenceMatcher`` into the worker for one call.
    The shadow-validation gate in Fase 2 looks at byte equality; ratio is
    purely diagnostic, so a length-normalised char-set distance is enough.
    """
    if a == b:
        return 0.0
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    common = sum(1 for ch in a if ch in b)
    return 1.0 - (2 * common) / (len(a) + len(b))
