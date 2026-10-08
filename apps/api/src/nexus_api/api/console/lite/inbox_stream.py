"""``GET /console/lite/inbox/stream`` — la Bandeja en vivo (spec 030, D17).

Se suscribe **solo** al canal ``inbox:{tenant}`` del cliente de la sesión y
reenvía cada evento como SSE, con un latido cada 15 s para que los proxies no
corten la conexión en reposo. Los eventos no llevan cuerpos: la consola vuelve
a pedir lo que cambió por sus rutas con RLS.

No abre transacción de base: una SSE vive minutos, y una transacción abierta
tanto tiempo retendría una conexión del pool. La persona y su cliente se
verifican al abrir; si se le retira el acceso, la próxima reconexión ya no
pasa.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from nexus_api.api.deps import get_redis
from nexus_api.core.client_auth import ClientPrincipal, require_client_principal
from nexus_api.services.inbox_stream import EVENTS, inbox_channel

router = APIRouter(prefix="/inbox")
log = structlog.get_logger(__name__)

HEARTBEAT_SECONDS = 15.0


@router.get("/stream")
async def stream(
    request: Request,
    principal: ClientPrincipal = Depends(require_client_principal("inbox")),
    redis: Redis = Depends(get_redis),
) -> EventSourceResponse:
    channel = inbox_channel(principal.tenant_id)

    async def events() -> AsyncIterator[dict[str, str]]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        yield {"event": "ready", "data": "{}"}
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
                )
                if msg is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                raw = msg.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode()
                try:
                    parsed = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    continue
                name = parsed.get("event")
                if name not in EVENTS:
                    continue
                yield {"event": str(name), "data": json.dumps(parsed)}
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()  # type: ignore[no-untyped-call]
            except Exception:  # pragma: no cover - cierre best-effort
                pass

    return EventSourceResponse(events())
