"""Partner-key broadcasts: ``/v1/partners/clients/{ref}/…``.

The server-to-server replacement for the widget surface. A partner's
backend lists the client's approved templates and sends one to N of the
client's contacts using only its secret API key — no session JWT, no
iframe, no browser.

What these tests pin down, beyond the happy path:

- the ``broadcasts`` scope is separate from ``provision`` (a provisioning
  key cannot message anyone's customers);
- the tenant always comes from ``partner_tenants``, so one partner can
  never read or send for another's client — and a broadcast id from
  another client reads as 404, not 403;
- the guards the shared service already enforced on the widget path
  (recipient cap, idempotent replay, APPROVED-only templates) apply here
  identically, because it is the same service.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import respx
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    Broadcast,
    Channel,
    ChannelStatus,
    ChannelType,
    EmbedAuditLog,
    Partner,
    PartnerApiKey,
    PartnerTenant,
    Tenant,
    TenantCredentials,
    TenantStatus,
)

pytestmark = pytest.mark.asyncio

TEMPLATE = "recordatorio_pago_vencido"

_TEMPLATE_PAYLOAD = {
    "data": [
        {
            "id": "1",
            "name": TEMPLATE,
            "language": "es",
            "category": "UTILITY",
            "status": "APPROVED",
            "components": [
                {
                    "type": "BODY",
                    "text": "Hola {{cliente}}, tienes {{monto}} pendiente desde {{fecha}}.",
                }
            ],
        },
        {
            "id": "2",
            "name": "borrador_no_aprobado",
            "language": "es",
            "category": "MARKETING",
            "status": "PENDING",
            "components": [{"type": "BODY", "text": "Hola {{cliente}}"}],
        },
    ]
}


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def _partner_with_key(
    db_session: Any,
    *,
    scopes: list[str] | None = None,
    cap: int = 250,
) -> dict[str, Any]:
    partner_id = uuid.uuid4()
    generated = generate_api_key()
    key_id = uuid.uuid4()
    db_session.add(
        Partner(
            id=partner_id,
            name="Broadcast Partner",
            slug=f"bcast-{partner_id.hex[:6]}",
            broadcast_recipient_cap=cap,
        )
    )
    db_session.add(
        PartnerApiKey(
            id=key_id,
            partner_id=partner_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=scopes if scopes is not None else ["provision", "broadcasts"],
        )
    )
    await db_session.commit()
    return {"partner_id": partner_id, "key": generated.plaintext, "key_id": key_id}


async def _client_ready_to_send(db_session: Any, world: dict[str, Any], ref: str) -> uuid.UUID:
    """A mapped client with an ACTIVE WhatsApp channel and Meta creds —
    the state a business is in right after signup completes."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name=f"Negocio {ref}",
            slug=f"bc-{tenant_id.hex[:8]}",
            status=TenantStatus.ACTIVE,
            timezone="America/Caracas",
        )
    )
    await db_session.commit()
    db_session.add(
        PartnerTenant(
            partner_id=world["partner_id"],
            external_client_ref=ref,
            tenant_id=tenant_id,
            client_name=f"Negocio {ref}",
        )
    )
    db_session.add(
        Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+58424{tenant_id.hex[:7]}",
            status=ChannelStatus.ACTIVE,
            config={"waba_id": "WABA_TEST", "phone_number_id": "PN_TEST"},
        )
    )
    db_session.add(
        TenantCredentials(
            tenant_id=tenant_id,
            integration="meta_whatsapp",
            encrypted_payload=_meta_creds_blob(),
            needs_reauth=False,
        )
    )
    await db_session.commit()
    return tenant_id


def _meta_creds_blob() -> bytes:
    """Meta credentials in the shape the signup flow persists. The column
    type encrypts on write, so this hands over plain bytes."""
    from nexus_channels.whatsapp_meta.credentials import MetaCredentials

    return MetaCredentials(
        bisuat="EAA-test",
        waba_id="WABA_TEST",
        phone_number_id="PN_TEST",
        business_id="BIZ_TEST",
        display_phone_number="+584241112233",
        verify_token="vt",
        mode="coexistence",
    ).to_payload()


