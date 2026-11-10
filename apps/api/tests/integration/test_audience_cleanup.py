"""Spec 058, T009 — limpiar las esperas que el fallo ya dejó en la Bandeja.

Requisitos 3.1 a 3.6. Es una herramienta de operador: en seco por defecto,
de verdad con ``apply=True`` y nunca desde un despliegue. Solo saca las esperas
de puerta, sin asignar, de contactos fuera de la audiencia **actual** en los
números que deciden su propia audiencia.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from structlog.testing import capture_logs

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ClientPushEvent, Conversation, ConversationStatus
from nexus_api.services import audience_cleanup

from ._audience_world import (
    TEAM,
    conversation_state,
    in_tenant,
    notices,
    paused_client,
    released,
    team_only,
    waiting,
)
from ._turn_world import outbound_rows, scalar

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

OUT_1 = "+34600000001"
OUT_2 = "+34600000002"
OUT_ESCALATED = "+34600000004"
OUT_ASSIGNED = "+34600000005"
OUT_RESOLVED = "+34600000006"

RELEASE_SH = Path(__file__).resolve().parents[2] / "scripts" / "release.sh"


async def _seed(db_session: Any, console_world: dict[str, Any]) -> dict[str, Any]:
    world = await paused_client(db_session, console_world["a"])
    ids = {
        "out_1": await waiting(world, OUT_1),
        "out_2": await waiting(world, OUT_2),
        "team": await waiting(world, TEAM),
        "escalated": await waiting(world, OUT_ESCALATED),
        "assigned": await waiting(world, OUT_ASSIGNED),
        "resolved": await waiting(world, OUT_RESOLVED),
    }
    await team_only(world, TEAM)
    await in_tenant(
        world,
        sa.update(Conversation)
        .where(Conversation.id == ids["out_2"])
        .values(waiting_reason="no_balance"),
        sa.update(Conversation)
        .where(Conversation.id == ids["escalated"])
        .values(waiting_reason="escalated"),
        sa.update(Conversation)
        .where(Conversation.id == ids["assigned"])
        .values(assigned_user_id="client_persona"),
        sa.update(Conversation)
        .where(Conversation.id == ids["resolved"])
        .values(status=ConversationStatus.CLOSED),
    )
    # Un número sin audiencia propia: el partner B no tiene la consola nueva y
    # su agente es solo para administradores. Su contacto era admin; ya no.
    other = await paused_client(
        db_session,
        console_world["b"],
        console_v2=False,
        policies={"admin_access": {"admin_only": True, "admin_phones": [OUT_1]}},
    )
    other_id = await waiting(other, OUT_1)
    from nexus_api.db.models import AgentConfig

    await in_tenant(
        other,
        sa.update(AgentConfig)
        .where(AgentConfig.agent_id == other.agent_id)
        .values(policies={"admin_access": {"admin_only": True, "admin_phones": [TEAM]}}),
    )
    return {"world": world, "ids": ids, "other": other, "other_id": other_id}


async def _snapshot(world: Any, ids: dict[str, Any]) -> dict[str, tuple[str, str | None]]:
    return {k: await conversation_state(world, v) for k, v in ids.items()}


async def _pushes(world: Any) -> int:
    return int(
        await scalar(
            world,
            sa.select(sa.func.count())
            .select_from(ClientPushEvent)
            .where(ClientPushEvent.kind == "inbox.waiting"),
        )
    )


async def test_a_dry_run_counts_and_changes_nothing(db_session, console_world) -> None:
    """Requisito 3.2: lo que pasa si no se pide otra cosa."""
    seed = await _seed(db_session, console_world)
    world, ids = seed["world"], seed["ids"]
    before = await _snapshot(world, ids)

    summary = await audience_cleanup.run(get_sessionmaker())

    assert summary.apply is False
    assert summary.released == 2, "out_1 y out_2"
    assert summary.skipped_not_strict == 1
    assert await _snapshot(world, ids) == before
    assert await released(world) == {}
    assert all(
        handled is None
        for handled in (await notices(db_session, world.extra["partner_id"])).values()
    )


async def test_apply_releases_only_what_the_bug_left(db_session, console_world) -> None:
    """Requisitos 3.1, 3.3, 3.4 y 3.5."""
    seed = await _seed(db_session, console_world)
    world, ids, other = seed["world"], seed["ids"], seed["other"]
    before = await _snapshot(world, ids)
    notices_before = await notices(db_session, world.extra["partner_id"])
    pushes_before = await _pushes(world)
    outbound_before = len(await outbound_rows(world))

    with capture_logs() as logs:
        summary = await audience_cleanup.run(get_sessionmaker(), apply=True)

    assert summary.apply is True
    assert summary.released == 2
    assert summary.skipped_not_strict == 1
    assert summary.failed == 0
    after = await _snapshot(world, ids)
    assert after["out_1"] == ("open", "out_of_audience")
    assert after["out_2"] == ("open", "out_of_audience")
    for untouched in ("team", "escalated", "assigned", "resolved"):
        assert after[untouched] == before[untouched], untouched
    assert await conversation_state(other, seed["other_id"]) == ("escalated", "paused_client")

    events = await released(world)
    assert events == {
        str(ids["out_1"]): {"why": "out_of_audience", "reason": "paused_client", "actor": "system"},
        str(ids["out_2"]): {"why": "out_of_audience", "reason": "no_balance", "actor": "system"},
    }
    now = await notices(db_session, world.extra["partner_id"])
    assert set(now) == set(notices_before), "ningún aviso nuevo"
    handled = {k for k, at in now.items() if at is not None}
    assert handled == {str(ids["out_1"]), str(ids["out_2"])}
    assert await _pushes(world) == pushes_before
    assert len(await outbound_rows(world)) == outbound_before

    names = [entry.get("event") for entry in logs]
    assert "inbox.audience_cleanup.tenant" in names
    assert "inbox.audience_cleanup.done" in names
    mine = [e for e in logs if str(e.get("event", "")).startswith("inbox.audience_cleanup")]
    assert "+34" not in repr(mine), "ningún log lleva teléfono"

    again = await audience_cleanup.run(get_sessionmaker(), apply=True)
    assert again.released == 0, "una segunda pasada no cambia nada"
    assert await _snapshot(world, ids) == after


async def test_no_deploy_runs_the_cleanup() -> None:
    """Requisito 3.6: la lanza una persona, nunca ``release.sh``."""
    text = RELEASE_SH.read_text(encoding="utf-8")
    assert "release_out_of_audience_waits" not in text
    assert "audience_cleanup" not in text
