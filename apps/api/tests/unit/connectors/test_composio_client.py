"""Unit tests for the Composio client adapter — fake client + webhook verify."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest

from nexus_api.services.connectors.composio_client import (
    ComposioAuthExpired,
    ComposioError,
    ComposioNotFound,
    ComposioTool,
    ComposioUnavailable,
    FakeComposioClient,
    verify_composio_webhook,
)

# ── FakeComposioClient ──────────────────────────────────────────────────────


@pytest.fixture
def composio() -> FakeComposioClient:
    c = FakeComposioClient()
    c.register_tools(
        "googlecalendar",
        [
            ComposioTool(
                slug="GOOGLECALENDAR_LIST_EVENTS",
                description="List calendar events",
                input_schema={"type": "object"},
            ),
            ComposioTool(
                slug="GOOGLECALENDAR_CREATE_EVENT",
                description="Create an event",
                input_schema={"type": "object"},
            ),
        ],
    )
    return c


@pytest.mark.asyncio
async def test_link_creates_pending_connection(composio: FakeComposioClient) -> None:
    req = await composio.link_account(
        user_id="tenant_test",
        auth_config_id="ac_test",
        callback_url="https://api.example.com/cb",
    )
    assert req.connection_id.startswith("conn_fake_")
    assert "https://" in req.redirect_url
    acc = await composio.get_account(req.connection_id)
    assert acc.status == "PENDING"


@pytest.mark.asyncio
async def test_force_connect_then_execute(
    composio: FakeComposioClient,
) -> None:
    req = await composio.link_account(user_id="tenant_a", auth_config_id="ac")
    composio.force_connect(
        connection_id=req.connection_id,
        user_id="tenant_a",
        toolkit="googlecalendar",
        scopes=["calendar.readonly"],
    )
    result = await composio.execute_tool(
        tool_slug="GOOGLECALENDAR_LIST_EVENTS",
        user_id="tenant_a",
        connection_id=req.connection_id,
        arguments={"max_results": 5},
    )
    assert result.error is None
    assert result.data["ok"] is True


@pytest.mark.asyncio
async def test_cross_tenant_execute_rejected(
    composio: FakeComposioClient,
) -> None:
    """Critical isolation guard: the fake mirrors the real Composio's
    contract that user_id passed to execute MUST match the connection's
    user_id."""
    composio.force_connect(
        connection_id="conn_A",
        user_id="tenant_A",
        toolkit="googlecalendar",
    )
    with pytest.raises(ComposioError, match="user_id mismatch"):
        await composio.execute_tool(
            tool_slug="GOOGLECALENDAR_LIST_EVENTS",
            user_id="tenant_B",
            connection_id="conn_A",
            arguments={},
        )


@pytest.mark.asyncio
async def test_unknown_connection_raises_not_found(
    composio: FakeComposioClient,
) -> None:
    with pytest.raises(ComposioNotFound):
        await composio.get_account("conn_does_not_exist")


@pytest.mark.asyncio
async def test_auth_expired_simulation(composio: FakeComposioClient) -> None:
    composio.force_connect(connection_id="conn_E", user_id="tenant_x", toolkit="googlecalendar")
    composio.simulate_auth_expired_for.add("conn_E")
    with pytest.raises(ComposioAuthExpired):
        await composio.get_account("conn_E")


@pytest.mark.asyncio
async def test_unavailable_simulation(composio: FakeComposioClient) -> None:
    composio.simulate_unavailable = True
    with pytest.raises(ComposioUnavailable):
        await composio.link_account(user_id="x", auth_config_id="x")


@pytest.mark.asyncio
async def test_list_tools_returns_registered(
    composio: FakeComposioClient,
) -> None:
    tools = await composio.list_tools(user_id="tenant_a", toolkit="googlecalendar")
    slugs = [t.slug for t in tools]
    assert "GOOGLECALENDAR_LIST_EVENTS" in slugs
    assert "GOOGLECALENDAR_CREATE_EVENT" in slugs


@pytest.mark.asyncio
async def test_revoke_removes_connection(composio: FakeComposioClient) -> None:
    composio.force_connect(connection_id="conn_R", user_id="x", toolkit="googlecalendar")
    await composio.revoke_account("conn_R")
    with pytest.raises(ComposioNotFound):
        await composio.get_account("conn_R")


@pytest.mark.asyncio
async def test_find_auth_config_id_happy(composio: FakeComposioClient) -> None:
    composio.register_auth_config("googlecalendar", "ac_abc123")
    ac_id = await composio.find_auth_config_id("googlecalendar")
    assert ac_id == "ac_abc123"


@pytest.mark.asyncio
async def test_find_auth_config_id_missing(composio: FakeComposioClient) -> None:
    from nexus_api.services.connectors.composio_client import (
        ComposioAuthConfigMissing,
    )

    with pytest.raises(ComposioAuthConfigMissing, match="no auth_config"):
        await composio.find_auth_config_id("googlecalendar")


@pytest.mark.asyncio
async def test_find_auth_config_id_ambiguous(composio: FakeComposioClient) -> None:
    from nexus_api.services.connectors.composio_client import (
        ComposioAuthConfigAmbiguous,
    )

    composio.register_auth_config("googlecalendar", "ac_one")
    composio.register_auth_config("googlecalendar", "ac_two")
    with pytest.raises(ComposioAuthConfigAmbiguous, match="2 auth_configs"):
        await composio.find_auth_config_id("googlecalendar")


@pytest.mark.asyncio
async def test_find_auth_config_id_case_insensitive(
    composio: FakeComposioClient,
) -> None:
    composio.register_auth_config("GoogleCalendar", "ac_x")
    ac_id = await composio.find_auth_config_id("googlecalendar")
    assert ac_id == "ac_x"


@pytest.mark.asyncio
async def test_execute_log_records_calls(composio: FakeComposioClient) -> None:
    composio.force_connect(connection_id="c1", user_id="u1", toolkit="googlecalendar")
    await composio.execute_tool(
        tool_slug="GOOGLECALENDAR_LIST_EVENTS",
        user_id="u1",
        connection_id="c1",
        arguments={"q": "today"},
    )
    log = composio.execute_log
    assert len(log) == 1
    assert log[0]["user_id"] == "u1"
    assert log[0]["arguments"] == {"q": "today"}


# ── webhook signature verification ─────────────────────────────────────────


def _build_sig(secret: str, wid: str, ts: str, body: str) -> str:
    return base64.b64encode(
        hmac.new(secret.encode(), f"{wid}.{ts}.{body}".encode(), hashlib.sha256).digest()
    ).decode()


def test_webhook_signature_valid() -> None:
    secret = "whsec_test"
    ts = str(int(time.time()))
    body = '{"x":1}'
    wid = "msg_001"
    sig = _build_sig(secret, wid, ts, body)
    # Both with and without the v1, prefix must work.
    verify_composio_webhook(
        webhook_id=wid,
        webhook_timestamp=ts,
        body=body,
        signature_header=f"v1,{sig}",
        secret=secret,
    )
    verify_composio_webhook(
        webhook_id=wid,
        webhook_timestamp=ts,
        body=body,
        signature_header=sig,
        secret=secret,
    )


def test_webhook_signature_tamper_rejected() -> None:
    secret = "whsec_test"
    ts = str(int(time.time()))
    body = '{"x":1}'
    wid = "m"
    sig = _build_sig(secret, wid, ts, body)
    with pytest.raises(ValueError, match="signature mismatch"):
        verify_composio_webhook(
            webhook_id=wid,
            webhook_timestamp=ts,
            body=body + "X",
            signature_header=f"v1,{sig}",
            secret=secret,
        )


def test_webhook_replay_window() -> None:
    secret = "whsec_test"
    ts = str(int(time.time()) - 1000)  # 1000s in the past
    body = "{}"
    wid = "m"
    sig = _build_sig(secret, wid, ts, body)
    with pytest.raises(ValueError, match="out of window"):
        verify_composio_webhook(
            webhook_id=wid,
            webhook_timestamp=ts,
            body=body,
            signature_header=sig,
            secret=secret,
        )


def test_webhook_missing_headers() -> None:
    with pytest.raises(ValueError, match="headers missing"):
        verify_composio_webhook(
            webhook_id="",
            webhook_timestamp="100",
            body="",
            signature_header="x",
            secret="s",
        )


def test_webhook_empty_secret() -> None:
    with pytest.raises(ValueError, match="secret is empty"):
        verify_composio_webhook(
            webhook_id="m",
            webhook_timestamp="100",
            body="{}",
            signature_header="x",
            secret="",
        )


def test_webhook_non_int_timestamp() -> None:
    with pytest.raises(ValueError, match="not an int"):
        verify_composio_webhook(
            webhook_id="m",
            webhook_timestamp="not-a-number",
            body="{}",
            signature_header="x",
            secret="s",
        )
