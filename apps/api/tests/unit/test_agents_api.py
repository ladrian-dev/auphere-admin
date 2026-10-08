"""Spec 030 T094 — los agentes de un cliente por la API (R14.1, 14.2, 14.5, 14.9).

Contrato: ``specs/030-consola-lite-del-cliente/contracts/agents-api.md``. Fija:

- crear un agente siembra su borrador desde una plantilla (los números de
  versión siguen siendo del cliente: el primero del agente nuevo no es v1);
- el nombre es único entre los activos, sin distinguir mayúsculas;
- ``?agent=`` en las rutas del agente actúa sobre ese agente; sin él, sobre el
  principal; un agente que no es del cliente es 404;
- publicar la versión de un agente no apaga la de otro;
- un número solo se da a un agente publicado y no solo de envío; archivar no
  deja números sin quien conteste ni al cliente sin agentes;
- el hilo del Playground fija su agente;
- el admin dice lo mismo.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Channel, ChannelStatus, ChannelType, QAThread

pytestmark = pytest.mark.asyncio


# generic_v1 asks for these two; the rest have defaults.
_PLACES = {"tenant.address": "Calle Mayor 1", "tenant.business_hours_label": "L-V 9-18"}


def _u(a: dict[str, Any], path: str) -> str:
    return f"/console/clients/{a['ref']}{path}"


async def _principal_live(client, a) -> None:
    r = await client.post(
        _u(a, "/agent/from-seed"),
        headers=a["headers"](),
        json={"seed_template": "generic_v1", "placeholders": _PLACES},
    )
    assert r.status_code == 201, r.text
    p = await client.post(
        _u(a, f"/agent/versions/{r.json()['version']}/publish"), headers=a["headers"]()
    )
    assert p.status_code == 200, p.text


async def _channel(db_session, tenant_id: uuid.UUID, *, send_only: bool = False) -> uuid.UUID:
    ch = Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3460{uuid.uuid4().int % 10**7:07d}",
        config={"phone_number_id": "PN", **({"agent_enabled": False} if send_only else {})},
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(ch)
    await db_session.commit()
    return ch.id


async def test_a_second_agent_lives_beside_the_first(client, db_session, console_world) -> None:
    a = console_world["a"]
    await _principal_live(client, a)
    agents = (await client.get(_u(a, "/agents"), headers=a["headers"]())).json()
    assert [(x["name"], x["is_principal"], x["active_version"]) for x in agents] == [
        ("Agente principal", True, 1)
    ]
    principal = agents[0]["id"]

    r = await client.post(
        _u(a, "/agents"),
        headers=a["headers"](),
        json={"name": "Ventas", "seed_template": "generic_v1", "placeholders": _PLACES},
    )
    assert r.status_code == 201, r.text
    sales = r.json()
    assert sales["is_principal"] is False
    assert sales["active_version"] is None
    assert sales["draft_version"] == 2  # numbered per client, not per agent

    dup = await client.post(
        _u(a, "/agents"),
        headers=a["headers"](),
        json={"name": "  VENTAS ", "seed_template": "generic_v1", "placeholders": _PLACES},
    )
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "name_taken"

    # ?agent= scopes the agent routes; without it, the principal.
    mine = (await client.get(_u(a, f"/agent?agent={sales['id']}"), headers=a["headers"]())).json()
    assert [v["version"] for v in mine["versions"]] == [2]
    main = (await client.get(_u(a, "/agent"), headers=a["headers"]())).json()
    assert main["active_version"] == 1
    ghost = await client.get(_u(a, f"/agent?agent={uuid.uuid4()}"), headers=a["headers"]())
    assert ghost.status_code == 404

    # A version of another agent does not exist under ?agent=.
    wrong = await client.post(
        _u(a, f"/agent/versions/1/publish?agent={sales['id']}"), headers=a["headers"]()
    )
    assert wrong.status_code == 404

    # Publishing the new agent leaves the principal live.
    pub = await client.post(
        _u(a, f"/agent/versions/2/publish?agent={sales['id']}"), headers=a["headers"]()
    )
    assert pub.status_code == 200, pub.text
    by_id = {
        x["id"]: x for x in (await client.get(_u(a, "/agents"), headers=a["headers"]())).json()
    }
    assert by_id[principal]["active_version"] == 1
    assert by_id[sales["id"]]["active_version"] == 2

    renamed = await client.patch(
        _u(a, f"/agents/{sales['id']}"), headers=a["headers"](), json={"name": "Ventas online"}
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Ventas online"


async def test_numbers_go_to_published_agents_and_archiving_has_rules(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    await _principal_live(client, a)
    principal = (await client.get(_u(a, "/agents"), headers=a["headers"]())).json()[0]["id"]
    draft_only = (
        await client.post(
            _u(a, "/agents"),
            headers=a["headers"](),
            json={"name": "Borrador", "seed_template": "generic_v1", "placeholders": _PLACES},
        )
    ).json()["id"]
    number = await _channel(db_session, a["tenant_id"])
    send_only = await _channel(db_session, a["tenant_id"], send_only=True)

    async def assign(channel: uuid.UUID, agent: str):
        return await client.patch(
            _u(a, f"/channels/{channel}/agent"), headers=a["headers"](), json={"agent_id": agent}
        )

    r = await assign(number, draft_only)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "agent_not_published"
    r = await assign(send_only, principal)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "channel_send_only"
    r = await assign(number, principal)
    assert r.status_code == 200 and r.json()["agent_id"] == principal

    r = await client.patch(
        _u(a, f"/agents/{principal}"), headers=a["headers"](), json={"status": "archived"}
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "agent_has_channels"
    r = await client.patch(
        _u(a, f"/agents/{draft_only}"), headers=a["headers"](), json={"status": "archived"}
    )
    assert r.status_code == 200 and r.json()["status"] == "archived"
    # The archived one no longer counts, and the principal is the last one.
    listed = [x["id"] for x in (await client.get(_u(a, "/agents"), headers=a["headers"]())).json()]
    assert listed == [principal]


async def test_the_last_agent_cannot_be_archived(client, console_world) -> None:
    a = console_world["a"]
    await _principal_live(client, a)
    principal = (await client.get(_u(a, "/agents"), headers=a["headers"]())).json()[0]["id"]
    r = await client.patch(
        _u(a, f"/agents/{principal}"), headers=a["headers"](), json={"status": "archived"}
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "last_agent"


async def test_a_playground_thread_keeps_its_agent(client, db_session, console_world) -> None:
    a = console_world["a"]
    await _principal_live(client, a)
    agents = (await client.get(_u(a, "/agents"), headers=a["headers"]())).json()
    sales = (
        await client.post(
            _u(a, "/agents"),
            headers=a["headers"](),
            json={"name": "Ventas", "seed_template": "generic_v1", "placeholders": _PLACES},
        )
    ).json()["id"]
    pinned = await client.post(
        _u(a, f"/playground/threads?agent={sales}"), headers=a["headers"](), json={"title": "B"}
    )
    plain = await client.post(
        _u(a, "/playground/threads"), headers=a["headers"](), json={"title": "A"}
    )
    assert pinned.status_code == 201 and plain.status_code == 201, (pinned.text, plain.text)
    rows = {
        str(r.id): r.agent_id
        for r in (
            await db_session.execute(
                sa.select(QAThread).where(QAThread.tenant_id == a["tenant_id"])
            )
        ).scalars()
    }
    assert rows[pinned.json()["id"]] == uuid.UUID(sales)
    assert rows[plain.json()["id"]] == uuid.UUID(agents[0]["id"])


async def test_the_admin_says_the_same(client, db_session, console_world, admin_headers) -> None:
    from nexus_api.services import operator_identity

    a = console_world["a"]
    await _principal_live(client, a)
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    base = f"/admin/tenants/{a['tenant_id']}/agents"
    r = await client.post(base, headers=headers, json={"name": "Soporte"})
    assert r.status_code == 201, r.text
    assert r.json()["active_version"] is None
    dup = await client.post(base, headers=headers, json={"name": "soporte"})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "name_taken"
    names = [x["name"] for x in (await client.get(base, headers=admin_headers)).json()]
    assert names == ["Agente principal", "Soporte"]
    staged = await client.put(
        f"/admin/tenants/{a['tenant_id']}/agent-config?agent_id={r.json()['id']}",
        headers=admin_headers,
        json={
            "system_prompt_rendered": "Eres soporte.",
            "channels": [],
            "tools": [],
            "policies": {},
        },
    )
    assert staged.status_code == 201, staged.text
    assert staged.json()["agent_id"] == r.json()["id"]

    # A template can be sown into that agent too.
    seeded = await client.post(
        f"/admin/tenants/{a['tenant_id']}/agent-config/from-seed?agent_id={r.json()['id']}",
        headers=admin_headers,
        json={
            "seed_template_ref": "generic_v1",
            "placeholders": {**_PLACES, "tenant.name": "Demo", "tenant.timezone": "Europe/Madrid"},
        },
    )
    assert seeded.status_code == 201, seeded.text
    assert seeded.json()["agent_id"] == r.json()["id"]

    # Another client's agent does not exist here: no version can point at it.
    other = console_world["b"]
    await _principal_live(client, other)
    foreign = (await client.get(_u(other, "/agents"), headers=other["headers"]())).json()[0]["id"]
    hijack = await client.put(
        f"/admin/tenants/{a['tenant_id']}/agent-config?agent_id={foreign}",
        headers=admin_headers,
        json={"system_prompt_rendered": "x", "channels": [], "tools": [], "policies": {}},
    )
    assert hijack.status_code == 404, hijack.text


async def test_the_playground_lists_each_agents_threads(client, db_session, console_world) -> None:
    a = console_world["a"]
    await _principal_live(client, a)
    principal = (await client.get(_u(a, "/agents"), headers=a["headers"]())).json()[0]["id"]
    sales = (
        await client.post(
            _u(a, "/agents"),
            headers=a["headers"](),
            json={"name": "Ventas", "seed_template": "generic_v1", "placeholders": _PLACES},
        )
    ).json()["id"]
    main = await client.post(
        _u(a, "/playground/threads"), headers=a["headers"](), json={"title": "Principal"}
    )
    other = await client.post(
        _u(a, f"/playground/threads?agent={sales}"), headers=a["headers"](), json={"title": "V"}
    )
    # A thread from before agents existed has none: it is the principal's.
    await db_session.execute(
        sa.update(QAThread).where(QAThread.id == uuid.UUID(main.json()["id"])).values(agent_id=None)
    )
    await db_session.commit()

    async def titles(query: str) -> list[str]:
        r = await client.get(_u(a, f"/playground/threads{query}"), headers=a["headers"]())
        assert r.status_code == 200, r.text
        return sorted(t["title"] for t in r.json())

    assert other.status_code == 201
    assert await titles("") == ["Principal", "V"]
    assert await titles(f"?agent={sales}") == ["V"]
    assert await titles(f"?agent={principal}") == ["Principal"]
    ghost = await client.get(
        _u(a, f"/playground/threads?agent={uuid.uuid4()}"), headers=a["headers"]()
    )
    assert ghost.status_code == 404
