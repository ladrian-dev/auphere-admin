"""``notification.send_template`` refuses only templates Meta did not approve.

The status webhook stores Meta's value as sent (``"APPROVED"``, uppercase);
the guard used to compare against ``"approved"`` and refused every approved
template that had ever received a status webhook.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from nexus_mcp.servers.notification.tools import _assert_template_approved

pytestmark = pytest.mark.asyncio


class _Session:
    def __init__(self, row: Any) -> None:
        self._row = row

    async def scalar(self, _stmt: Any) -> Any:
        return self._row


@pytest.mark.parametrize("status", ["APPROVED", "approved"])
async def test_an_approved_template_passes_whatever_the_case(status: str) -> None:
    row = SimpleNamespace(status=status, reason=None)
    await _assert_template_approved(_Session(row), waba_id="W", template_name="t", language="es")


@pytest.mark.parametrize("status", ["PAUSED", "REJECTED", "DISABLED"])
async def test_a_template_meta_did_not_approve_is_refused(status: str) -> None:
    row = SimpleNamespace(status=status, reason="quality")
    with pytest.raises(Exception, match=status):
        await _assert_template_approved(
            _Session(row), waba_id="W", template_name="t", language="es"
        )


async def test_no_row_is_permissive() -> None:
    await _assert_template_approved(_Session(None), waba_id="W", template_name="t", language="es")
