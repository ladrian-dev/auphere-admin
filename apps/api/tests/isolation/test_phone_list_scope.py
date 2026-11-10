"""Spec 031 · R15.6, R7.5 — la lista de teléfonos es de quien la pide (T033).

* Desde la web o la app, ``GET /console/lite/phones`` solo devuelve los
  teléfonos de la persona que llama, ni los de otra persona del mismo cliente.
* ``DELETE /console/lite/phones/{id}`` de otra persona es el mismo 404 que un id
  que no existe.
* En el admin, la lista de una persona solo sale bajo **su** cliente: el mismo
  ``member_id`` bajo otro tenant no devuelve nada.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.services import operator_identity
from tests.conftest import add_client_member, add_client_phone, make_client_access

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


@pytest.fixture
async def people(db_session, console_world, admin_headers) -> dict[str, Any]:
    a, b = console_world["a"], console_world["b"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    await make_client_access(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    me = await add_client_member(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    colleague = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    stranger = await add_client_member(
        db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"]
    )
    mine = await add_client_phone(db_session, membership_id=me["membership_id"])
    theirs = await add_client_phone(db_session, membership_id=colleague["membership_id"])
    far = await add_client_phone(db_session, membership_id=stranger["membership_id"])
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
        )
    return {
        "a": a,
        "b": b,
        "me": me,
        "colleague": colleague,
        "mine": mine,
        "theirs": theirs,
        "far": far,
        "admin": {**admin_headers, "X-Operator-Id": str(op.id)},
    }


@pytest.mark.parametrize("via", ["web", "app"])
async def test_the_list_is_only_mine(client, people, via: str) -> None:
    headers = people["me"]["headers"]() if via == "web" else people["mine"]["headers"]()
    resp = await client.get("/console/lite/phones", headers=headers)
    assert resp.status_code == 200
    assert [p["id"] for p in resp.json()] == [str(people["mine"]["phone_id"])]


@pytest.mark.parametrize("target", ["theirs", "far"])
async def test_closing_someone_elses_phone_is_the_ghost_404(client, people, target: str) -> None:
    headers = people["me"]["headers"]
    foreign = await client.delete(
        f"/console/lite/phones/{people[target]['phone_id']}", headers=headers()
    )
    ghost = await client.delete(f"/console/lite/phones/{uuid.uuid4()}", headers=headers())
    assert foreign.status_code == ghost.status_code == 404
    assert foreign.content == ghost.content


async def test_the_admin_list_only_answers_under_the_persons_client(client, people) -> None:
    member = people["me"]["membership_id"]
    own = await client.get(
        f"/admin/tenants/{people['a']['tenant_id']}/client-members/{member}/phones",
        headers=people["admin"],
    )
    cross = await client.get(
        f"/admin/tenants/{people['b']['tenant_id']}/client-members/{member}/phones",
        headers=people["admin"],
    )
    assert [p["id"] for p in own.json()] == [str(people["mine"]["phone_id"])]
    assert cross.status_code == 200
    assert cross.json() == []


async def test_the_admin_cannot_close_a_phone_under_another_client(client, people) -> None:
    member = people["me"]["membership_id"]
    resp = await client.delete(
        f"/admin/tenants/{people['b']['tenant_id']}/client-members/{member}"
        f"/phones/{people['mine']['phone_id']}",
        headers=people["admin"],
    )
    assert resp.status_code == 404
