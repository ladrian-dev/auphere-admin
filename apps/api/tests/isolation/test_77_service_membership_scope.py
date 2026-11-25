"""Garantía 1 (RLS) — la membresía de un cliente es suya. Spec 077.

- Bajo el contexto de B no se ve la membresía de A, ni se puede escribir una
  con el ``tenant_id`` de A (``WITH CHECK``).
- La puerta de A no corta a B: B, sin membresía, envía.
- La rotación de una clave de envío conserva su cliente por los tres caminos
  (ficha del cliente, ficha del partner, consola): la nueva sigue siendo de A,
  nunca una clave de todo el partner que alcance a B. Antes de la 077 la
  ficha del partner y la consola la rotaban sin cliente.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ApiKeyScope,
    Partner,
    PartnerApiKey,
    ServiceMembership,
    Tenant,
    TenantPlan,
)
from nexus_api.services.membership_gate import blocks_sending

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _tenant(db_session, *, partner_id: uuid.UUID | None = None) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="T",
            slug=f"t-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            partner_id=partner_id,
        )
    )
    await db_session.commit()
    return tid


async def test_membership_of_a_is_invisible_under_b(db_session) -> None:
    a, b = await _tenant(db_session), await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, a):
        s.add(ServiceMembership(tenant_id=a, payer="stripe", amount_cents=4000))
    async with get_sessionmaker()() as s, tenant_scoped_session(s, b):
        seen = (await s.scalars(sa.select(ServiceMembership))).all()
        assert seen == []
        assert await blocks_sending(s) is False
    async with get_sessionmaker()() as s, tenant_scoped_session(s, a):
        assert await blocks_sending(s) is True


async def test_b_cannot_write_a_membership_for_a(db_session) -> None:
    a, b = await _tenant(db_session), await _tenant(db_session)
    with pytest.raises(DBAPIError):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, b):
            s.add(ServiceMembership(tenant_id=a, payer="stripe", amount_cents=4000))
            await s.flush()


async def test_without_context_no_membership_is_seen(db_session) -> None:
    a = await _tenant(db_session)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, a):
        s.add(ServiceMembership(tenant_id=a, payer="stripe", amount_cents=4000))
    async with get_sessionmaker()() as s, s.begin():
        await s.execute(sa.text("SET LOCAL ROLE nexus_app"))
        assert (await s.scalars(sa.select(ServiceMembership))).all() == []


async def _live_keys(db_session, partner_id: uuid.UUID) -> list[PartnerApiKey]:
    db_session.expire_all()
    rows = await db_session.scalars(
        sa.select(PartnerApiKey).where(
            PartnerApiKey.partner_id == partner_id, PartnerApiKey.revoked_at.is_(None)
        )
    )
    return list(rows)


async def test_admin_rotation_keeps_the_key_on_its_client(client, db_session, admin_headers):
    from nexus_api.services import operator_identity

    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="P", slug=f"p-{pid.hex[:6]}"))
    await db_session.commit()
    a = await _tenant(db_session, partner_id=pid)
    await _tenant(db_session, partner_id=pid)  # B, same partner
    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    operator = {**admin_headers, "X-Operator-Id": str(account.id)}

    created = await client.post(f"/admin/tenants/{a}/api-keys", headers=operator)
    assert created.status_code == 201, created.text
    first = created.json()["key"]["id"]
    from_client_page = await client.post(
        f"/admin/tenants/{a}/api-keys/{first}/rotate", json={"grace_hours": 0}, headers=operator
    )
    assert from_client_page.status_code == 201, from_client_page.text
    second = from_client_page.json()["key"]["id"]
    from_partner_page = await client.post(
        f"/admin/partners/{pid}/keys/{second}/rotate",
        json={"grace_hours": 0},
        headers=admin_headers,
    )
    assert from_partner_page.status_code == 201, from_partner_page.text

    live = await _live_keys(db_session, pid)
    assert len(live) == 1
    assert live[0].tenant_id == a


async def test_the_console_never_handles_a_clients_send_key(client, console_world, db_session):
    """/cso 2026-11-24 (R5.7): a client's send key is the operator's. A
    partner member could otherwise rotate it and walk away with a working
    secret that messages that client's customers."""
    a = console_world["a"]
    generated = generate_api_key()
    key = PartnerApiKey(
        partner_id=a["partner_id"],
        tenant_id=a["tenant_id"],
        prefix_snippet=generated.prefix_snippet,
        key_hash=generated.key_hash,
        scopes=[ApiKeyScope.MESSAGES_SEND.value],
    )
    db_session.add(key)
    await db_session.commit()

    listed = await client.get("/console/keys", headers=a["headers"]())
    assert listed.status_code == 200
    assert str(key.id) not in [k["id"] for k in listed.json()]
    for action, body in (("rotate", {"grace_hours": 0}), ("revoke", None)):
        resp = await client.post(
            f"/console/keys/{key.id}/{action}", headers=a["headers"](), json=body
        )
        assert resp.status_code == 404, (action, resp.text)

    live = await _live_keys(db_session, a["partner_id"])
    assert [(k.id, k.tenant_id) for k in live] == [(key.id, a["tenant_id"])]
