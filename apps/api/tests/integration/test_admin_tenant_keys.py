"""Spec 077 · R5 — claves de envío de un cliente desde el panel.

- Lista las claves del cliente, también una creada a mano (la de New Air).
- Emite una ligada al cliente, solo con ``messages_send``, del partner del
  cliente o del contenedor de los directos.
- Rotar conserva el cliente, también desde la ficha del partner (el fallo de
  antes: la nueva perdía el cliente y daba 403 al vencer la gracia).
- Revoca. Cada escritura nombra al operador. La clave de otro cliente es 404.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    ApiKeyScope,
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Partner,
    PartnerApiKey,
    Tenant,
    TenantPlan,
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_TEMPLATE = TemplateOut(
    id="t1",
    name="aviso",
    language="es",
    category="UTILITY",
    status="APPROVED",
    components=[{"type": "BODY", "text": "Hola {{nombre}}"}],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_TEMPLATE], "waba-1"

    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)


async def _operator(db_session: Any, admin_headers: dict[str, str]) -> dict[str, str]:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id), "_email": account.email}


async def _tenant(db_session: Any, *, partner_id: uuid.UUID | None = None) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Tecfin",
            slug=f"tf-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            partner_id=partner_id,
            send_only=True,
        )
    )
    await db_session.flush()
    db_session.add(
        Channel(
            tenant_id=tid,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+5622{tid.int % 10_000_000:07d}",
            status=ChannelStatus.ACTIVE,
        )
    )
    await db_session.commit()
    return tid


@pytest_asyncio.fixture
async def headers(db_session, admin_headers) -> dict[str, str]:
    h = await _operator(db_session, admin_headers)
    return h


def _clean(h: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in h.items() if not k.startswith("_")}


async def _send(client: Any, plaintext: str) -> int:
    resp = await client.post(
        "/v1/messages/template",
        json={"to": "+56912345678", "template_name": "aviso", "variables": {"nombre": "Ana"}},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    return resp.status_code


async def test_create_binds_the_key_to_the_client_and_it_sends(client, db_session, headers):
    tid = await _tenant(db_session)
    resp = await client.post(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["key"]["tenant_id"] == str(tid)
    assert body["key"]["scopes"] == [ApiKeyScope.MESSAGES_SEND.value]
    assert body["plaintext"].startswith("ak_")
    # The direct client's key hangs from the direct container partner.
    partner = await db_session.scalar(sa.select(Partner).where(Partner.slug == "auphere-direct"))
    assert partner is not None
    assert body["key"]["partner_id"] == str(partner.id)
    assert await _send(client, body["plaintext"]) == 202


async def test_key_of_a_partners_client_hangs_from_that_partner(client, db_session, headers):
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="P", slug=f"pp-{pid.hex[:6]}"))
    await db_session.commit()
    tid = await _tenant(db_session, partner_id=pid)
    resp = await client.post(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))
    assert resp.json()["key"]["partner_id"] == str(pid)


async def test_list_shows_keys_created_by_hand(client, db_session, headers):
    """R5.1 y R11.3: la clave de New Air, emitida por el script, aparece."""
    tid = await _tenant(db_session)
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="Direct", slug=f"dd-{pid.hex[:6]}"))
    generated = generate_api_key()
    db_session.add(
        PartnerApiKey(
            partner_id=pid,
            tenant_id=tid,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=[ApiKeyScope.MESSAGES_SEND.value],
        )
    )
    await db_session.commit()
    resp = await client.get(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))
    assert resp.status_code == 200
    assert [k["prefix_snippet"] for k in resp.json()] == [generated.prefix_snippet]
    # Issued outside the panel: nobody to name.
    assert resp.json()[0]["created_by"] is None


async def test_list_names_who_issued_each_key(client, db_session, headers):
    """R5.1: quién y cuándo la creó, también tras rotarla."""
    tid = await _tenant(db_session)
    created = (await client.post(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))).json()
    assert created["key"]["created_by"] == headers["_email"]
    await client.post(
        f"/admin/tenants/{tid}/api-keys/{created['key']['id']}/rotate",
        json={"grace_hours": 1},
        headers=_clean(headers),
    )
    listed = (await client.get(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))).json()
    assert [k["created_by"] for k in listed] == [headers["_email"], headers["_email"]]


async def test_rotate_keeps_the_client(client, db_session, headers):
    tid = await _tenant(db_session)
    created = (await client.post(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))).json()
    rotated = await client.post(
        f"/admin/tenants/{tid}/api-keys/{created['key']['id']}/rotate",
        json={"grace_hours": 0},
        headers=_clean(headers),
    )
    assert rotated.status_code == 201, rotated.text
    assert rotated.json()["key"]["tenant_id"] == str(tid)
    assert await _send(client, rotated.json()["plaintext"]) == 202
    assert await _send(client, created["plaintext"]) == 401


async def test_rotation_follows_the_clients_current_partner(client, db_session, headers):
    """R5.8: a client moved to another partner takes its key along on the
    next rotation (limit and suspension are the new partner's)."""
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    db_session.add_all(
        [
            Partner(id=p1, name="P1", slug=f"p1-{p1.hex[:6]}"),
            Partner(id=p2, name="P2", slug=f"p2-{p2.hex[:6]}"),
        ]
    )
    await db_session.commit()
    tid = await _tenant(db_session, partner_id=p1)
    created = (await client.post(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))).json()
    assert created["key"]["partner_id"] == str(p1)
    await db_session.execute(sa.update(Tenant).where(Tenant.id == tid).values(partner_id=p2))
    await db_session.commit()
    rotated = await client.post(
        f"/admin/tenants/{tid}/api-keys/{created['key']['id']}/rotate",
        json={"grace_hours": 0},
        headers=_clean(headers),
    )
    assert rotated.status_code == 201, rotated.text
    assert rotated.json()["key"]["partner_id"] == str(p2)
    assert rotated.json()["key"]["tenant_id"] == str(tid)


