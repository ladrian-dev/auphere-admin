"""Spec 030 — el acceso del cliente desde el admin (R1.1 a R1.3, R1.7, R1.8).

``/admin/tenants/{tenant_id}/client-access``: el operador de Auphere enciende
la consola lite de un cliente y elige sus módulos. Lo que fija este archivo:

- quién es elegible (cliente en un partner, no archivado) y por qué no;
- las reglas de módulos: al menos uno con el acceso encendido, y la Bandeja
  solo con un WhatsApp conectado;
- apagar el acceso cierra las sesiones de sus personas;
- la auditoría nombra al OPERADOR (``operator:<correo>``), nunca el prefijo
  del token del admin; sin operador identificado, no hay acción.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    ConsoleSession,
    PartnerTenant,
    Tenant,
    TenantPlan,
)
from nexus_api.services import console_identity, operator_identity

pytestmark = pytest.mark.asyncio


async def _operator(db_session) -> tuple[uuid.UUID, str]:
    email = f"ops-{uuid.uuid4().hex[:8]}@auphere.test"
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session, email=email, password="operator-password-1", display_name="Ops"
        )
    return op.id, email


def _url(tenant_id: uuid.UUID) -> str:
    return f"/admin/tenants/{tenant_id}/client-access"


async def _headers(db_session, admin_headers) -> tuple[dict[str, str], str]:
    op_id, email = await _operator(db_session)
    return {**admin_headers, "X-Operator-Id": str(op_id)}, email


def _whatsapp(tenant_id: uuid.UUID, status: ChannelStatus = ChannelStatus.ACTIVE) -> Channel:
    return Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
        config={"phone_number_id": "PN"},
        status=status,
    )


async def test_read_says_who_is_eligible(client, db_session, console_world, admin_headers) -> None:
    w = console_world["a"]
    headers, _ = await _headers(db_session, admin_headers)
    resp = await client.get(_url(w["tenant_id"]), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["eligible"] is True
    assert body["ineligible_reason"] is None
    assert body["partner"] == {"id": str(w["partner_id"]), "name": "Console Partner A"}
    assert body["whatsapp_connected"] is False
    assert body["enabled"] is False
    assert body["modules"] == []
    assert body["members"] == []


async def test_a_tenant_without_partner_is_not_eligible(client, db_session, admin_headers) -> None:
    tenant = Tenant(
        id=uuid.uuid4(), name="Directo", slug=f"d-{uuid.uuid4().hex[:6]}", plan=TenantPlan.PRO
    )
    db_session.add(tenant)
    await db_session.commit()
    headers, _ = await _headers(db_session, admin_headers)
    body = (await client.get(_url(tenant.id), headers=headers)).json()
    assert body["eligible"] is False
    assert body["ineligible_reason"] == "no_partner"
    resp = await client.put(
        _url(tenant.id), headers=headers, json={"enabled": True, "modules": ["panel"]}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "no_partner"


async def test_enabling_needs_at_least_one_module(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    headers, _ = await _headers(db_session, admin_headers)
    resp = await client.put(
        _url(w["tenant_id"]), headers=headers, json={"enabled": True, "modules": []}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "no_modules"


async def test_inbox_needs_a_connected_whatsapp(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    headers, _ = await _headers(db_session, admin_headers)
    resp = await client.put(
        _url(w["tenant_id"]), headers=headers, json={"enabled": True, "modules": ["inbox"]}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "inbox_requires_whatsapp"

    db_session.add(_whatsapp(w["tenant_id"]))
    await db_session.commit()
    resp = await client.put(
        _url(w["tenant_id"]),
        headers=headers,
        json={"enabled": True, "modules": ["usage", "inbox", "panel"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["modules"] == ["panel", "inbox", "usage"]
    assert resp.json()["whatsapp_connected"] is True


async def test_every_change_is_audited_with_the_operator(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    headers, email = await _headers(db_session, admin_headers)
    resp = await client.put(
        _url(w["tenant_id"]), headers=headers, json={"enabled": True, "modules": ["panel"]}
    )
    assert resp.status_code == 200
    row = await db_session.scalar(
        sa.select(AuditLog).where(AuditLog.action == "client_access.updated")
    )
    assert row is not None
    assert row.actor == f"operator:{email}"
    assert row.tenant_id == w["tenant_id"]
    assert row.after_json == {"enabled": True, "modules": ["panel"]}


async def test_without_an_operator_there_is_no_change(client, console_world, admin_headers) -> None:
    w = console_world["a"]
    resp = await client.put(
        _url(w["tenant_id"]), headers=admin_headers, json={"enabled": True, "modules": ["panel"]}
    )
    assert resp.status_code == 400
    bogus = {**admin_headers, "X-Operator-Id": str(uuid.uuid4())}
    resp = await client.put(
        _url(w["tenant_id"]), headers=bogus, json={"enabled": True, "modules": ["panel"]}
    )
    assert resp.status_code == 400


async def test_switching_off_closes_every_session(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    headers, _ = await _headers(db_session, admin_headers)
    email_v = f"valeria-{uuid.uuid4().hex[:10]}@minegocio.test"
    await client.put(
        _url(w["tenant_id"]), headers=headers, json={"enabled": True, "modules": ["panel"]}
    )
    invited = await client.post(
        f"/admin/tenants/{w['tenant_id']}/client-members",
        headers=headers,
        json={"email": email_v, "name": "Valeria"},
    )
    assert invited.status_code == 201, invited.text
    # Aceptar crea la cuenta y una sesión.
    token = invited.json()["accept_path"].rsplit("/", 1)[-1]
    from tests.conftest import console_headers

    svc = console_headers(user_id="console-bff", partner_id=None, service=True)
    accepted = await client.post(
        f"/console/invitations/{token}/accept",
        headers=svc,
        json={"password": "una-clave-larga-y-segura-2026"},
    )
    assert accepted.status_code == 200, accepted.text
    async with db_session.begin():
        account = await console_identity.get_by_email(db_session, email_v)
    assert account is not None
    account_id = account.id
    live = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleSession)
        .where(ConsoleSession.principal_id == account_id)
    )
    assert live == 1

    resp = await client.put(
        _url(w["tenant_id"]), headers=headers, json={"enabled": False, "modules": ["panel"]}
    )
    assert resp.status_code == 200
    db_session.expire_all()
    live = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleSession)
        .where(ConsoleSession.principal_id == account_id)
    )
    assert live == 0


async def test_the_mapping_names_the_partner(
    client, db_session, console_world, admin_headers
) -> None:
    """Un tenant en dos partners es imposible de elegir bien: se usa el del
    tenant (``tenants.partner_id``) y, si no hay, el de su único mapeo."""
    w = console_world["a"]
    headers, _ = await _headers(db_session, admin_headers)
    mapping = await db_session.scalar(
        sa.select(PartnerTenant).where(PartnerTenant.tenant_id == w["tenant_id"])
    )
    assert mapping is not None
    body = (await client.get(_url(w["tenant_id"]), headers=headers)).json()
    assert body["partner"]["id"] == str(w["partner_id"])
