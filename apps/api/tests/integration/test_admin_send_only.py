"""Spec 077 · R1, R2 y R10 — clientes de solo envío en el panel.

- El asistente crea el cliente con la marca; sin ella, como hoy.
- Marcar un cliente audita al operador y deja sus números sin agente.
- Conectar un número de un cliente de solo envío lo deja sin agente y como
  línea de avisos; en un cliente normal no cambia nada.
- La puesta en marcha se calcula con su estado real; sin membresía no hay paso.
- Los últimos envíos enmascaran el destinatario y no devuelven el código.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signup import EmbeddedSignupOrchestrator

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ApiKeyScope,
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Partner,
    PartnerApiKey,
    ServiceMembership,
    Tenant,
    TenantPlan,
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _operator(db_session: Any, admin_headers: dict[str, str]) -> tuple[dict[str, str], str]:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id)}, account.email


async def _tenant(db_session: Any, *, send_only: bool, role: str | None = None) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="Cliente",
            slug=f"c-{tid.hex[:6]}",
            plan=TenantPlan.PRO,
            send_only=send_only,
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
            config={"role": role} if role else {},
        )
    )
    await db_session.commit()
    return tid


async def _channel_configs(tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        return [dict(c or {}) for c in (await s.scalars(sa.select(Channel.config))).all()]


async def test_wizard_creates_a_send_only_client(client, admin_headers):
    slug = f"tecfin-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/admin/tenants",
        json={"slug": slug, "name": "Tecfin", "send_only": True},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["send_only"] is True


async def test_wizard_default_is_todays_client(client, admin_headers):
    resp = await client.post(
        "/admin/tenants",
        json={"slug": f"agente-{uuid.uuid4().hex[:6]}", "name": "Con agente"},
        headers=admin_headers,
    )
    assert resp.json()["send_only"] is False


async def test_marking_audits_and_silences_its_numbers(client, db_session, admin_headers):
    headers, email = await _operator(db_session, admin_headers)
    tid = await _tenant(db_session, send_only=False, role="agent")
    resp = await client.patch(
        f"/admin/tenants/{tid}/send-only", json={"send_only": True}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["send_only"] is True
    configs = await _channel_configs(tid)
    assert configs[0]["agent_enabled"] is False
    # A role the operator already set is not overwritten.
    assert configs[0]["role"] == "agent"
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        actor = await s.scalar(
            sa.select(AuditLog.actor).where(AuditLog.action == "tenant.send_only_changed")
        )
    assert actor == f"operator:{email}"


async def test_marking_needs_an_operator(client, db_session, admin_headers):
    tid = await _tenant(db_session, send_only=False)
    resp = await client.patch(
        f"/admin/tenants/{tid}/send-only", json={"send_only": True}, headers=admin_headers
    )
    assert resp.status_code == 400


def _orchestrator(session: Any) -> EmbeddedSignupOrchestrator:
    return EmbeddedSignupOrchestrator(
        session=session,
        redis=None,  # type: ignore[arg-type]
        client=None,  # type: ignore[arg-type]
        app_id="app",
        webhook_callback_url="https://x",
        webhook_verify_token="t",
    )


async def _connect(tenant_id: uuid.UUID, phone: str) -> dict[str, Any]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        channel_id = await _orchestrator(s)._upsert_channel(
            display_phone=phone,
            waba_id="waba",
            phone_number_id=f"pn-{uuid.uuid4().hex[:6]}",
            business_id="biz",
            mode="cloud_api",
            quality_rating=None,
            verified_name="Tecfin",
            messaging_tier=None,
        )
        channel = await s.get(Channel, channel_id)
        assert channel is not None
        return dict(channel.config or {})


async def test_connecting_a_number_of_a_send_only_client(db_session):
    """R2.1: sin agente y como línea de avisos, por cualquier camino de alta."""
    tid = await _tenant(db_session, send_only=True)
    config = await _connect(tid, f"+3461{tid.int % 10_000_000:07d}")
    assert config["agent_enabled"] is False
    assert config["role"] == "notifications"


async def test_connecting_a_number_of_a_normal_client_is_unchanged(db_session):
    tid = await _tenant(db_session, send_only=False)
    config = await _connect(tid, f"+3462{tid.int % 10_000_000:07d}")
    assert "agent_enabled" not in config
    assert "role" not in config


async def test_readiness_without_membership_has_three_steps(
    client, db_session, admin_headers, monkeypatch
):
    tid = await _tenant(db_session, send_only=True)

    async def _fake_fetch(_session, **_kw):
        return [
            TemplateOut(
                name="tecfin_codigo", language="es", category="AUTHENTICATION", status="APPROVED"
            ),
            TemplateOut(name="aviso", language="es", category="UTILITY", status="APPROVED"),
        ], "waba"

    monkeypatch.setattr("nexus_api.services.whatsapp_templates.fetch_templates", _fake_fetch)
    body = (await client.get(f"/admin/tenants/{tid}/send-readiness", headers=admin_headers)).json()
    assert body["channel"] == {"ok": True, "active_numbers": 1}
    assert body["template"] == {"ok": True, "approved": 1, "pending": 0, "unknown": False}
    assert body["membership"] is None
    assert body["keys"] == {"ok": False, "active": 0}


async def test_readiness_with_membership_and_meta_down(
    client, db_session, admin_headers, monkeypatch
):
    tid = await _tenant(db_session, send_only=True)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        s.add(ServiceMembership(tenant_id=tid, payer="stripe", amount_cents=4000))
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="D", slug=f"d-{pid.hex[:6]}"))
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

    async def _down(_session, **_kw):
        raise RuntimeError("meta unreachable")

    monkeypatch.setattr("nexus_api.services.whatsapp_templates.fetch_templates", _down)
    body = (await client.get(f"/admin/tenants/{tid}/send-readiness", headers=admin_headers)).json()
    assert body["membership"] == {"ok": False, "status": "pending"}
    assert body["template"]["unknown"] is True
    assert body["keys"] == {"ok": True, "active": 1}


async def test_last_sends_are_masked_and_carry_no_code(client, db_session, admin_headers):
    tid = await _tenant(db_session, send_only=True)
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        channel_id = await s.scalar(sa.select(Channel.id))
        customer = Customer(tenant_id=tid, identifier="56912345678", preferences={})
        s.add(customer)
        await s.flush()
        conv = Conversation(
            tenant_id=tid,
            channel_id=channel_id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        s.add(conv)
        await s.flush()
        s.add(
            Message(
                tenant_id=tid,
                conversation_id=conv.id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.FAILED,
                failure_code="membership_inactive",
                content="[template:tecfin_codigo]",
                tool_calls=[],
                template_payload={
                    "name": "tecfin_codigo",
                    "otp": True,
                    "params": {"body": ["482913"]},
                },
            )
        )
    resp = await client.get(f"/admin/tenants/{tid}/template-messages", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    [row] = resp.json()
    assert row["template"] == "tecfin_codigo"
    assert row["status"] == "failed"
    assert row["failure_code"] == "membership_inactive"
    assert row["to_masked"] == "+5691***5678"
    assert "482913" not in resp.text


async def test_billing_change_is_audited_with_the_operator(client, db_session, admin_headers):
    """The partner decides whose balance pays a membership: who changed it is said."""
    headers, email = await _operator(db_session, admin_headers)
    tid = await _tenant(db_session, send_only=True)
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="P", slug=f"p-{pid.hex[:6]}"))
    await db_session.commit()
    resp = await client.put(
        f"/admin/tenants/{tid}/billing", json={"partner_id": str(pid)}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tid):
        actor = await s.scalar(
            sa.select(AuditLog.actor).where(AuditLog.action == "tenant.billing_updated")
        )
    assert actor == f"operator:{email}"


async def test_a_bad_operator_header_is_refused(client, db_session, admin_headers):
    tid = await _tenant(db_session, send_only=True)
    resp = await client.put(
        f"/admin/tenants/{tid}/billing",
        json={"price_override_cents": 100},
        headers={**admin_headers, "X-Operator-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 400
