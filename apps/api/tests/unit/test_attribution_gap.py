"""Spec 004 · R4.4 — the gap between the total and what is attributed is named.

The partner's total is the book. What ``/console/teammates/usage`` can attribute
to a named teammate is only the Companion and teammate runs. The difference is
real — the clients' channel turns and local execution — and it has to be
**said**, not hidden and not spread over the teammates that do appear.

The Account screen already has the line for it (``account.usage.elsewhere``),
written with this exact problem in mind: *"dos cifras que no suman y nadie
diciendo por qué es la manera de que nadie vuelva a creerse ninguna."* This test
protects the number behind that line.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio]


async def test_elsewhere_is_the_difference_not_a_reallocation() -> None:
    from nexus_api.api.console.companion import attribution_gap

    assert attribution_gap(total=10_000, attributed=4_000) == 6_000


async def test_gap_is_zero_when_everything_is_attributed() -> None:
    from nexus_api.api.console.companion import attribution_gap

    assert attribution_gap(total=4_000, attributed=4_000) == 0


async def test_gap_never_goes_negative() -> None:
    """Attribution can exceed the book for a moment: the run row closes inside
    the request while the ledger entry is written just after. A negative
    "spent elsewhere" would be nonsense on screen, so it floors at zero."""
    from nexus_api.api.console.companion import attribution_gap

    assert attribution_gap(total=1_000, attributed=1_500) == 0
