"""Spec 048 — turning Reservas on from Acceso still passes the client
(requirement 3.9).

The pass by hand («Pasar a Reservas» in the panel, and its two ``/admin``
routes) is gone: it is automatic, in every deploy (``test_auto_pass.py``).
Turning the module on from the Acceso tab keeps doing what it did: every active
agent gets a draft with ``reservas.*`` in its four places — not published, it
goes through the gate — and the future appointments are imported, with the
report in the client's audit (``reservations.passed``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AgentConfig, AgentConfigStatus, AuditLog
from nexus_api.services import operator_identity
from tests.integration.reservations._legacy_world import (
    agent_with_booking,
    appointment,
    customer,
    read,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _operator(db_session, admin_headers) -> dict[str, str]:
    email = f"ops-{uuid.uuid4().hex[:8]}@auphere.test"
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session, email=email, password="operator-password-1", display_name="Ops"
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def test_activating_reservas_passes_the_client_too(
    client, db_session, console_world, admin_headers
) -> None:
    """Turning the module on prepares the draft with ``reservas.*`` in the four
    places and imports, with its report in the audit. Freshly turned on there
    are no services: nothing matches and nothing is lost."""
    w = console_world["b"]
    tenant_id = w["tenant_id"]
    agent_id = await agent_with_booking(db_session, tenant_id)
    customer_id = await customer(db_session, tenant_id)
    starts = datetime.now(UTC) + timedelta(days=3)
    future = appointment(tenant_id, customer_id, None, "Corte", starts)
    db_session.add(future)
    await db_session.commit()
    h = await _operator(db_session, admin_headers)
    r = await client.put(
        f"/admin/tenants/{tenant_id}/client-access",
        headers=h,
        json={"enabled": True, "modules": ["panel", "reservas"], "reservas": {"mode": "services"}},
    )
    assert r.status_code == 200, r.text

    async def versions(session):  # type: ignore[no-untyped-def]
        return list(
            (
                await session.execute(
                    sa.select(AgentConfig)
                    .where(AgentConfig.agent_id == agent_id)
                    .order_by(AgentConfig.version)
                )
            ).scalars()
        )

    active, staged = await read(tenant_id, versions)
    # Nothing is promoted by itself: the active version still books with booking.*.
    assert active.status == AgentConfigStatus.ACTIVE
    assert "booking.create_appointment" in active.tools
    assert staged.status == AgentConfigStatus.STAGED
    assert not [t for t in staged.spec["tools"] if t.startswith("booking.")]
    assert staged.spec["procedures"][0]["tools"] == ["reservas.find_slots", "reservas.create"]
    assert "booking." not in staged.system_prompt_rendered

    async def audit(session):  # type: ignore[no-untyped-def]
        return await session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "reservations.passed")
        )

    row = await read(tenant_id, audit)
    assert row is not None
    assert row.actor.startswith("operator:")
    assert row.after_json["automatic"] is False
    assert row.after_json["imported"] == 0
    assert [n["appointment_id"] for n in row.after_json["not_imported"]] == [str(future.id)]
