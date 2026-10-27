"""Spec 047, T004 — ``GET /console/me`` dice qué consola ve el partner (requisito 55.2).

La consola elige el marco con ``console_version``: ``v1`` (la de hoy) hasta que
Auphere activa la nueva para ese partner, ``v2`` después, y ``v1`` otra vez si
se desactiva. La activación es de un partner: la de A no toca a B.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services import console_v2

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _version(client: Any, who: dict[str, Any]) -> str:
    resp = await client.get("/console/me", headers=who["headers"]())
    assert resp.status_code == 200, resp.text
    version: str = resp.json()["console_version"]
    return version


async def test_a_partner_that_was_not_activated_sees_v1(
    client: Any, console_world: dict[str, Any]
) -> None:
    assert await _version(client, console_world["a"]) == "v1"


async def test_activation_is_per_partner_and_can_be_undone(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a, b = console_world["a"], console_world["b"]
    async with db_session.begin():
        await console_v2.enable_console_v2(db_session, a["partner_id"], actor="operator:ana")

    assert await _version(client, a) == "v2"
    assert await _version(client, b) == "v1"

    async with db_session.begin():
        await console_v2.disable_console_v2(db_session, a["partner_id"], actor="operator:ana")
    assert await _version(client, a) == "v1"
