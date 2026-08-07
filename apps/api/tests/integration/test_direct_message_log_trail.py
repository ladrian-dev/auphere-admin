"""The log trail a New Air campaign run leaves behind.

Not a contract test — a readable rehearsal of the instrumentation. It
drives the four outcomes an operator actually has to tell apart from the
outside (queued / replay of a delivered send / replay of a failed send /
key collision), all of which answer 202, and asserts that the log says
which one happened.

Run it with ``-s`` to read the trail:

    uv run pytest tests/integration/test_direct_message_log_trail.py -s
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import sqlalchemy as sa
import structlog

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    ApiKeyScope,
    Channel,
    ChannelStatus,
    ChannelType,
    Message,
    Partner,
    PartnerApiKey,
    Tenant,
    TenantPlan,
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = pytest.mark.asyncio

_TEMPLATE = TemplateOut(
    id="t1",
    name="newair_ciclo_instalacion_previo",
    language="es",
    category="UTILITY",
    status="APPROVED",
    components=[{"type": "BODY", "text": "Hola {{nombre}}, el {{fecha}} se cumplen 6 meses."}],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_TEMPLATE], "waba-newair"

    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)


@pytest_asyncio.fixture
async def world(db_session):
    tenant_id, partner_id = uuid.uuid4(), uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Tenant(id=tenant_id, name="New Air", slug=f"na-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.flush()
    db_session.add(
        Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier="+56222222222",
            status=ChannelStatus.ACTIVE,
        )
    )
    db_session.add(Partner(id=partner_id, name="Auphere", slug=f"pp-{partner_id.hex[:6]}"))
    db_session.add(
        PartnerApiKey(
            partner_id=partner_id,
            tenant_id=tenant_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=[ApiKeyScope.MESSAGES_SEND.value],
        )
    )
    await db_session.commit()
    return {
        "tenant_id": tenant_id,
        "headers": {"Authorization": f"Bearer {generated.plaintext}"},
    }


def _send(idempotency_key: str, *, nombre: str = "Juan Pérez", to: str = "+56912345678"):
    return {
        "to": to,
        "template_name": "newair_ciclo_instalacion_previo",
        "language": "es",
        "variables": {"nombre": nombre, "fecha": "15/01/2026"},
        "idempotency_key": idempotency_key,
    }


async def _fail(db_session, tenant_id: uuid.UUID, message_id: uuid.UUID, code: str) -> None:
    await db_session.rollback()
    async with db_session.begin():
        await db_session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        await db_session.execute(
            sa.update(Message)
            .where(Message.id == message_id)
            .values(
                status="failed",
                attempts=3,
                failed_at=datetime.now(UTC),
                failure_code=code,
                last_error=f"MetaAPIError: code {code}",
            )
        )


async def test_campaign_run_is_readable_from_the_log_alone(client, world, db_session) -> None:
    tenant_id = world["tenant_id"]
    headers = world["headers"]

    with structlog.testing.capture_logs() as logs:
        # 1. A clean send.
        ok = await client.post("/v1/messages/template", json=_send("row-1"), headers=headers)
        # 2. Row 2 sends, then fails at Meta, then the automation retries.
        failing = await client.post("/v1/messages/template", json=_send("row-2"), headers=headers)

    await _fail(db_session, tenant_id, uuid.UUID(failing.json()["message_id"]), "131026")

    with structlog.testing.capture_logs() as retry_logs:
        retried = await client.post("/v1/messages/template", json=_send("row-2"), headers=headers)
        # 3. Two different customers under one key — the caller's key is
        #    derived from tipo+telefono+fecha and two rows collided.
        collision = await client.post(
            "/v1/messages/template",
            json=_send("row-1", nombre="Marta Silva", to="+56987654321"),
            headers=headers,
        )

    events = [entry["event"] for entry in logs]
    retry_events = [entry["event"] for entry in retry_logs]

    print("\n--- first run ---")
    for entry in logs:
        print(f"  {entry['log_level']:<7} {entry['event']}")
    print("--- retry run ---")
    for entry in retry_logs:
        print(f"  {entry['log_level']:<7} {entry['event']}")

    # A clean send is traceable end to end inside the API.
    assert ok.status_code == 202
    assert events.count("direct_message.received") == 2
    assert "direct_message.channel_resolved" in events
    assert "direct_message.template_resolved" in events
    assert events.count("direct_message.queued") == 2
    assert events.count("api.messages.template.response") == 2

    # The retry of a failed send is loud, and re-queues.
    assert retried.json()["duplicate"] is False
    assert retried.json()["status"] == "pending"
    assert "direct_message.replay_of_failed_send" in retry_events
    assert "direct_message.requeued" in retry_events
    failed_replay = next(
        e for e in retry_logs if e["event"] == "direct_message.replay_of_failed_send"
    )
    assert failed_replay["prior_failure_code"] == "131026"
    assert failed_replay["prior_attempts"] == 3

    # The collision is answered 202/duplicate but recorded as a WARNING
    # naming both messages — otherwise a dropped customer is invisible.
    assert collision.json()["duplicate"] is True
    assert "direct_message.idempotency_collision" in retry_events
    collided = next(e for e in retry_logs if e["event"] == "direct_message.idempotency_collision")
    assert collided["log_level"] == "warning"
    assert collided["variables_differ"] is True

    # No log line carries a phone number in the clear.
    for entry in [*logs, *retry_logs]:
        assert "56912345678" not in str(entry), entry
