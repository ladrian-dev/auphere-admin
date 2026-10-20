"""The partner sets its own billing e-mail (owner, 2026-10-20).

Until now only the Admin could, and the console said «escríbenos». The 3D
Secure notice goes to this address, so the partner has to be able to set it.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog, Partner
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio


async def test_the_owner_sets_and_clears_it_and_the_audit_says_so(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    res = await client.put(
        "/console/billing/email",
        headers=a["headers"](),
        json={"billing_email": " Facturas@Partner-A.example "},
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"billing_email": "facturas@partner-a.example"}

    shown = await client.get("/console/billing", headers=a["headers"]())
    assert shown.json()["billing_email"] == "facturas@partner-a.example"

    row = (
        await db_session.execute(
            sa.select(AuditLog).where(AuditLog.action == "console.billing.email_update")
        )
    ).scalar_one()
    assert row.before_json == {"billing_email": None}
    assert row.after_json == {"billing_email": "facturas@partner-a.example"}
    assert row.target == f"partner:{a['partner_id']}"

    # The same value again writes nothing new.
    again = await client.put(
        "/console/billing/email",
        headers=a["headers"](),
        json={"billing_email": "facturas@partner-a.example"},
    )
    assert again.status_code == 200
    count = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "console.billing.email_update")
        )
    ).scalar_one()
    assert count == 1

    cleared = await client.put(
        "/console/billing/email", headers=a["headers"](), json={"billing_email": None}
    )
    assert cleared.json() == {"billing_email": None}


async def test_a_bad_address_and_a_role_without_billing_are_refused(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    bad = await client.put(
        "/console/billing/email", headers=a["headers"](), json={"billing_email": "no-es-correo"}
    )
    assert bad.status_code == 422

    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    denied = await client.put(
        "/console/billing/email",
        headers=builder["headers"](),
        json={"billing_email": "x@partner-a.example"},
    )
    assert denied.status_code == 403

    # Partner B's change never touches A.
    ok = await client.put(
        "/console/billing/email",
        headers=b["headers"](),
        json={"billing_email": "facturas@partner-b.example"},
    )
    assert ok.status_code == 200
    a_row = await db_session.get(Partner, a["partner_id"])
    await db_session.refresh(a_row)
    assert a_row is not None and a_row.billing_email is None
