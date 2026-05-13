"""Owner inbound message parser.

The owner sends free-form text (or, in Phase 2, slash commands) over
WhatsApp. This module turns that text into a tagged
:class:`ParsedOwnerMessage` the webhook handler can route on.

Phase 1 scope (per ADR-018 + ``architecture/owner-backchannel.md`` §13):
- ``free_text`` — anything that doesn't match a yes / no shortcut.
- ``yes`` — unambiguous affirmatives (sí, ok, dale, listo, hecho).
- ``no`` — unambiguous negatives.
- ``unknown_command`` — recognised slash prefix but the verb is not in
  the Phase 1 set; the handler should reply "use /help" but Phase 1 has
  no slash verbs implemented, so any slash command degrades to
  ``unknown_command``.

The parser is intentionally **conservative**: borderline messages
("hmm puede ser") classify as ``free_text``, not as a yes/no. The
agent sees the literal text in the fanout system note and can ask the
customer for clarification if needed — that is much safer than
mis-classifying.
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


@dataclass(frozen=True)
class ParsedOwnerMessage:
    """Result of parsing a single owner inbound text.

    ``kind`` is the routing label the handler dispatches on. ``free_text``
    carries the (stripped) original text. ``yes`` / ``no`` keep the
    original text in ``free_text`` for the audit log.
    """

    kind: str  # 'free_text' | 'yes' | 'no' | 'unknown_command' | 'empty'
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

    # Slash commands — Phase 2 will route the recognised verbs. Phase 1
    # acknowledges that the owner tried a slash command but cannot act
    # on it; the webhook handler replies with a "not yet supported" note.
    m = _COMMAND_RE.match(stripped)
    if m:
        verb = (m.group(1) or "").lower()
        arg = (m.group(2) or "").strip()
        return ParsedOwnerMessage(
            kind="unknown_command",
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
