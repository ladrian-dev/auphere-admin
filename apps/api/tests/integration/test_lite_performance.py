"""Spec 030 T108 — la Bandeja y el Panel de un cliente con 5.000 conversaciones.

Se siembran 5.000 conversaciones (10.000 mensajes; una de cada diez esperando
a una persona) en un cliente y se mide, por la API real y contra la misma base
de pruebas que el resto de la suite:

- la primera página de la Bandeja — p95 < 1,5 s (CE-007), también filtrada
  por «Necesita humano» y por búsqueda, que recorren otro camino;
- el Panel lite (``/console/lite/home``) — p95 < 1 s.

Mide la API dentro del proceso, sin red ni navegador. El presupuesto de CE-007
es de extremo a extremo: si esto se acerca al límite, en staging no cabe. Los
tiempos salen por la salida estándar (``-s``) para la evidencia de T108.

La latencia de un mensaje nuevo (CE-004, < 5 s) no se mide aquí: depende del
worker y de Redis, y la cubre la prueba en staging del quickstart (T110).
"""

from __future__ import annotations

import statistics
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
)
from tests.conftest import make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]

N = 5_000
RUNS = 20
CHUNK = 1_000


async def _seed(db_session: Any, tenant_id: uuid.UUID, channel_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    customers = [
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "identifier": f"+5491{i:09d}",
            "name": f"Contacto {i}",
            "preferences": {},
        }
        for i in range(N)
    ]
    conversations = [
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "channel_id": channel_id,
            "customer_id": c["id"],
            "status": ConversationStatus.ESCALATED if i % 10 == 0 else ConversationStatus.OPEN,
            "last_inbound_at": now - timedelta(minutes=i),
            "last_message_at": now - timedelta(minutes=i) + timedelta(seconds=5),
        }
        for i, c in enumerate(customers)
    ]
    messages: list[dict[str, Any]] = []
    for i, conv in enumerate(conversations):
        at = now - timedelta(minutes=i)
        messages.append(
            {
                "tenant_id": tenant_id,
                "conversation_id": conv["id"],
                "direction": MessageDirection.INBOUND,
                "status": MessageStatus.DELIVERED,
                "content": f"Hola, soy el contacto {i}",
                "tool_calls": [],
                "actor_kind": None,  # executemany wants the same keys in every row
                "created_at": at,
            }
        )
        messages.append(
            {
                "tenant_id": tenant_id,
                "conversation_id": conv["id"],
                "direction": MessageDirection.OUTBOUND,
                "status": MessageStatus.SENT,
                "content": f"Hola contacto {i}, ¿en qué te ayudo?",
                "tool_calls": [],
                "actor_kind": "agent",
                "created_at": at + timedelta(seconds=5),
            }
        )
    for model, rows in ((Customer, customers), (Conversation, conversations), (Message, messages)):
        for start in range(0, len(rows), CHUNK):
            await db_session.execute(sa.insert(model), rows[start : start + CHUNK])
    await db_session.commit()
    await db_session.execute(sa.text("ANALYZE customers, conversations, messages"))
    await db_session.commit()


async def _p95(label: str, call: Callable[[], Awaitable[Any]]) -> float:
    await call()  # warm-up: the first call pays imports and plan caches
    times: list[float] = []
    for _ in range(RUNS):
        started = time.perf_counter()
        response = await call()
        times.append(time.perf_counter() - started)
        assert response.status_code == 200, response.text
    p95 = statistics.quantiles(times, n=20)[18]
    print(f"T108 {label}: p50 {statistics.median(times) * 1000:.0f} ms · p95 {p95 * 1000:.0f} ms")
    return p95


async def test_inbox_and_panel_with_five_thousand_conversations(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], conversations=1
    )
    await _seed(db_session, w["tenant_id"], inbox["channel_id"])
    url = "/console/lite/inbox/conversations"

    first_page = await _p95(
        "bandeja, primera página", lambda: client.get(url, headers=inbox["headers"]())
    )
    waiting = await _p95(
        "bandeja, necesita humano",
        lambda: client.get(url, headers=inbox["headers"](), params={"filter": "waiting"}),
    )
    search = await _p95(
        "bandeja, búsqueda",
        lambda: client.get(url, headers=inbox["headers"](), params={"q": "Contacto 4321"}),
    )
    panel = await _p95(
        "panel lite", lambda: client.get("/console/lite/home", headers=inbox["headers"]())
    )

    page = (await client.get(url, headers=inbox["headers"]())).json()
    assert len(page["items"]) == 50 and page["next_cursor"]
    assert page["counts"]["waiting"] == N // 10

    assert first_page < 1.5, f"CE-007: first page p95 {first_page:.2f}s"
    assert waiting < 1.5, f"CE-007 (waiting): p95 {waiting:.2f}s"
    assert search < 1.5, f"CE-007 (search): p95 {search:.2f}s"
    assert panel < 1.0, f"Panel lite p95 {panel:.2f}s"
