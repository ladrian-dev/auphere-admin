"""Spec 058, T002 — garantía 1 (RLS) en la limpieza de esperas.

La limpieza recorre todos los clientes. Cada uno se trabaja bajo su propia RLS:
lo de un cliente nunca libera las esperas ni cierra los avisos de otro, aunque
los dos tengan exactamente la misma forma (requisitos 3.1 y 3.3).
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.db.base import get_sessionmaker
from nexus_api.services import audience_cleanup

from ..integration._audience_world import (
    TEAM,
    conversation_state,
    notices,
    paused_client,
    team_only,
    waiting,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CONTACT = "+34600000001"


async def _twin(db_session: Any, side: dict[str, Any]) -> tuple[Any, Any]:
    world = await paused_client(db_session, side)
    conversation_id = await waiting(world, CONTACT)
    await team_only(world, TEAM)
    return world, conversation_id


async def test_one_client_never_releases_another(db_session, console_world) -> None:
    a, a_conv = await _twin(db_session, console_world["a"])
    b, b_conv = await _twin(db_session, console_world["b"])

    report = await audience_cleanup.release_tenant(get_sessionmaker(), a.tenant_id, apply=True)

    assert report.released == 1
    assert await conversation_state(a, a_conv) == ("open", "out_of_audience")
    assert await conversation_state(b, b_conv) == ("escalated", "paused_client"), "B intacto"
    a_notices = await notices(db_session, a.extra["partner_id"])
    b_notices = await notices(db_session, b.extra["partner_id"])
    assert a_notices[str(a_conv)] is not None
    assert b_notices[str(b_conv)] is None, "el aviso de B sigue sin atender"


async def test_the_full_run_keeps_each_client_in_its_own_lane(db_session, console_world) -> None:
    a, a_conv = await _twin(db_session, console_world["a"])
    b, b_conv = await _twin(db_session, console_world["b"])

    summary = await audience_cleanup.run(get_sessionmaker(), apply=True)

    assert summary.released == 2
    assert await conversation_state(a, a_conv) == ("open", "out_of_audience")
    assert await conversation_state(b, b_conv) == ("open", "out_of_audience")
    a_notices = await notices(db_session, a.extra["partner_id"])
    b_notices = await notices(db_session, b.extra["partner_id"])
    assert set(a_notices) == {str(a_conv)}, "A solo ve su aviso"
    assert set(b_notices) == {str(b_conv)}, "B solo ve su aviso"
    assert a_notices[str(a_conv)] is not None
    assert b_notices[str(b_conv)] is not None
