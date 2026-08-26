"""Fase 4 packs — isolation + Sec tests required by the cut."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.companion.tools import CompanionToolbelt
from nexus_api.core.console_auth import InProcessActor
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.workflow import WorkflowCron, WorkflowPack, WorkflowSendReceipt
from nexus_api.packs.cron import process_due_workflow_crons
from nexus_api.packs.send import send_if_new

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

VALID: dict[str, Any] = {
    "trigger": "cron",
    "steps": ["send_template", "wait_reply", "end"],
    "template_id": "hello_world",
    "cron": {"hour": 9, "minute": 0, "timezone": "Europe/Madrid"},
    "enabled": True,
    "stop": "end",
}


def _actor(side: dict[str, Any]) -> InProcessActor:
    return InProcessActor(
        user_id=side["user_id"],
        partner_id=side["partner_id"],
        jti=f"companion:{uuid.uuid4()}",
    )


async def test_foreign_client_workflow_is_opaque_404(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    for method, path_tpl in (
        ("GET", "/console/clients/{ref}/workflow"),
        ("PUT", "/console/clients/{ref}/workflow"),
        ("GET", "/console/clients/{ref}/workflow/runs"),
    ):
        foreign = await client.request(
            method,
            path_tpl.format(ref=b["ref"]),
            headers=a["headers"](),
            json=VALID if method == "PUT" else None,
        )
        missing = await client.request(
            method,
            path_tpl.format(ref="does-not-exist"),
            headers=a["headers"](),
            json=VALID if method == "PUT" else None,
        )
        assert foreign.status_code == 404, f"{method} {path_tpl}: {foreign.text}"
        assert missing.status_code == 404
        assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}


async def test_partner_id_in_workflow_body_is_422(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.put(
        f"/console/clients/{a['ref']}/workflow",
        headers=a["headers"](),
        json={**VALID, "partner_id": str(a["partner_id"])},
    )
    assert resp.status_code == 422


async def test_unknown_step_id_is_422(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.put(
        f"/console/clients/{a['ref']}/workflow",
        headers=a["headers"](),
        json={**VALID, "steps": ["send_template", "call_agent", "end"]},
    )
    assert resp.status_code == 422


async def test_companion_propose_pack_does_not_apply(client, console_world) -> None:
    from nexus_api.main import app

    a = console_world["a"]
    before = await client.get(f"/console/clients/{a['ref']}/workflow", headers=a["headers"]())
    assert before.status_code == 200
    assert before.json()["is_set"] is False

    async with CompanionToolbelt(actor=_actor(a), app=app, principal_id=a["user_id"]) as belt:
        out = await belt.call(
            "console.propose_pack",
            {
                "client_ref": a["ref"],
                "trigger": "cron",
                "steps": "send_template,wait_reply,end",
                "template_id": "hello_world",
                "hour": 9,
                "minute": 0,
                "timezone": "Europe/Madrid",
            },
        )
    assert out.ok is True
    assert '"staged": true' in out.content
    assert '"kind": "pack"' in out.content

    after = await client.get(f"/console/clients/{a['ref']}/workflow", headers=a["headers"]())
    assert after.json()["is_set"] is False
    assert after.json() == before.json()


async def test_send_is_idempotent_before_interrupt(console_world) -> None:
    a = console_world["a"]
    hits: list[str] = []

    def sender() -> None:
        hits.append("meta")

    sm = get_sessionmaker()
    key = {
        "partner_id": a["partner_id"],
        "thread_id": f"t-{uuid.uuid4()}",
        "step_id": "send_template",
        "run_id": f"r-{uuid.uuid4()}",
    }
    async with sm() as session, session.begin():
        first = await send_if_new(session, sender=sender, **key)
        n = await session.scalar(sa.select(sa.func.count()).select_from(WorkflowSendReceipt))
        assert first is True
        assert int(n or 0) >= 1
        second = await send_if_new(session, sender=sender, **key)
        assert second is False
    assert hits == ["meta"]


async def _seed_pack_and_cron(
    partner_id: uuid.UUID,
    client_ref: str,
    *,
    enabled: bool,
    end_time: datetime | None,
    run_at: datetime,
) -> None:
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        pack = (
            await session.scalars(
                sa.select(WorkflowPack).where(
                    WorkflowPack.partner_id == partner_id,
                    WorkflowPack.client_ref == client_ref,
                )
            )
        ).first()
        if pack is None:
            pack = WorkflowPack(
                partner_id=partner_id,
                client_ref=client_ref,
                yaml={
                    "trigger": "cron",
                    "steps": ["send_template", "end"],
                    "template_id": "x",
                },
                version=1,
            )
            session.add(pack)
            await session.flush()
        cron = (
            await session.scalars(sa.select(WorkflowCron).where(WorkflowCron.pack_id == pack.id))
        ).first()
        if cron is None:
            session.add(
                WorkflowCron(
                    partner_id=partner_id,
                    pack_id=pack.id,
                    run_at_utc=run_at,
                    timezone="UTC",
                    hour=9,
                    minute=0,
                    enabled=enabled,
                    end_time=end_time,
                )
            )
            return
        cron.run_at_utc = run_at
        cron.enabled = enabled
        cron.end_time = end_time


async def test_dead_cron_does_not_fire(console_world) -> None:
    a = console_world["a"]
    fired: list[str] = []

    async def start_run(_session: object, cron: WorkflowCron, _pack: object) -> None:
        fired.append(str(cron.id))

    past = datetime.now(UTC) - timedelta(hours=1)
    await _seed_pack_and_cron(a["partner_id"], a["ref"], enabled=False, end_time=None, run_at=past)
    n = await process_due_workflow_crons(now=datetime.now(UTC), start_run=start_run)
    assert n == 0
    assert fired == []

    await _seed_pack_and_cron(a["partner_id"], a["ref"], enabled=True, end_time=past, run_at=past)
    n = await process_due_workflow_crons(now=datetime.now(UTC), start_run=start_run)
    assert n == 0
    assert fired == []


async def test_admin_foreign_client_workflow_is_opaque_404(
    client, console_world, admin_headers
) -> None:
    a, b = console_world["a"], console_world["b"]
    missing_id = uuid.uuid4()
    for path_tpl in (
        "/admin/partners/{pid}/clients/{ref}/workflow",
        "/admin/partners/{pid}/clients/{ref}/workflow/runs",
    ):
        foreign = await client.get(
            path_tpl.format(pid=a["partner_id"], ref=b["ref"]),
            headers=admin_headers,
        )
        missing = await client.get(
            path_tpl.format(pid=a["partner_id"], ref="does-not-exist"),
            headers=admin_headers,
        )
        assert foreign.status_code == 404, f"{path_tpl}: {foreign.text}"
        assert missing.status_code == 404
        assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}
        assert foreign.status_code != 403
        assert "sk-" not in foreign.text
        assert "sk-" not in missing.text

        unknown_partner = await client.get(
            path_tpl.format(pid=missing_id, ref=a["ref"]),
            headers=admin_headers,
        )
        assert unknown_partner.status_code == 404
        assert unknown_partner.json() == {"detail": f"partner {missing_id} not found"}


async def test_admin_workflow_has_no_put(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    path = f"/admin/partners/{a['partner_id']}/clients/{a['ref']}/workflow"
    put = await client.put(path, headers=admin_headers, json=VALID)
    delete = await client.delete(path, headers=admin_headers)
    assert put.status_code == 405, put.text
    assert delete.status_code == 405, delete.text
