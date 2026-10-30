"""Spec 047, enmienda del 2026-10-29 (requisito 63.1, H5; research D56) — la página
del canal dice cómo se conectó el número.

La cabecera del canal es «WhatsApp · {método} · canal de {agente}»: la API manda
``method`` (``coexistence`` o ``cloud_api``) y ``None`` cuando no se sabe, para que
la consola no lo invente (§V).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Channel

from ..business._business_world import Biz
from ._channel_world import _channel, _page, _published

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _set(db_session: AsyncSession, biz: Biz, channel_id: Any, **values: Any) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = await db_session.get(Channel, channel_id)
        assert channel is not None
        for key, value in values.items():
            setattr(channel, key, value)


async def test_the_channel_page_says_how_the_number_was_connected(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    unknown = await _channel(db_session, biz, agent_id, "34911000101")
    assert (await _page(client, biz, unknown))["method"] is None, "sin dato, no se inventa"

    cloud = await _channel(db_session, biz, agent_id, "34911000102")
    await _set(db_session, biz, cloud, config={"phone_number_id": "PN0102", "mode": "cloud_api"})
    assert (await _page(client, biz, cloud))["method"] == "cloud_api"

    coex = await _channel(db_session, biz, agent_id, "34911000103")
    await _set(db_session, biz, coex, coexistence=True)
    assert (await _page(client, biz, coex))["method"] == "coexistence"

    by_mode = await _channel(db_session, biz, agent_id, "34911000104")
    await _set(
        db_session, biz, by_mode, config={"phone_number_id": "PN0104", "mode": "coexistence"}
    )
    assert (await _page(client, biz, by_mode))["method"] == "coexistence"
