"""Owner inbound message parser.

The owner sends free-form text or slash commands over WhatsApp. This
module turns that text into a tagged :class:`ParsedOwnerMessage` the
webhook handler can route on.

Phase 1 + Phase 2 vocabulary:

- ``free_text`` — anything that doesn't match a yes/no shortcut or a
  known slash verb.
- ``yes`` / ``no`` — unambiguous affirmatives/negatives (sí, ok, dale,
  listo / no, nope, negativo). Both natural and ``/yes`` / ``/no``
  shortcuts collapse to these kinds.
- Phase 2 slash kinds — ``done``, ``handoff``, ``pause``, ``help``.
  ``slash_verb`` is set to the literal verb on every slash kind so the
  webhook can build an accurate ack message.
- ``unknown_command`` — slash with a verb not in the recognised set;
  the webhook replies with the help list.

The parser is intentionally **conservative**: borderline messages
("hmm puede ser") classify as ``free_text``, not as a yes/no. The
agent sees the literal text in the fanout system note and can ask the
customer for clarification if needed — much safer than mis-classifying.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_COMMAND_RE = re.compile(r"^/(\w+)(?:\s+(.*))?$", re.DOTALL)

# Lowercased, stripped. Whole-message match — these are unambiguous on
# their own ("sí." with a period also qualifies after rstrip(".!?")).
_YES_TOKENS = frozenset(
    {
        "si",
        "sí",
        "si.",
        "sí.",
        "yes",
        "ok",
        "okey",
        "okay",
        "dale",
        "listo",
        "hecho",
        "perfecto",
        "confirmo",
        "confirmado",
        "ya",
        "yep",
    }
)

_NO_TOKENS = frozenset(
    {
        "no",
        "no.",
        "nope",
        "negativo",
        "imposible",
        "ahora no",
        "no por ahora",
    }
)


# Slash verbs that map 1:1 to a ``kind``. Both ``yes`` and ``no``
# collapse into the same kinds as their natural-language counterparts
# so the dispatch table is simpler.
_SLASH_VERB_KIND: dict[str, str] = {
    "yes": "yes",
    "no": "no",
    "done": "done",
    "handoff": "handoff",
    "pause": "pause",
    "help": "help",
}


@dataclass(frozen=True)
class ParsedOwnerMessage:
    """Result of parsing a single owner inbound text.

    ``kind`` is the routing label the handler dispatches on. ``free_text``
    carries the (stripped) original text. ``yes`` / ``no`` / slash kinds
    keep the original text in ``free_text`` for the audit log.
    """

    kind: str  # 'free_text' | 'yes' | 'no' | 'done' | 'handoff' | 'pause' | 'help' | 'unknown_command' | 'empty'
    free_text: str = ""
    slash_verb: str | None = None
    slash_arg: str = ""


def parse_owner_message(text: str) -> ParsedOwnerMessage:
    """Parse the owner's WhatsApp text into a routing decision.

    The parser is pure (no IO) so it can be unit-tested exhaustively
    without DB or network fixtures.
    """
    if text is None:
        return ParsedOwnerMessage(kind="empty")
    stripped = text.strip()
    if not stripped:
        return ParsedOwnerMessage(kind="empty")

    # Slash commands — recognised verbs route to dedicated kinds; an
    # unknown verb returns ``unknown_command`` so the webhook can reply
    # with the help list rather than silently swallow it.
    m = _COMMAND_RE.match(stripped)
    if m:
        verb = (m.group(1) or "").lower()
        arg = (m.group(2) or "").strip()
        kind = _SLASH_VERB_KIND.get(verb, "unknown_command")
        return ParsedOwnerMessage(
            kind=kind,
            free_text=stripped,
            slash_verb=verb,
            slash_arg=arg,
        )

    # Normalise for the yes/no shortcuts.
    lowered = stripped.lower().rstrip(".!?")
    if lowered in _YES_TOKENS:
        return ParsedOwnerMessage(kind="yes", free_text=stripped)
    if lowered in _NO_TOKENS:
        return ParsedOwnerMessage(kind="no", free_text=stripped)

    return ParsedOwnerMessage(kind="free_text", free_text=stripped)
