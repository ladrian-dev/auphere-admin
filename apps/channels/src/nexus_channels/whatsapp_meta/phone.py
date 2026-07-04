"""E.164 normalisation — the single rule for ``channels.provider_identifier``.

Meta hands the business phone number in two different shapes depending on the
surface:

- **Signup** reads it from ``GET /{phone_number_id}?fields=display_phone_number``
  which returns a *formatted* number, e.g. ``"+34 672 13 83 67"``.
- **Webhook** reads ``value.metadata.display_phone_number`` which is usually
  *unformatted*, e.g. ``"34672138367"``.

The channel is stored on signup and resolved on every inbound webhook by
exact match on ``provider_identifier``. If the two surfaces normalise
differently the webhook can't find the channel (``channel.unresolved_event``)
and the agent goes silent. So BOTH must funnel through this one function,
which reduces any input to canonical E.164: a leading ``+`` followed by
digits only.
"""

from __future__ import annotations

import re
from typing import Any


def to_e164(phone: Any) -> str | None:
    """Strip every non-digit and return E.164 with a leading ``+``.

    ``"+34 672 13 83 67"`` and ``"34672138367"`` both become
    ``"+34672138367"``. Returns ``None`` for empty / non-string input.
    """
    if not isinstance(phone, str):
        return None
    digits = re.sub(r"\D", "", phone)
    return f"+{digits}" if digits else None


__all__ = ["to_e164"]
