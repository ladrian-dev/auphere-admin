"""Spec 047, requisito 13.7 — la pasada en segundo plano que lanza un cambio de
la ficha avisa al partner si deja pruebas en rojo (``agent.tests.failing``, una
por agente y día; ``contracts/events.md`` §3). Las demás pasadas no avisan: las
lanzó alguien que está mirando."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_worker.jobs.handlers.agent_tests import tell_failing

pytestmark = [pytest.mark.unit]

TENANT = uuid.UUID("11111111-1111-4111-8111-111111111111")
AGENT = uuid.UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    async def fake_announce(**kw: Any) -> None:
        out.append(kw)

    monkeypatch.setattr("nexus_api.services.channel_config.announce", fake_announce)
    return out


async def test_a_business_change_with_failures_tells_the_partner(
    sent: list[dict[str, Any]],
) -> None:
    await tell_failing(TENANT, AGENT, reason="business_change", failed=2, sections=["hours"])
    (notice,) = sent
    assert notice["tenant_id"] == TENANT
    assert (notice["kind"], notice["severity"]) == ("agent.tests.failing", "warning")
    assert notice["data"] == {"agent_id": str(AGENT), "failed": 2, "sections": ["hours"]}
    # Una por agente y día.
    assert notice["dedupe_key"].startswith(f"agent.tests.failing:{AGENT}:")
    assert notice.get("to_client", False) is False


@pytest.mark.parametrize(
    ("reason", "failed"),
    [("business_change", 0), ("business_change", None), ("manual", 3), ("certification", 1)],
)
async def test_nothing_to_say_otherwise(
    sent: list[dict[str, Any]], reason: str, failed: int | None
) -> None:
    await tell_failing(TENANT, AGENT, reason=reason, failed=failed, sections=[])
    assert sent == []
