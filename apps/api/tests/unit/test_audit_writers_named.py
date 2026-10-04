"""Three audit writers that wrote rows the partner could not read well.

- Revoking a member's access named the person by a bare user id.
- The platform watcher's burst row had no ``target`` and was never written
  (see ``apps/worker/tests/unit/test_platform_watcher.py``).
- The sign-up row had a bare uuid as target (see
  ``tests/integration/test_signup_flow.py``).
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.db.models import PartnerMembership

pytestmark = pytest.mark.asyncio


async def test_the_owner_sees_who_revoked_whose_access(client, console_world, db_session) -> None:
    """Owner, 2026-10-04: the owner wants to see it in Auditoría. The row is
    written under the partner, names who did it by email (not a bare user
    id) and says whose access it was."""
    from nexus_api.api.console import audit as audit_module

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
    audit_module.reset_vocabulary_cache_for_tests()

    r = await client.delete(f"/console/team/members/{membership_id}/access", headers=a["headers"]())
    assert r.status_code == 204, r.text

    items = (
        await client.get("/console/audit?lang=es&category=team", headers=a["headers"]())
    ).json()["items"]
    row = next(i for i in items if i["action"] == "principal.access_revoked")
    assert row["summary"] == (
        "owner-a@example.com retiró el acceso de builder-x@example.com: "
        "sus sesiones y sus máquinas."
    )
    assert row["actor_kind"] == "person"
    # Partner B does not see A's team.
    b = console_world["b"]
    other = (await client.get("/console/audit", headers=b["headers"]())).json()["items"]
    assert all(i["action"] != "principal.access_revoked" for i in other)
