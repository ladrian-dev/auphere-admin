"""Spec 082 (datos al día) — lo que la consola relee después de escribir.

Requisito 1.1: una escritura de Reservas está confirmada en la base **antes**
de que su respuesta salga. Si no, la consola relee (``router.refresh`` o la
consulta de React Query) contra una base que aún no la tiene y pinta lo de
antes, sin nada que la vuelva a leer hasta el sondeo.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from tests.conftest import future_day, make_reservas

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/console/lite/reservas"


@pytest.fixture
async def shop(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


@pytest.fixture
async def ordered() -> AsyncIterator[tuple[Any, list[str]]]:
    """Un cliente HTTP sobre la app que apunta, en orden, cada commit de una
    sesión y el último trozo del cuerpo de cada respuesta."""
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from nexus_api.main import app

    seen: list[str] = []

    def on_commit(session: Session) -> None:
        from nexus_api.db.models import Reservation

        # Solo cuenta el commit que lleva la reserva cancelada, no el del token ni otros.
        if any(
            isinstance(o, Reservation) and o.status == "cancelled"
            for o in session.identity_map.values()
        ):
            seen.append("commit")

    async def wrapped(scope: Any, receive: Any, send: Any) -> None:
        async def spy(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.body" and not message.get("more_body"):
                seen.append("body")
            await send(message)

        await app(scope, receive, spy)

    event.listen(Session, "after_commit", on_commit)
    try:
        async with LifespanManager(app):
            transport = ASGITransport(app=wrapped)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac, seen
    finally:
        event.remove(Session, "after_commit", on_commit)


async def test_a_cancel_is_committed_before_its_answer_leaves(ordered, shop) -> None:
    client, seen = ordered
    h = shop["headers"]
    made = await client.post(
        f"{BASE}/bookings",
        headers=h(),
        json={
            "date": future_day().isoformat(),
            "time": "10:00",
            "staff_id": str(shop["lucia"]),
            "service_id": str(shop["corte"]),
            "contact": {"name": "Ana Pérez", "phone": "+56911112222"},
        },
    )
    assert made.status_code == 201, made.text
    b = made.json()

    seen.clear()
    r = await client.post(
        f"{BASE}/bookings/{b['id']}/cancel",
        headers={**h(), "If-Match": str(b["version"])},
        json={"notify": False, "offer_slot": False},
    )
    assert r.status_code == 200, r.text
    assert "commit" in seen, seen
    assert seen.index("commit") < seen.index("body"), (
        f"la respuesta salió antes de confirmar la cancelación: {seen}"
    )
