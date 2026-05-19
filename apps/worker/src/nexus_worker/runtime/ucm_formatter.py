"""UCM formatter — converts the agent's final response into a Universal
Channel Message (UCM v1.0.0).

Inserted as a graph node between ``respond`` and ``checkpoint`` (see
``pipeline.py``). When ``NEXUS_USE_UCM_FORMATTER`` is enabled, the node:

1. Reads ``state["response"]`` (the assistant's reply, today always plain
   text), wraps it in a ``type:"text"`` UCM and stamps a stable message id.
2. Runs ``degrade(ucm, "whatsapp")`` so we can compare the channel-rendered
   form against the legacy text — shadow validation.
3. Writes both the UCM and the shadow-diff summary back into the state.

The node is a pure-Python helper plus a tiny LangGraph wrapper; the heavy
lifting (validation, degradation) lives in ``@nexus/ucm-schema``. This file
intentionally has no side-effects: persistence happens in the downstream
``checkpoint`` node, which can decide what to do with the UCM (e.g. attach
it as Langfuse trace metadata; in a later phase, also persist it).

See ADR-020 and ``Auphere/nexus/features/qa-playground-mvp.md`` (Phase 2).
"""

from __future__ import annotations

import uuid
from typing import Any

from ucm_schema import (
    UCM_VERSION,
    UCMMessage,
    degrade,
    parse_ucm,
)


def format_response_as_ucm(
    *,
    response_text: str,
    message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> UCMMessage:
    """Convert a plain-text agent response into a UCM ``text`` message.

    This is the minimum-viable formatter for Phase 2 of ADR-020. Today the
    agent emits only text, so the UCM is a 1:1 wrapper with the response as
    both ``content.body`` and ``fallback_text``. When the agent starts
    emitting richer content (quick replies, lists, …), this function grows
    branches that recognise the structured shapes the LLM is asked to use;
    until then a one-line wrap is correct.

    ``message_id`` defaults to a new UUIDv4 so each emission is uniquely
    addressable across channels.
    """
    body = response_text or ""
    mid = message_id or str(uuid.uuid4())
    payload: dict[str, Any] = {
        "ucm_version": UCM_VERSION,
        "message_id": mid,
        "type": "text",
        "capabilities_required": ["text"],
        "fallback_text": body,
        "metadata": metadata or {},
        "content": {"body": body, "format": "plain"},
    }
    # parse_ucm validates the payload — fail loud if our own emission breaks
    # the schema. In practice this is unreachable for plain text but it
    # forms the contract for future structured payloads.
    return parse_ucm(payload)


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
