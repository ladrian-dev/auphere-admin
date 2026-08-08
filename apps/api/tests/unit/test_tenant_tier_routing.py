"""WP-10: inbound routing by tenant tier.

A ``priority`` tenant's messages go to ``nexus:inbound:priority`` (its own
runner pool); everyone else lands on ``nexus:inbound:standard``. The tier
lookup is cached and fail-safe — any lookup problem degrades to standard,
never to a dropped message.
"""

from __future__ import annotations

import json
import uuid

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy import text

from nexus_api.core.streams import (
    INBOUND_STREAM_PRIORITY,
    INBOUND_STREAM_STANDARD,
    stream_for_tier,
)
from nexus_api.core.tenant_resolver import resolve_tenant_tier

META_APP_SECRET = "dev-meta-app-secret-change-me"


def test_stream_for_tier_mapping() -> None:
    assert stream_for_tier("priority") == INBOUND_STREAM_PRIORITY
    assert stream_for_tier("standard") == INBOUND_STREAM_STANDARD
    # Fail-safe: unknown or missing tier is standard, never an error.
    assert stream_for_tier(None) == INBOUND_STREAM_STANDARD
    assert stream_for_tier("weird") == INBOUND_STREAM_STANDARD


@pytest.mark.asyncio
async def test_resolve_tenant_tier_reads_and_caches(db_session, fake_redis, seed_tenants) -> None:
    tenant_id = seed_tenants["a"]
    assert await resolve_tenant_tier(db_session, fake_redis, tenant_id) == "standard"

    await db_session.execute(
        text("UPDATE tenants SET tier = 'priority' WHERE id = :tid"),
        {"tid": str(tenant_id)},
    )
    await db_session.commit()
    # Cached: still standard until the TTL or an explicit invalidation.
    assert await resolve_tenant_tier(db_session, fake_redis, tenant_id) == "standard"

    from nexus_api.core.tenant_resolver import invalidate_tenant_tier_cache

    await invalidate_tenant_tier_cache(fake_redis, tenant_id)
    assert await resolve_tenant_tier(db_session, fake_redis, tenant_id) == "priority"


@pytest.mark.asyncio
async def test_resolve_tenant_tier_fail_safe(fake_redis) -> None:
    class _BoomSession:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")

    tier = await resolve_tenant_tier(_BoomSession(), fake_redis, uuid.uuid4())
    assert tier == "standard"


@pytest.mark.asyncio
async def test_priority_tenant_routes_to_priority_stream(
    client, db_session, fake_redis, seed_tenants
) -> None:
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    tenant_id = seed_tenants["a"]
    business_phone = "+56988887777"
    sender = "56933334444"

    async with db_session.begin():
        await db_session.execute(
            text("UPDATE tenants SET tier = 'priority' WHERE id = :tid"),
            {"tid": str(tenant_id)},
        )
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=business_phone,
                status=ChannelStatus.ACTIVE,
                config={"waba_id": "WABA-TIER", "phone_number_id": "PN-TIER"},
            )
        )

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-TIER",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business_phone.lstrip("+"),
                                "phone_number_id": "PN-TIER",
                            },
                            "contacts": [{"profile": {"name": "VIP"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": f"wamid.tier-{uuid.uuid4().hex[:8]}",
                                    "timestamp": "1716300000",
                                    "type": "text",
                                    "text": {"body": "hola prioridad"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    r = await client.post(
        "/webhook/meta",
        content=body,
        headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
    )
    assert r.status_code == 200, r.text

    priority_entries = await fake_redis.xrange(INBOUND_STREAM_PRIORITY, count=10)
    standard_entries = await fake_redis.xrange(INBOUND_STREAM_STANDARD, count=10)
    assert len(priority_entries) == 1
    assert standard_entries == []
