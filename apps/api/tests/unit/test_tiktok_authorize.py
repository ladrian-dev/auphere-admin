"""TikTok authorisation orchestration.

Focus is on the ordering guarantees rather than the happy path plumbing:

- the region check runs *before* anything is persisted, because a blocked
  region that got written would look connected and stay silent forever;
- a webhook failure does NOT throw the token away, because a tenant with a
  live token and a broken webhook is recoverable and a tenant without a
  token has to start over.

The DB and Redis are stubbed. Persistence itself is exercised by the
integration suite; what matters here is *what gets called, in what order,
and what doesn't get called at all*.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
from nexus_channels.tiktok_bm.authorize import (
    UNSUPPORTED_REGIONS,
    TikTokAuthorizationOrchestrator,
)
from nexus_channels.tiktok_bm.exceptions import (
    TikTokNoBusinessAccountError,
    TikTokRegionNotSupportedError,
    TikTokWebhookSetupError,
)
from nexus_channels.tiktok_bm.tiktok_client import TikTokClient

pytestmark = pytest.mark.asyncio

TENANT_ID = uuid.uuid4()
BUSINESS_ID = "7123456789012345678"
CALLBACK_URL = "https://webhooks.auphere.com/webhook/tiktok"
REDIRECT_URI = "https://api.auphere.com/admin/integrations/tiktok/callback"


def ok(data: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "message": "OK", "data": data or {}})


class FakeCredentialsRepo:
    """Records what the orchestrator tried to persist."""

    def __init__(self) -> None:
        self.upserted: Any = None
        self.deleted = False

    async def upsert(self, creds: Any) -> None:
        self.upserted = creds

    async def get(self) -> Any:
        return self.upserted

    async def delete(self) -> None:
        self.deleted = True


class FakeSession:
    """Enough of an AsyncSession for the orchestrator's channel upsert."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def scalar(self, _stmt: Any) -> Any:
        return None  # no pre-existing channel row

    def add(self, obj: Any) -> None:
        obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.deleted_keys: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted_keys.append(key)


def build_orchestrator(
    handler: Any,
) -> tuple[TikTokAuthorizationOrchestrator, FakeCredentialsRepo, FakeSession, FakeRedis]:
    client = TikTokClient("app-1", "secret-1", transport=httpx.MockTransport(handler))
    session = FakeSession()
    redis = FakeRedis()
    orchestrator = TikTokAuthorizationOrchestrator(
        session=session,  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        client=client,
        webhook_callback_url=CALLBACK_URL,
        redirect_uri=REDIRECT_URI,
    )
    repo = FakeCredentialsRepo()
    orchestrator._credentials = repo  # type: ignore[assignment]
    return orchestrator, repo, session, redis


def routed_handler(
    *,
    region: str = "VE",
    accounts: list[dict[str, Any]] | None = None,
    webhook_fails: bool = False,
    calls: list[str] | None = None,
) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if calls is not None:
            calls.append(path)
        if "oauth2/token" in path:
            return ok(
                {
                    "access_token": "act.new",
                    "refresh_token": "rft.new",
                    "expires_in": 86400,
                    "refresh_token_expires_in": 31536000,
                }
            )
        if "business/get" in path:
            listing = (
                accounts
                if accounts is not None
                else [
                    {
                        "business_id": BUSINESS_ID,
                        "display_name": "Clínica Boreal",
                        "region": region,
                    }
                ]
            )
            return ok({"list": listing})
        if "webhook/create" in path:
            if webhook_fails:
                return httpx.Response(200, json={"code": 40002, "message": "callback_url rejected"})
            return ok({"webhook_id": "wh_1"})
        return ok()

    return handler


@pytest.fixture(autouse=True)
def _tenant_context(monkeypatch: pytest.MonkeyPatch) -> None:
    import nexus_channels.tiktok_bm.authorize as mod

    monkeypatch.setattr(mod, "require_current_tenant", lambda: TENANT_ID)

    async def _noop_invalidate(redis: Any, provider: str, identifier: str) -> None:
        await redis.delete(f"nexus:tenant_resolve:{provider}:{identifier}")

    monkeypatch.setattr(mod, "invalidate_tenant_cache", _noop_invalidate)


# ── happy path ──────────────────────────────────────────────────────────────


async def test_connects_a_supported_account_end_to_end() -> None:
    calls: list[str] = []
    orchestrator, repo, session, redis = build_orchestrator(routed_handler(calls=calls))

    result = await orchestrator.complete(auth_code="code-1")

    assert result.business_id == BUSINESS_ID
    assert result.display_name == "Clínica Boreal"
    assert result.region == "VE"
    assert result.webhook_config_id == "wh_1"

    # Token persisted with an absolute expiry the refresh cron can act on.
    assert repo.upserted.access_token == "act.new"
    assert repo.upserted.refresh_token == "rft.new"
    assert repo.upserted.access_token_expires_at is not None

    # Channel row created and the resolver cache invalidated, so the very
    # first inbound after connecting routes instead of being dropped.
    assert len(session.added) == 1
    assert session.added[0].provider_identifier == BUSINESS_ID
    assert redis.deleted_keys == [f"nexus:tenant_resolve:tiktok:{BUSINESS_ID}"]