def _mock_templates(mock: respx.MockRouter) -> None:
    mock.get("/WABA_TEST/message_templates").respond(200, json=_TEMPLATE_PAYLOAD)


def _send_body(phone: str = "+584241112233", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "template_name": TEMPLATE,
        "language": "es",
        "recipients": [
            {
                "phone": phone,
                "variables": {"cliente": "Ana", "monto": "36.00", "fecha": "12/08"},
            }
        ],
    }
    body.update(extra)
    return body


# ── templates ──────────────────────────────────────────────────────────────


async def test_templates_lists_only_approved(client, db_session) -> None:
    world = await _partner_with_key(db_session)
    await _client_ready_to_send(db_session, world, "negocio-1")

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_templates(mock)
        r = await client.get(
            "/v1/partners/clients/negocio-1/templates", headers=_auth(world["key"])
        )
    assert r.status_code == 200, r.text
    names = [t["name"] for t in r.json()["templates"]]
    assert names == [TEMPLATE], "a PENDING template must never be offered"


async def test_templates_requires_broadcasts_scope(client, db_session) -> None:
    world = await _partner_with_key(db_session, scopes=["provision"])
    await _client_ready_to_send(db_session, world, "negocio-1")

    r = await client.get("/v1/partners/clients/negocio-1/templates", headers=_auth(world["key"]))
    assert r.status_code == 403
    assert "broadcasts" in r.json()["detail"]


# ── sending ────────────────────────────────────────────────────────────────


async def test_send_to_single_recipient_queues_message(client, db_session) -> None:
    world = await _partner_with_key(db_session)
    tenant_id = await _client_ready_to_send(db_session, world, "negocio-1")

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_templates(mock)
        r = await client.post(
            "/v1/partners/clients/negocio-1/broadcasts",
            json=_send_body(),
            headers=_auth(world["key"]),
        )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["accepted"] == 1
    assert body["rejected"] == []

    broadcast = await db_session.scalar(
        sa.select(Broadcast).where(Broadcast.tenant_id == tenant_id)
    )
    assert broadcast is not None
    assert broadcast.partner_id == world["partner_id"]
    assert broadcast.jti is None, "no session token on the server-to-server path"

    events = (
        await db_session.scalars(
            sa.select(EmbedAuditLog.event).where(EmbedAuditLog.tenant_id == tenant_id)
        )
    ).all()
    assert "broadcast.created" in events


async def test_send_requires_broadcasts_scope(client, db_session) -> None:
    """The whole point of the separate scope: a provisioning key must not
    be able to message a client's customers."""
    world = await _partner_with_key(db_session, scopes=["provision"])
    await _client_ready_to_send(db_session, world, "negocio-1")

    r = await client.post(
        "/v1/partners/clients/negocio-1/broadcasts",
        json=_send_body(),
        headers=_auth(world["key"]),
    )
    assert r.status_code == 403
    assert "broadcasts" in r.json()["detail"]


async def test_idempotent_replay_does_not_send_twice(client, db_session) -> None:
    world = await _partner_with_key(db_session)
    tenant_id = await _client_ready_to_send(db_session, world, "negocio-1")
    payload = _send_body(idempotency_key="factura-991")

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_templates(mock)
        first = await client.post(
            "/v1/partners/clients/negocio-1/broadcasts",
            json=payload,
            headers=_auth(world["key"]),
        )
        second = await client.post(
            "/v1/partners/clients/negocio-1/broadcasts",
            json=payload,
            headers=_auth(world["key"]),
        )
    assert first.status_code == 202
    assert second.status_code == 200, "a replay is not a new send"
    assert first.json()["broadcast_id"] == second.json()["broadcast_id"]

    count = await db_session.scalar(
        sa.select(sa.func.count()).select_from(Broadcast).where(Broadcast.tenant_id == tenant_id)
    )
    assert count == 1


