"""Split an agent reply into messages a channel accepts.

Instagram counts **bytes** (1000 per text message, UTF-8); Messenger counts
characters (2000). A reply that does not fit goes out as consecutive
messages, cut at a paragraph, then a sentence, then a word — never inside
one, and never inside a multi-byte character.
"""

from __future__ import annotations

import re
from collections.abc import Callable

INSTAGRAM_MAX_BYTES = 1000
MESSENGER_MAX_CHARS = 2000

_BREAKS = (re.compile(r"\n\s*\n"), re.compile(r"(?<=[.!?…])\s+"), re.compile(r"\s+"))


def split_message(
    text: str, *, max_bytes: int | None = None, max_chars: int | None = None
) -> list[str]:
    """Return ``text`` as a list of chunks that each fit the limit.

    Exactly one of ``max_bytes`` / ``max_chars`` is the binding limit; when
    both are given each chunk respects both.
    """
    text = text.strip()
    if not text:
        return []
    if max_bytes is None and max_chars is None:
        return [text]

    def fits(chunk: str) -> bool:
        if max_chars is not None and len(chunk) > max_chars:
            return False
        return not (max_bytes is not None and len(chunk.encode("utf-8")) > max_bytes)

    chunks: list[str] = []
    rest = text
    while rest:
        if fits(rest):
            chunks.append(rest)
            break
        cut = _best_cut(rest, fits)
        head, rest = rest[:cut].rstrip(), rest[cut:].lstrip()
        if head:
            chunks.append(head)
    return chunks


def _best_cut(text: str, fits: Callable[[str], bool]) -> int:
    # Longest prefix that fits, by characters (binary search keeps it linear
    # in practice even for long replies).
    lo, hi = 1, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(text[:mid]):
            lo = mid
        else:
            hi = mid - 1
    limit = lo
    for pattern in _BREAKS:
        cut = 0
        for m in pattern.finditer(text, 0, limit + 1):
            if m.start() == 0:
                continue
            if m.start() <= limit:
                cut = m.start()
        # Only accept a break that keeps a reasonable amount of text, so a
        # stray early newline does not produce a one-word message.
        if cut >= limit // 3:
            return cut
    return limit