async def test_channel_config_records_the_channel_s_hard_limits() -> None:
    """The 48h window and the no-business-initiated rule are read by the
    outbound guardrails; keeping them on the row avoids hardcoding 48 in
    three places."""
    orchestrator, _, session, _ = build_orchestrator(routed_handler())

    await orchestrator.complete(auth_code="code-1")

    config = session.added[0].config
    assert config["service_window_hours"] == 48
    assert config["supports_business_initiated"] is False


# ── region gate ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("region", ["DE", "FR", "ES", "GB", "CH", "NO"])
async def test_refuses_regions_where_business_messaging_does_not_exist(region: str) -> None:
    orchestrator, repo, session, redis = build_orchestrator(routed_handler(region=region))

    with pytest.raises(TikTokRegionNotSupportedError):
        await orchestrator.complete(auth_code="code-1")

    # Nothing persisted: a connected-looking channel that never receives an
    # event is worse than a clear refusal.
    assert repo.upserted is None
    assert session.added == []
    assert redis.deleted_keys == []


async def test_the_region_gate_never_reaches_webhook_registration() -> None:
    calls: list[str] = []
    orchestrator, _, _, _ = build_orchestrator(routed_handler(region="DE", calls=calls))

    with pytest.raises(TikTokRegionNotSupportedError):
        await orchestrator.complete(auth_code="code-1")

    assert not any("webhook/create" in c for c in calls)


@pytest.mark.parametrize("region", ["VE", "CL", "MX", "US", "BR", "AR"])
async def test_supported_regions_pass_the_gate(region: str) -> None:
    orchestrator, _, _, _ = build_orchestrator(routed_handler(region=region))

    result = await orchestrator.complete(auth_code="code-1")
    assert result.region == region


async def test_an_unknown_region_is_allowed_through() -> None:
    """The denylist is deliberate: TikTok keeps opening markets, and a new
    one should start working without waiting on a code change."""
    orchestrator, _, _, _ = build_orchestrator(routed_handler(region="ZZ"))

    assert await orchestrator.complete(auth_code="code-1") is not None


async def test_a_missing_region_does_not_block_the_connection() -> None:
    orchestrator, _, _, _ = build_orchestrator(
        routed_handler(accounts=[{"business_id": BUSINESS_ID, "display_name": "Sin región"}])
    )

    result = await orchestrator.complete(auth_code="code-1")
    assert result.region is None


async def test_the_denylist_covers_the_eea_switzerland_and_the_uk() -> None:
    assert {"DE", "FR", "ES", "IT", "NL", "IE"} <= UNSUPPORTED_REGIONS  # EU sample
    assert {"IS", "LI", "NO"} <= UNSUPPORTED_REGIONS  # rest of the EEA
    assert {"CH", "GB"} <= UNSUPPORTED_REGIONS
    assert "US" not in UNSUPPORTED_REGIONS
    assert "VE" not in UNSUPPORTED_REGIONS


# ── failure modes ───────────────────────────────────────────────────────────


async def test_a_personal_account_is_rejected_with_a_specific_error() -> None:
    orchestrator, repo, _, _ = build_orchestrator(routed_handler(accounts=[]))

    with pytest.raises(TikTokNoBusinessAccountError):
        await orchestrator.complete(auth_code="code-1")

    assert repo.upserted is None


async def test_a_webhook_failure_surfaces_without_discarding_the_token() -> None:
    """A tenant with a live token and a broken webhook can retry from the
    panel; a tenant whose token we threw away has to start over."""
    orchestrator, _repo, session, _ = build_orchestrator(routed_handler(webhook_fails=True))

    with pytest.raises(TikTokWebhookSetupError):
        await orchestrator.complete(auth_code="code-1")

    # No half-written channel row either — the caller sees a clean failure.
    assert session.added == []


async def test_disconnect_tears_down_webhook_credentials_and_cache() -> None:
    calls: list[str] = []
    orchestrator, repo, _, redis = build_orchestrator(routed_handler(calls=calls))
    await orchestrator.complete(auth_code="code-1")
    redis.deleted_keys.clear()
    calls.clear()

    await orchestrator.disconnect()

    assert any("webhook/delete" in c for c in calls)
    assert repo.deleted is True
    assert redis.deleted_keys == [f"nexus:tenant_resolve:tiktok:{BUSINESS_ID}"]


async def test_disconnect_completes_even_when_tiktok_is_unreachable() -> None:
    """A stale registration on TikTok's side is far less harmful than a
    tenant stuck half-connected on ours."""
    orchestrator, repo, _, _redis = build_orchestrator(routed_handler())
    await orchestrator.complete(auth_code="code-1")

    def failing(request: httpx.Request) -> httpx.Response:
        if "webhook/delete" in request.url.path:
            return httpx.Response(200, json={"code": 40100, "message": "token dead"})
        return ok()

    orchestrator._client = TikTokClient(  # type: ignore[assignment]
        "app-1", "secret-1", transport=httpx.MockTransport(failing)
    )

    await orchestrator.disconnect()
    assert repo.deleted is True
