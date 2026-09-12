"""Spec 005 · what a dollar of purchased credit buys.

One number and one conversion, kept in their own module so the rate is
greppable rather than buried in a handler.
"""

from __future__ import annotations

#: USD per million quota units, from the assessment's ``concept.md`` §La
#: tarifa: 3.52 USD of provider cost against 10 USD sold, a 65% target
#: margin. **The same price as the included pool** — Lovable charges top-ups
#: 20% more than included credit and Cursor charges the same; the same was
#: chosen because a membership is access to the application, not a volume
#: discount on consumption.
#:
#: Provisional like every other figure in this spec (ADR-037). It lives here
#: and not in the database because changing it changes what past purchases
#: were worth, and that deserves a deploy and a diff.
CREDIT_USD_PER_MILLION = 10

#: Derived once so the two zeros of "cents" and the six of "million" are not
#: retyped at a call site.
_UNITS_PER_CENT = 1_000_000 // (CREDIT_USD_PER_MILLION * 100)


def units_for_cents(amount_cents: int) -> int:
    """Quota units bought by ``amount_cents``.

    Integer arithmetic, rounding **down**. Rounding up would hand out units
    on every purchase, and at any volume that is margin leaving without
    anyone deciding it. A non-positive amount buys nothing rather than
    raising: this runs in a background worker, and a refused notice is worse
    than a credited zero.
    """
    if amount_cents <= 0:
        return 0
    return amount_cents * _UNITS_PER_CENT
