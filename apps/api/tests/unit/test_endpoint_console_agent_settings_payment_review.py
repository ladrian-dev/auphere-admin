"""Spec 025 (Requisito 4): «Revisión de pagos» in the agent settings endpoint.

The reviewers are read from the version being edited, written normalised on
the draft, applied by publishing, shown in the review sheet, and refused by
number when one could never match a sender.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig
from tests.unit.test_endpoint_console_agent_tools import SETTINGS, _stage_and_publish

pytestmark = pytest.mark.asyncio

REVIEWERS = {
    "reviewers": [
        {"phone": "+56 9 9128 0655", "name": "Daniela"},
        {"phone": "56989829063"},
    ]
}


async def _policies(db_session, tenant_id, version: int) -> dict:
    async with tenant_scoped_session(db_session, tenant_id):
        row = await db_session.scalar(
            sa.select(AgentConfig.policies).where(
                AgentConfig.tenant_id == tenant_id, AgentConfig.version == version
            )
        )
    return row or {}


async def test_reviewers_are_saved_on_the_draft_and_applied_by_publishing(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"
    v1 = await _stage_and_publish(client, a)

    before = await client.get(f"{base}/settings", headers=h())
    assert before.json()["payment_review"] == {"reviewers": []}

    saved = await client.put(
        f"{base}/settings",
        headers=h(),
        json={"settings": SETTINGS, "payment_review": REVIEWERS},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["payment_review"]["reviewers"] == [
        {"phone": "+56991280655", "name": "Daniela"},
        {"phone": "+56989829063", "name": None},
    ]
    assert "payment_review" not in await _policies(db_session, a["tenant_id"], v1)

    diff = await client.get(f"{base}/draft-diff", headers=h())
    rows = {r["field"]: r for r in diff.json()["settings"]}
    assert rows["payment_review"]["before"] == {"count": 0}
    assert rows["payment_review"]["after"] == {"count": 2}

    pub = await client.post(f"{base}/versions/{v1 + 1}/publish", headers=h())
    assert pub.status_code == 200, pub.text
    published = await _policies(db_session, a["tenant_id"], v1 + 1)
    assert [r["phone"] for r in published["payment_review"]["reviewers"]] == [
        "+56991280655",
        "+56989829063",
    ]


async def test_a_put_without_reviewers_leaves_them_alone(client, console_world) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"
    await _stage_and_publish(client, a)
    await client.put(
        f"{base}/settings", headers=h(), json={"settings": SETTINGS, "payment_review": REVIEWERS}
    )
    again = await client.put(f"{base}/settings", headers=h(), json={"settings": SETTINGS})
    assert len(again.json()["payment_review"]["reviewers"]) == 2


async def test_a_number_that_could_never_match_is_refused_by_name(client, console_world) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"
    await _stage_and_publish(client, a)
    bad = await client.put(
        f"{base}/settings",
        headers=h(),
        json={"settings": SETTINGS, "payment_review": {"reviewers": [{"phone": "12"}]}},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == {"code": "payment_reviewer_invalid_phone", "phone": "12"}