async def test_partner_page_rotation_keeps_the_client(client, db_session, headers, admin_headers):
    """El fallo de antes: rotar desde la ficha del partner perdía el cliente."""
    tid = await _tenant(db_session)
    created = (await client.post(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))).json()
    partner_id = created["key"]["partner_id"]
    rotated = await client.post(
        f"/admin/partners/{partner_id}/keys/{created['key']['id']}/rotate",
        json={"grace_hours": 0},
        headers=admin_headers,
    )
    assert rotated.status_code == 201, rotated.text
    assert rotated.json()["tenant_id"] == str(tid)
    assert await _send(client, rotated.json()["plaintext"]) == 202


async def test_revoke_and_audit_name_the_operator(client, db_session, headers):
    tid = await _tenant(db_session)
    created = (await client.post(f"/admin/tenants/{tid}/api-keys", headers=_clean(headers))).json()
    revoked = await client.post(
        f"/admin/tenants/{tid}/api-keys/{created['key']['id']}/revoke", headers=_clean(headers)
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert await _send(client, created["plaintext"]) == 401
    await db_session.rollback()
    async with db_session.begin():
        await db_session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tid)}
        )
        actors = (
            await db_session.scalars(
                sa.select(AuditLog.actor).where(AuditLog.action.like("tenant_key.%"))
            )
        ).all()
    assert set(actors) == {f"operator:{headers['_email']}"}


async def test_writes_need_an_operator(client, db_session, admin_headers):
    tid = await _tenant(db_session)
    resp = await client.post(f"/admin/tenants/{tid}/api-keys", headers=admin_headers)
    assert resp.status_code == 400


async def test_another_clients_key_is_404(client, db_session, headers):
    a = await _tenant(db_session)
    b = await _tenant(db_session)
    created = (await client.post(f"/admin/tenants/{a}/api-keys", headers=_clean(headers))).json()
    for action in ("rotate", "revoke"):
        resp = await client.post(
            f"/admin/tenants/{b}/api-keys/{created['key']['id']}/{action}",
            json={"grace_hours": 0} if action == "rotate" else None,
            headers=_clean(headers),
        )
        assert resp.status_code == 404, action
