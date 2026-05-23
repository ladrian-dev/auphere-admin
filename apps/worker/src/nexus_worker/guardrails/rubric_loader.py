"""Bundled markdown rubrics — load by intent name + vertical.

Rubrics live next to this module in ``rubrics/<vertical>/<intent>.md``.
They are versioned with the worker source: shipping a new rubric is a
PR + deploy, not a runtime knob. A future migration may add per-tenant
overrides (column ``runtime_rubrics JSONB`` in ``agent_configs``); the
loader is designed to be the seam where that override layer goes
without touching the grader.

Intent-name convention (matches the spec §C.4):

- ``booking.confirm`` → ``restaurant/booking_confirm.md``
- ``booking.cancel`` → ``restaurant/booking_cancel.md``
- ``ecommerce.product_recommend`` → ``ecommerce/product_recommend.md``
- ``ecommerce.order_status`` → ``ecommerce/order_status.md``
- ``default.general_response`` → ``general/general_response.md``

If a more specific rubric is missing, the loader falls back to
``general/general_response.md`` — the operator opt-in still rides on
``NEXUS_OUTCOME_GRADER_ENABLED_TENANTS``, so this fallback only fires
for tenants that explicitly want the guardrail.
"""

from __future__ import annotations

import functools
from pathlib import Path

_RUBRICS_DIR = Path(__file__).resolve().parent / "rubrics"

_INTENT_TO_FILE: dict[str, Path] = {
    "booking.confirm": _RUBRICS_DIR / "restaurant" / "booking_confirm.md",
    "booking.cancel": _RUBRICS_DIR / "restaurant" / "booking_cancel.md",
    "ecommerce.product_recommend": _RUBRICS_DIR / "ecommerce" / "product_recommend.md",
    "ecommerce.order_status": _RUBRICS_DIR / "ecommerce" / "order_status.md",
    "default.general_response": _RUBRICS_DIR / "general" / "general_response.md",
}

# Fallback used when no intent-specific rubric exists. Keep this in
# sync with the table above — pointing to the general rubric.
_FALLBACK = _RUBRICS_DIR / "general" / "general_response.md"


@functools.lru_cache(maxsize=64)
def load_rubric_text(intent: str) -> str | None:
    """Return the rubric markdown body for ``intent``, or ``None``.

    LRU-cached because the worker reads rubrics on every turn for any
    tenant with the feature enabled. The rubric files are immutable for
    the lifetime of the process (they ship with the wheel), so caching
    is safe and faster than re-reading the filesystem.

    Falls back to the general rubric when the intent has no specific
    rubric registered — that way a tenant opted into the grader is
    never silently bypassed because of an intent name we did not map.
    """
    candidate = _INTENT_TO_FILE.get(intent, _FALLBACK)
    try:
        return candidate.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def available_rubric_intents() -> tuple[str, ...]:
    """Tuple of intents with a dedicated rubric (NOT including the
    fallback). Useful for the admin UI / config validation later."""
    return tuple(_INTENT_TO_FILE.keys())


__all__ = ["available_rubric_intents", "load_rubric_text"]
