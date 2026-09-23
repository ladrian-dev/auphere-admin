"""Spec 016 (garantías 4 y 6): las cinco acciones nuevas dejan rastro y no
dejan secretos.

Cada una escribe ``audit_log`` con ``actor = console:{email}`` y un
``after_json`` que no contiene la clave de API, el código de Meta ni nada
que no deba leerse en la auditoría del partner. La URL pública de AgendaPro
es pública y sí viaja.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.signup import SignupResult

from nexus_api.api.console import whatsapp as wa_router
from nexus_api.db.models import AuditLog, Channel, ChannelStatus, ChannelType
from nexus_api.services.meta_signup_service import SignupServiceResult
from tests.unit.test_endpoint_console_agent_tools import (  # noqa: F401
    fake_composio,
    seeded_connectors,
)

pytestmark = pytest.mark.asyncio

ACTIONS = (
    "console.allocation.move",
    "console.model.update",
    "console.integration.agendapro_url",
    "console.connector.connect",
    "console.channel.connect",
)
SECRETS = ("ck_secret_016", "cs_secret_016", "META-CODE-016", "EAA-bisuat")


async def test_the_five_actions_leave_a_trail_without_secrets(
    client,
    console_world,
    db_session,
    seeded_connectors,
    fake_composio,
    monkeypatch,  # noqa: F811
) -> None:
    from tests.integration.test_console_wallet import _add_unallocated_client

    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}"
    other = "client-a-trail"
    await _add_unallocated_client(db_session, partner_id=a["partner_id"], ref=other)

    r = await client.post(
        "/console/wallet/allocations/move",
        headers=h(),
        json={"from_ref": a["ref"], "to_ref": other, "qty": 1_000},
    )
    assert r.status_code == 200, r.text
    r = await client.put(f"{base}/model", headers=h(), json={"model_id": "openai/gpt-5.6-luna"})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"{base}/integrations/agendapro/public-url",
        headers=h(),
        json={"public_url": "https://trail.site.agendapro.com/cl/x"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{base}/connectors/woocommerce/api-key",
        headers=h(),
        json={
            "secrets": {"consumer_key": SECRETS[0], "consumer_secret": SECRETS[1]},
            "endpoint_meta": {"store_url": "https://s.example"},
        },
    )
    assert r.status_code == 201, r.text

    channel_id = uuid.uuid4()

    async def _fake(**kw):
        kw["session"].add(
            Channel(
                id=channel_id,
                tenant_id=kw["tenant_id"],
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"+3460016{uuid.uuid4().int % 10000:04d}",
                config={"phone_number_id": "PN"},
                status=ChannelStatus.ACTIVE,
            )
        )
        await kw["session"].flush()
        # The real orchestrator writes its own audit row with this action.
        kw["session"].add(
            AuditLog(
                tenant_id=kw["tenant_id"],
                actor=kw["actor"],
                action=kw["audit_action"],
                target=f"channel:{channel_id}",
                after_json={"waba_id": kw["payload"].waba_id, "mode": kw["payload"].mode},
            )
        )
        return SignupServiceResult(
            result=SignupResult(
                channel_id=channel_id,
                waba_id="W1",
                phone_number_id="PN",
                display_phone_number="+34600000016",
                mode="cloud_api",
                bisuat_expires_at=None,
            ),
            audit_log_id=uuid.uuid4(),
        )

    monkeypatch.setattr(wa_router, "complete_meta_signup", _fake)
    r = await client.post(
        f"{base}/channels/whatsapp/signup",
        headers=h(),
        json={"code": SECRETS[2], "waba_id": "W1", "mode": "cloud_api"},
    )
    assert r.status_code == 201, r.text

    rows = (
        await db_session.execute(
            sa.select(
                AuditLog.action, AuditLog.actor, AuditLog.after_json, AuditLog.before_json
            ).where(AuditLog.action.in_(ACTIONS))
        )
    ).all()
    seen = {row.action for row in rows}
    assert seen == set(ACTIONS), f"missing trail for {set(ACTIONS) - seen}"
    for row in rows:
        assert row.actor.startswith("console:") and "@" in row.actor, row
        blob = json.dumps([row.after_json, row.before_json])
        for secret in SECRETS:
            assert secret not in blob, (row.action, secret)
    # And every one of them renders in both languages from the vocabulary.
    vocab = (await client.get("/console/audit/vocabulary?lang=es", headers=h())).json()
    assert set(ACTIONS) <= {e["action"] for e in vocab["entries"]}
