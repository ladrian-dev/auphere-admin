"""Spec 004 · R4.2, R4.6 / CE-008 — one number decides, and only one.

Structural test. It does not exercise a scenario; it reads the source and
fails if the second counter comes back. That is deliberate: the defect this
spec removes was never a crash, it was two functions that both looked correct
and disagreed about the same money. A scenario test catches today's version of
that; this catches the next one.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = [pytest.mark.asyncio]


async def test_the_budget_endpoint_does_not_sum_runs() -> None:
    """``GET /console/companion/budget`` must read the book, not the run log."""
    from nexus_api.api.console import companion

    source = inspect.getsource(companion.get_budget)
    assert "sum_partner_companion_tokens" not in source, (
        "the budget endpoint is summing companion.runs again. That sum only sees "
        "Companion and teammate turns; the book is also drained by the clients' "
        "channel turns and by local execution, so the two disagree."
    )
    assert "partner_budget" in source


async def test_the_run_gate_does_not_compare_against_the_run_sum() -> None:
    """Starting a turn must be gated by the book, not by a second tally."""
    from nexus_api.api.console import companion

    source = inspect.getsource(companion.start_run)
    assert "companion_monthly_token_cap" not in source, (
        "the run gate still reads the deprecated monthly cap. The cap is the "
        "wallet now; two caps is the bug."
    )


async def test_the_attribution_helper_is_named_as_attribution() -> None:
    """``sum_partner_companion_tokens`` survives — as attribution only.

    Its docstring has to say so, because the next person to need "how much has
    this partner spent" will find it by name and reach for it.
    """
    from nexus_api.api.console.companion import sum_partner_companion_tokens

    doc = (sum_partner_companion_tokens.__doc__ or "").lower()
    assert "atribuci" in doc or "attribution" in doc, (
        "the helper that is no longer the total must say what it is now"
    )


async def test_the_deprecated_cap_is_marked_as_deprecated() -> None:
    """``companion_monthly_token_cap`` stays as a column but stops being a cap.

    It is not dropped here: creating its replacement and dropping it in the
    same migration leaves a ``downgrade()`` that cannot return the data.
    """
    import re
    from pathlib import Path

    src = Path(inspect.getfile(__import__("nexus_api.db.models.partner", fromlist=["x"])))
    text = src.read_text()
    block = re.search(r"companion_monthly_token_cap.*?(?=\n    [a-z_]+: Mapped)", text, re.S)
    assert block is not None
    around = text[max(0, block.start() - 1200) : block.end()]
    assert "deprecad" in around.lower() or "deprecated" in around.lower(), (
        "the column that used to be the cap must be marked deprecated, naming the "
        "migration that will drop it"
    )
