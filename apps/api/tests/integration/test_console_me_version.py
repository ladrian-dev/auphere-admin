"""Spec 047, T004 — ``GET /console/me`` dice qué consola ve el partner (requisito 55.2).

La consola elige el marco con ``console_version``. Desde la 0204 la nueva es la de
todos los partners (Andrés, 2026-10-29): el panel ya no la activa uno a uno.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Partner

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _version(client: Any, who: dict[str, Any]) -> str:
    resp = await client.get("/console/me", headers=who["headers"]())
    assert resp.status_code == 200, resp.text
    version: str = resp.json()["console_version"]
    return version


async def test_every_partner_sees_the_new_console(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """Desde la 0204 todos tienen la consola nueva: el panel ya no la activa por partner."""
    a, b = console_world["a"], console_world["b"]
    async with db_session.begin():
        await db_session.execute(
            sa.update(Partner)
            .where(Partner.id.in_([a["partner_id"], b["partner_id"]]))
            .values(console_v2_enabled_at=sa.func.now(), console_v2_enabled_by="auphere:alta")
        )
    assert await _version(client, a) == "v2"
    assert await _version(client, b) == "v2"
