"""Spec 076, requisito 1.7 — el identificador del clic se borra a los 90 días.

Se pone a NULL el ``ctwa_clid`` de los clics de hace más de
``retention_ad_click_days``; el resto del origen (anuncio, titular, enlace) se
queda, porque la Bandeja y el informe lo siguen usando. Con 0 o menos el paso no
hace nada. Trabaja tenant a tenant: con FORCE RLS, una pasada sin tenant no vería
ninguna fila.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.dispatcher import accept_inbound
from nexus_worker.streams.ad_referral_retention_cron import clear_old_clicks

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import CustomerAdReferral

from ._turn_world import make_world

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

AD = {"source_type": "ad", "source_id": "1", "headline": "Corte", "ctwa_clid": "CLICK"}


async def _age(world: Any, wamid: str, days: int) -> None:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        await s.execute(
            sa.update(CustomerAdReferral)
            .where(CustomerAdReferral.provider_message_id == wamid)
            .values(clicked_at=datetime.now(UTC) - timedelta(days=days))
        )
        await s.commit()


async def _rows(world: Any) -> dict[str, CustomerAdReferral]:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, world.tenant_id):
        rows = (await s.execute(sa.select(CustomerAdReferral))).scalars().all()
        for r in rows:
            s.expunge(r)
        return {r.provider_message_id: r for r in rows}


async def test_old_clicks_lose_their_id_and_keep_the_rest(db_session) -> None:
    world = await make_world(db_session)
    await accept_inbound(world.event("a", user="+34600000011", referral=AD, wamid="wamid.old"))
    await accept_inbound(world.event("b", user="+34600000012", referral=AD, wamid="wamid.new"))
    await _age(world, "wamid.old", 91)
    await _age(world, "wamid.new", 89)

    cleared = await clear_old_clicks(world.tenant_id, days=90)

    assert cleared == 1
    rows = await _rows(world)
    assert rows["wamid.old"].ctwa_clid is None
    assert rows["wamid.old"].headline == "Corte" and rows["wamid.old"].source_id == "1"
    assert rows["wamid.new"].ctwa_clid == "CLICK"


@pytest.mark.parametrize("days", [0, -1])
async def test_zero_or_less_does_nothing(db_session, days: int) -> None:
    world = await make_world(db_session)
    await accept_inbound(world.event("a", user="+34600000013", referral=AD, wamid="wamid.z"))
    await _age(world, "wamid.z", 400)
    assert await clear_old_clicks(world.tenant_id, days=days) == 0
    assert (await _rows(world))["wamid.z"].ctwa_clid == "CLICK"


async def test_another_tenant_is_untouched(db_session) -> None:
    mine = await make_world(db_session)
    theirs = await make_world(db_session)
    await accept_inbound(theirs.event("a", user="+34600000014", referral=AD, wamid="wamid.t"))
    await _age(theirs, "wamid.t", 120)
    assert await clear_old_clicks(mine.tenant_id, days=90) == 0
    assert (await _rows(theirs))["wamid.t"].ctwa_clid == "CLICK"
