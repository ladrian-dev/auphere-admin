"""Block N — endpoint tests for /admin/tenants/:id/agent-config/improve-prompt.

The FakePromptImproverProvider is injected via ``set_prompt_improver_provider``
so we don't reach litellm + Anthropic. Each test resets the singleton in
its own fixture to avoid bleed between tests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text

from nexus_api.api.admin.agent_configs import (
    get_prompt_improver_provider,
    set_prompt_improver_provider,
)
from nexus_api.services.prompt_improver import FakePromptImproverProvider

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fake_improver() -> AsyncIterator[FakePromptImproverProvider]:
    """Replace the production singleton with a fresh Fake for each test;
    restore on teardown so the next test starts clean."""
    provider = FakePromptImproverProvider()
    set_prompt_improver_provider(provider)
    try:
        yield provider
    finally:
        set_prompt_improver_provider(None)


async def _seed_active_config(
    db_session,
    tenant_id: uuid.UUID,
    *,
    seed_ref: str = "barbershop_v1",
    tools: tuple[str, ...] = ("booking.create_appointment",),
) -> None:
    """Insert a minimal active agent_config inside the tenant's RLS scope."""
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"),
        {"t": str(tenant_id)},
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Sos el asistente de prueba.",
            channels=[],
            tools=list(tools),
            policies={"agent": {"name": "Alex"}},
            seed_template_ref=seed_ref,
        )
    )
    await db_session.flush()


async def test_improve_prompt_happy_path(
    client, admin_headers, seed_tenants, db_session, fake_improver
) -> None:
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(db_session, tid)

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": "Sos el asistente de Test.", "mode": "general"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["improved_prompt"].strip()
    assert isinstance(body["summary_of_changes"], list)
    assert body["mode"] == "general"
    assert body["meta_prompt_version"] == "n.v1"
    assert body["model"] == "anthropic/claude-sonnet-4-6"
    assert body["latency_ms"] >= 0
    # The fake provider records the call so we can inspect the
    # tenant_id + model that the endpoint passed down.
    assert len(fake_improver.calls) == 1
    call = fake_improver.calls[0]
    assert call["tenant_id"] == tid
    assert call["model"] == "anthropic/claude-sonnet-4-6"


async def test_improve_prompt_injects_tenant_context_into_metaprompt(
    client, admin_headers, seed_tenants, db_session, fake_improver
) -> None:
    """The system message must carry meta-prompt v1 + cache_control, and
    the user message must mention the tenant + the actual whitelisted
    tools. This is the difference from a generic prompt improver."""
    tid = seed_tenants["a"]
    async with db_session.begin():
        await _seed_active_config(
            db_session, tid, tools=("booking.create_appointment", "client.get_history")
        )

    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": "hola"},
    )
    assert r.status_code == 200, r.text

    messages = fake_improver.calls[0]["messages"]
    sys_block = messages[0]["content"][0]
    assert sys_block["cache_control"] == {"type": "ephemeral"}
    assert "n.v1" in sys_block["text"]

    user_text = messages[1]["content"]
    assert "Tenant A" in user_text  # seed_tenants fixture creates "Tenant A"
    assert "barbershop_v1" in user_text
    assert "booking.create_appointment" in user_text
    assert "client.get_history" in user_text


async def test_improve_prompt_works_without_active_config(
    client, admin_headers, seed_tenants, fake_improver
) -> None:
    """Greenfield case: the operator hasn't applied a seed yet. The
    improver should still run, treating the use_case as 'generic' and
    available_tools as empty."""
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": "Sos el asistente."},
    )
    assert r.status_code == 200, r.text
    user_text = fake_improver.calls[0]["messages"][1]["content"]
    assert "generic" in user_text


async def test_improve_prompt_rejects_unknown_mode(
    client, admin_headers, seed_tenants, fake_improver
) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": "hola", "mode": "hallucinate"},
    )
    assert r.status_code == 400, r.text
    assert "unsupported mode" in r.json()["detail"]
    assert fake_improver.calls == []


async def test_improve_prompt_rejects_empty_prompt(
    client, admin_headers, seed_tenants, fake_improver
) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": ""},
    )
    # Pydantic min_length=1 catches the empty string before our service.
    assert r.status_code == 422
    assert fake_improver.calls == []


async def test_improve_prompt_413_on_oversize_payload(
    client, admin_headers, seed_tenants, fake_improver
) -> None:
    tid = seed_tenants["a"]
    huge = "x" * 21_000  # default cap is 20_000
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": huge},
    )
    assert r.status_code == 413, r.text
    assert fake_improver.calls == []


async def test_improve_prompt_502_on_malformed_response(
    client, admin_headers, seed_tenants, fake_improver
) -> None:
    """If the LLM returns text we can't parse, surface a 502 with copy
    the operator can act on (retry / switch mode). The raw response is
    NOT exposed in the API body for safety — it lands in logs."""
    fake_improver.responder = lambda messages, mode: "lo siento, no puedo."
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": "hola"},
    )
    assert r.status_code == 502, r.text
    assert "malformed" in r.json()["detail"].lower()


async def test_improve_prompt_unknown_tenant_returns_404(
    client, admin_headers, fake_improver
) -> None:
    r = await client.post(
        f"/admin/tenants/{uuid.uuid4()}/agent-config/improve-prompt",
        headers=admin_headers,
        json={"prompt": "hola"},
    )
    assert r.status_code == 404
    assert fake_improver.calls == []


async def test_improve_prompt_requires_auth(client, seed_tenants) -> None:
    tid = seed_tenants["a"]
    r = await client.post(
        f"/admin/tenants/{tid}/agent-config/improve-prompt",
        json={"prompt": "hola"},
    )
    assert r.status_code == 401


async def test_improver_default_singleton_is_litellm() -> None:
    """The DI hook returns the LiteLLM-backed provider by default in
    production. Tests pin the Fake via set_prompt_improver_provider; this
    test resets the singleton, then re-resolves and confirms the type."""
    set_prompt_improver_provider(None)
    try:
        from nexus_api.services.prompt_improver import LiteLLMPromptImproverProvider

        provider = get_prompt_improver_provider()
        assert isinstance(provider, LiteLLMPromptImproverProvider)
    finally:
        set_prompt_improver_provider(None)