async def test_recipient_cap_is_enforced(client, db_session) -> None:
    world = await _partner_with_key(db_session, cap=2)
    await _client_ready_to_send(db_session, world, "negocio-1")
    body = _send_body()
    body["recipients"] = [
        {"phone": f"+58424111{n:04d}", "variables": {"cliente": "X", "monto": "1", "fecha": "1"}}
        for n in range(3)
    ]

    # No Graph mock on purpose: the cap is checked before the template is
    # resolved, so an over-cap call must never reach Meta at all.
    r = await client.post(
        "/v1/partners/clients/negocio-1/broadcasts",
        json=body,
        headers=_auth(world["key"]),
    )
    assert r.status_code == 413


async def test_unapproved_template_is_rejected(client, db_session) -> None:
    world = await _partner_with_key(db_session)
    await _client_ready_to_send(db_session, world, "negocio-1")
    body = _send_body()
    body["template_name"] = "borrador_no_aprobado"

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_templates(mock)
        r = await client.post(
            "/v1/partners/clients/negocio-1/broadcasts",
            json=body,
            headers=_auth(world["key"]),
        )
    assert r.status_code == 422
    assert "APPROVED" in r.json()["detail"]


async def test_client_without_whatsapp_gets_409(client, db_session) -> None:
    world = await _partner_with_key(db_session)
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Sin WhatsApp",
            slug=f"bc-{tenant_id.hex[:8]}",
            status=TenantStatus.PROVISIONING,
        )
    )
    await db_session.commit()
    db_session.add(
        PartnerTenant(
            partner_id=world["partner_id"],
            external_client_ref="sin-wa",
            tenant_id=tenant_id,
            client_name="Sin WhatsApp",
        )
    )
    await db_session.commit()

    r = await client.post(
        "/v1/partners/clients/sin-wa/broadcasts",
        json=_send_body(),
        headers=_auth(world["key"]),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "whatsapp_not_connected"


# ── status + isolation ─────────────────────────────────────────────────────


async def test_status_reports_queued_recipients(client, db_session) -> None:
    world = await _partner_with_key(db_session)
    await _client_ready_to_send(db_session, world, "negocio-1")

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_templates(mock)
        sent = await client.post(
            "/v1/partners/clients/negocio-1/broadcasts",
            json=_send_body(),
            headers=_auth(world["key"]),
        )
    broadcast_id = sent.json()["broadcast_id"]

    r = await client.get(
        f"/v1/partners/clients/negocio-1/broadcasts/{broadcast_id}",
        headers=_auth(world["key"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["template_name"] == TEMPLATE
    # ``pending`` is the message row's own status right after fan-out —
    # the outbound dispatcher advances it to sent/delivered later.
    assert body["counts"] == {"pending": 1}
    assert body["recipients"][0]["status"] == "pending"


async def test_broadcast_of_another_client_is_404(client, db_session) -> None:
    """Same partner, two clients: the id of one must not resolve under
    the other. RLS makes it invisible, so it reads as 404."""
    world = await _partner_with_key(db_session)
    await _client_ready_to_send(db_session, world, "negocio-1")
    await _client_ready_to_send(db_session, world, "negocio-2")

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_templates(mock)
        sent = await client.post(
            "/v1/partners/clients/negocio-1/broadcasts",
            json=_send_body(),
            headers=_auth(world["key"]),
        )
    broadcast_id = sent.json()["broadcast_id"]

    r = await client.get(
        f"/v1/partners/clients/negocio-2/broadcasts/{broadcast_id}",
        headers=_auth(world["key"]),
    )
    assert r.status_code == 404


async def test_other_partner_cannot_use_your_client_ref(client, db_session) -> None:
    """``external_client_ref`` is only meaningful under its own partner:
    an attacker who learns a competitor's ref gets an opaque 404."""
    owner = await _partner_with_key(db_session)
    await _client_ready_to_send(db_session, owner, "negocio-1")
    intruder = await _partner_with_key(db_session)

    for path, method in (
        ("/v1/partners/clients/negocio-1/templates", "get"),
        ("/v1/partners/clients/negocio-1/broadcasts", "post"),
    ):
        call = getattr(client, method)
        r = await (
            call(path, json=_send_body(), headers=_auth(intruder["key"]))
            if method == "post"
            else call(path, headers=_auth(intruder["key"]))
        )
        assert r.status_code == 404, f"{method} {path} leaked: {r.status_code}"
