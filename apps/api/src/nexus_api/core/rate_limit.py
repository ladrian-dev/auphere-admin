"""Per-partner token-bucket rate limiting on Redis (ADR-028).

One bucket per (partner, surface). Capacity doubles as burst headroom;
refill rate is the partner's configured per-minute limit. The whole
check-and-consume is a single Lua script so concurrent API replicas
can't race the counter.

Fail-open on Redis outage: the partner surface degrades to "no rate
limit" rather than taking every integration down with our Redis. The
event is logged loudly — an outage that silences rate limiting should
page, not hide.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, cast

import structlog
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

# KEYS[1] = bucket key
# ARGV = capacity, refill_per_second, now (epoch seconds), cost
# Returns 1 if allowed (token consumed), 0 if rejected.
# ``now`` is read from the Redis server clock (``TIME``) by the caller
# and passed in, so every API replica refills against the same clock —
# process-local clocks would each refill independently and multiply the
# effective limit. Passing it as ARGV keeps the script deterministic.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

tokens = math.min(capacity, tokens + (now - ts) * refill_per_sec)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- Idle buckets self-clean once full again: capacity/refill seconds.
redis.call('EXPIRE', key, math.ceil(capacity / refill_per_sec) * 2)
return allowed
"""


async def allow(
    redis: Redis,
    *,
    key: str,
    per_minute: int,
    cost: int = 1,
) -> bool:
    """True if the request fits the bucket. ``per_minute`` is both the
    sustained rate and the burst capacity."""
    if per_minute <= 0:
        return False
    try:
        # redis-py types these as sync|async unions (the client can be
        # either); we only ever use the async client, so cast to Awaitable.
        seconds, micros = await cast("Awaitable[tuple[int, int]]", redis.time())
        now = float(seconds) + float(micros) / 1e6
        result = await cast(
            "Awaitable[Any]",
            redis.eval(
                _TOKEN_BUCKET_LUA,
                1,
                key,
                per_minute,
                per_minute / 60.0,
                now,
                cost,
            ),
        )
        return bool(int(result))
    except Exception:
        log.error("rate_limit.redis_unavailable_fail_open", key=key)
        return True


def mint_bucket_key(partner_id: str) -> str:
    return f"rl:partner:{partner_id}:mint"


def embed_bucket_key(partner_id: str) -> str:
    return f"rl:partner:{partner_id}:embed"


def broadcast_bucket_key(partner_id: str) -> str:
    """Server-to-server broadcast surface. Its own bucket so a partner
    hammering sends cannot starve its own provisioning calls (or the
    other way round) — the limits are tuned per surface, not shared."""
    return f"rl:partner:{partner_id}:broadcast"
