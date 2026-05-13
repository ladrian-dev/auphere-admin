"""Block O — endpoint tests for /admin/tenants/:id/agent-config/test.

Uses ``set_test_agent_provider`` to inject ``FakeTestAgentProvider`` so
the suite never reaches litellm + Anthropic.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text

from nexus_api.api.admin.agent_configs import (
    get_test_agent_provider,
    set_test_agent_provider,
)
from nexus_api.services.test_agent import FakeTestAgentProvider

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fake_agent() -> AsyncIterator[FakeTestAgentProvider]:
    provider = FakeTestAgentProvider()
    set_test_agent_provider(provider)
    try:
        yield provider
    finally:
        set_test_agent_provider(None)


async def _seed_active_config(
    db_session,
    tenant_id: uuid.UUID,
    *,
    version: int = 1,
    status_value: str = "active",
    tools: tuple[str, ...] = ("booking.check_availability",),
    seed_ref: str = "barbershop_v1",
) -> None:
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=version,
            status=AgentConfigStatus(status_value),
            system_prompt_rendered="Sos el asistente de prueba.",
            channels=[],
            tools=list(tools),
            policies={},
            seed_template_ref=seed_ref,
        )
    )
    await db_session.flush()


async def test_test_agent_happy_path_against_active(
    client, admin_headers, seed_tenants, db_session, fake_agent
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid, version=3, status_value="active")

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={"user_message": "hola"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version_tested"] == 3
    assert body["version_status"] == "active"
    assert body["assistant_message"] == "Hola, soy el asistente de prueba."
    assert body["planned_tool_calls"] == []
    assert body["iterations"] == 1
    assert body["model"]
    assert len(fake_agent.calls) == 1


async def test_test_agent_prefers_latest_staged_over_active(
    client, admin_headers, seed_tenants, db_session, fake_agent
) -> None:
    """If both ACTIVE and STAGED exist, the sandbox picks STAGED so the
    operator validates the draft they just saved before promoting."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid, version=1, status_value="active")
        await _seed_active_config(db_session, tid, version=2, status_value="staged")

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={"user_message": "hola"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version_tested"] == 2
    assert r.json()["version_status"] == "staged"


async def test_test_agent_explicit_version_wins(
    client, admin_headers, seed_tenants, db_session, fake_agent
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid, version=1, status_value="active")
        await _seed_active_config(db_session, tid, version=2, status_value="staged")

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={"user_message": "hola", "version": 1},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version_tested"] == 1
    assert r.json()["version_status"] == "active"


async def test_test_agent_explicit_unknown_version_returns_404(
    client, admin_headers, seed_tenants, db_session, fake_agent
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid, version=1)
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={"user_message": "hola", "version": 99},
    )
    assert r.status_code == 404


async def test_test_agent_no_config_returns_404(
    client, admin_headers, seed_tenants, fake_agent
) -> None:
    """Greenfield tenant — no agent_config yet. The endpoint must 404
    so the UI can prompt the operator to apply a seed first."""
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={"user_message": "hola"},
    )
    assert r.status_code == 404
    assert "apply a seed" in r.json()["detail"].lower()
    assert fake_agent.calls == []


async def test_test_agent_captures_tool_calls_without_dispatching(
    client, admin_headers, seed_tenants, db_session, fake_agent
) -> None:
    """The model emits a tool_use on the first call. The sandbox must
    capture it as ``planned_tool_calls`` and the response must show no
    side effect was triggered."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        # ``booking.check_availability`` is already in the migration
        # 0003 seed, so we just point the active config at it.
        await _seed_active_config(db_session, tid)

    def responder(messages, tools, call_index):
        if call_index == 0:
            return (
                "Voy a chequear disponibilidad.",
                [
                    {
                        "id": "call_001",
                        "name": "booking.check_availability",
                        "arguments": {"date": "2026-05-14"},
                    }
                ],
            )
        return ("Tenemos turnos a las 10 y a las 14.", [])

    fake_agent.responder = responder

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={"user_message": "tenés turnos mañana?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assistant_message"] == "Tenemos turnos a las 10 y a las 14."
    assert body["iterations"] == 2
    assert len(body["planned_tool_calls"]) == 1
    p = body["planned_tool_calls"][0]
    assert p["name"] == "booking.check_availability"
    assert p["arguments"] == {"date": "2026-05-14"}
    # The dry_run_result is the synthetic answer fed back to the model;
    # the operator never sees the real upstream system.
    assert "SANDBOX" in p["dry_run_result"]


async def test_test_agent_history_round_trip(
    client, admin_headers, seed_tenants, db_session, fake_agent
) -> None:
    """Multi-turn within the dialog: send the running history each
    request. The service forwards it between the system prompt and the
    new user message."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={
            "user_message": "¿y a la tarde?",
            "history": [
                {"role": "user", "content": "¿tenés algo mañana?"},
                {"role": "assistant", "content": "sí, a las 10 y 14"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    messages_sent = fake_agent.calls[0]["messages"]
    # [system, user-h, assistant-h, user-new]
    assert len(messages_sent) == 4
    assert messages_sent[1]["content"] == "¿tenés algo mañana?"
    assert messages_sent[3]["content"] == "¿y a la tarde?"


async def test_test_agent_invalid_history_role_400(
    client, admin_headers, seed_tenants, db_session, fake_agent
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={
            "user_message": "hola",
            "history": [{"role": "system", "content": "hack"}],
        },
    )
    assert r.status_code == 400
    assert "user" in r.json()["detail"].lower()


async def test_test_agent_empty_user_message_422(
    client, admin_headers, seed_tenants, fake_agent
) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        headers=admin_headers,
        json={"user_message": ""},
    )
    assert r.status_code == 422
    assert fake_agent.calls == []


async def test_test_agent_requires_auth(client, seed_tenants) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/test",
        json={"user_message": "hola"},
    )
    assert r.status_code == 401


async def test_test_agent_default_provider_is_litellm() -> None:
    from nexus_api.services.test_agent import LiteLLMTestAgentProvider

    set_test_agent_provider(None)
    try:
        provider = get_test_agent_provider()
        assert isinstance(provider, LiteLLMTestAgentProvider)
    finally:
        set_test_agent_provider(None)
