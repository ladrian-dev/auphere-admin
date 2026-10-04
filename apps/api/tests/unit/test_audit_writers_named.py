"""Three audit writers that wrote rows the partner could not read well.

- Revoking a member's access named the person by a bare user id.
- The platform watcher's burst row had no ``target`` and was never written
  (see ``apps/worker/tests/unit/test_platform_watcher.py``).
- The sign-up row had a bare uuid as target (see
  ``tests/integration/test_signup_flow.py``).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.db.models import PartnerMembership

pytestmark = pytest.mark.asyncio


async def test_revoking_access_names_who_did_it_by_email(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    membership_id = uuid.uuid4()
    db_session.add(
        PartnerMembership(
            id=membership_id,
            partner_id=a["partner_id"],
            user_id=str(uuid.uuid4()),
            email="builder-x@example.com",
            role="builder",
            status="active",
        )
    )
    await db_session.commit()

    seen: dict[str, Any] = {}

    async def fake_revoke(_session, **kw: Any) -> dict[str, int]:
        seen.update(kw)
        return {"sessions_closed": 0, "machines_archived": 0}

    from nexus_api.api.console import team as team_module

    monkeypatch.setattr(team_module.principal_access, "revoke_all_access", fake_revoke)
    r = await client.delete(f"/console/team/members/{membership_id}/access", headers=a["headers"]())
    assert r.status_code == 204, r.text
    assert seen["actor"] == "console:owner-a@example.com"
