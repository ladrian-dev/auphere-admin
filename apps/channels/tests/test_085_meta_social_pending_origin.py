"""Spec 085 (requisito 7.3) — a pending account choice knows where it began.

The console and each owner link start the same connection
(:class:`MetaSocialConnector`). When Meta returns several accounts, the
choice waits in Redis; only the place that began it — the console, or that
one link — may complete it. Anyone else gets ``pending_expired`` and nothing
connects.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import fakeredis.aioredis
import pytest
from nexus_api.core.tenant_context import tenant_context

from nexus_channels.meta_social.connect import (
    _PENDING_KEY,
    ConnectableAccount,
    ConnectOutcome,
    MetaSocialConnector,
    _fernet,
)
from nexus_channels.meta_social.exceptions import MetaSocialConnectError

pytestmark = pytest.mark.asyncio

TENANT = uuid.uuid4()


class _TwoAccounts:
    """Meta granting two Instagram accounts: the connection has to ask."""

    async def exchange_code(self, *, app_id: str, code: str) -> dict[str, Any]:
        return {"access_token": "SUAT"}

    async def client_business_id(self, *, access_token: str) -> str:
        return "BIZ"

    async def assigned_instagram_accounts(self, *, access_token: str) -> list[dict[str, Any]]:
        return [{"id": "IG-1", "username": "uno"}, {"id": "IG-2", "username": "dos"}]

    async def account_profile(self, *, object_id: str, access_token: str, fields: str) -> Any:
        return {"id": object_id, "username": f"user{object_id}", "name": f"Cuenta {object_id}"}


def _connector(redis: Any, connected: list[str]) -> MetaSocialConnector:
    connector = MetaSocialConnector(
        session=None,  # type: ignore[arg-type]
        redis=redis,
        client=_TwoAccounts(),  # type: ignore[arg-type]
        app_id="APP",
    )

    async def _connect(kind: str, account: ConnectableAccount, creds: Any) -> ConnectOutcome:
        connected.append(account.id)
        return ConnectOutcome(status="connected", channel_id=uuid.uuid4(), account=account)

    connector._connect = _connect  # type: ignore[method-assign]
    return connector


async def _begin(connector: MetaSocialConnector, **origin: str) -> str:
    outcome = await connector.begin(kind="instagram", code="CODE", **origin)
    assert outcome.status == "choose" and outcome.nonce
    return outcome.nonce


async def test_a_link_choice_is_not_completed_by_the_console_nor_another_link() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    connected: list[str] = []
    connector = _connector(redis, connected)
    with tenant_context(TENANT):
        nonce = await _begin(connector, origin="link:A")
        for other in ({}, {"origin": "console"}, {"origin": "link:B"}):
            with pytest.raises(MetaSocialConnectError) as refused:
                await connector.complete(kind="instagram", nonce=nonce, account_id="IG-2", **other)
            assert refused.value.reason == "pending_expired"
        assert connected == [], "nothing connects"

        done = await connector.complete(
            kind="instagram", nonce=nonce, account_id="IG-2", origin="link:A"
        )
    assert done.status == "connected"
    assert connected == ["IG-2"]


async def test_a_console_choice_is_not_completed_from_a_link() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    connected: list[str] = []
    connector = _connector(redis, connected)
    with tenant_context(TENANT):
        nonce = await _begin(connector)
        with pytest.raises(MetaSocialConnectError) as refused:
            await connector.complete(
                kind="instagram", nonce=nonce, account_id="IG-1", origin="link:A"
            )
        assert refused.value.reason == "pending_expired"
        done = await connector.complete(kind="instagram", nonce=nonce, account_id="IG-1")
    assert done.status == "connected" and connected == ["IG-1"]


async def test_a_choice_stored_before_the_origin_existed_belongs_to_the_console() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    connected: list[str] = []
    connector = _connector(redis, connected)
    nonce = "legacy-nonce-0001"
    stash = {
        "kind": "instagram",
        "token": "SUAT",
        "business_id": "BIZ",
        "page_tokens": {},
        "accounts": [{"id": "IG-1", "name": "Uno", "username": "uno", "picture_url": None}],
    }
    await redis.set(
        _PENDING_KEY.format(tenant=TENANT, nonce=nonce),
        _fernet().encrypt(json.dumps(stash).encode()),
    )
    with tenant_context(TENANT):
        with pytest.raises(MetaSocialConnectError) as refused:
            await connector.complete(
                kind="instagram", nonce=nonce, account_id="IG-1", origin="link:A"
            )
        assert refused.value.reason == "pending_expired"
        done = await connector.complete(
            kind="instagram", nonce=nonce, account_id="IG-1", origin="console"
        )
    assert done.status == "connected" and connected == ["IG-1"]
