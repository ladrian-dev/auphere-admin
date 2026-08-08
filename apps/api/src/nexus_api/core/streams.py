"""Single publication point for Redis Streams (WP-04, plataforma v2 Fase 0).

Closes V2 of the scaling report: every ``XADD`` in the codebase previously
published without ``MAXLEN``, so a stalled consumer made Redis grow without
bound until the instance OOMed — and the webhook kept returning 200 while
messages were silently at risk.

``xadd_capped`` is the only allowed way to publish. The architecture test
``apps/api/tests/unit/test_no_raw_xadd.py`` greps the tree and fails the
build on any raw ``redis.xadd(`` outside this module, so the invariant
survives future contributors.

The cap is approximate (``~``): Redis trims to at least ``maxlen`` but only
at radix-tree node boundaries, which is O(1) instead of O(log n) per call.
100k entries of 1-3 KB ≈ 100-300 MB worst case per stream — bounded memory,
and far more headroom than any consumer lag we would tolerate before the
queue-age alert (WP-06) fires anyway.
"""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis

DEFAULT_MAXLEN = 100_000


async def xadd_capped(
    redis: Redis,
    stream: str,
    fields: dict[str, Any],
    *,
    maxlen: int = DEFAULT_MAXLEN,
) -> Any:
    """Publish ``fields`` to ``stream`` with an approximate length cap.

    Returns the entry id (bytes or str depending on the client's
    ``decode_responses``), same contract as ``redis.xadd``.
    """
    return await redis.xadd(  # noqa: NEXUS-RAW-XADD — the one allowed call site
        stream,
        fields,  # type: ignore[arg-type]  # redis stub types xadd fields as invariant dict
        maxlen=maxlen,
        approximate=True,
    )
