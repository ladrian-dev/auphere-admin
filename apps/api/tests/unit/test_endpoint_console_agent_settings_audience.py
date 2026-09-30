"""Spec 024 (Requisitos 1.1 a 1.4, 2.2, 4.1, 5.1 · CE-004): «A quién responde»
in the agent settings endpoint.

The list is read from the version being edited, written normalised on the
draft, applied by publishing, carried by rollback, and refused when it
could leave the agent answering nobody or open an admin-only template.
What the console writes, the partner API reads unchanged.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.api.partners_clients import _admins_out
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AgentConfig, AgentConfigStatus
from tests.unit.test_endpoint_console_agent_tools import SETTINGS, _stage_and_publish

pytestmark = pytest.mark.asyncio

LIST = {
    "mode": "list",
    "numbers": [
        {"phone": "+56 9 9191 9125", "name": "Daniel, ventas"},
        {"phone": "+34 666 261 967"},
    ],
}


async def _version(db_session, tenant_id, number: int) -> AgentConfig:
    async with tenant_scoped_session(db_session, tenant_id):
        row = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.tenant_id == tenant_id, AgentConfig.version == number
            )
        )
    assert row is not None
    return row


async def _set_template(db_session, tenant_id, version: int, ref: str) -> None:
    async with tenant_scoped_session(db_session, tenant_id):
        await db_session.execute(
            sa.update(AgentConfig)
            .where(AgentConfig.tenant_id == tenant_id, AgentConfig.version == version)
            .values(seed_template_ref=ref)
        )
        await db_session.commit()


async def test_the_list_is_saved_on_the_draft_normalised_and_applied_by_publishing(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"
    v1 = await _stage_and_publish(client, a)

    before = await client.get(f"{base}/settings", headers=h())
    assert before.json()["audience"] == {"mode": "everyone", "numbers": [], "locked": False}

    saved = await client.put(
        f"{base}/settings", headers=h(), json={"settings": SETTINGS, "audience": LIST}
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["draft_created"] is True and body["version"] == v1 + 1
    assert body["audience"] == {
        "mode": "list",
        "numbers": [
            {"phone": "+56991919125", "name": "Daniel, ventas"},
            {"phone": "+34666261967", "name": None},
        ],
        "locked": False,
    }

    # The active version is untouched until publishing (clarification A).
    active = await _version(db_session, a["tenant_id"], v1)
    assert "admin_access" not in (active.policies or {})

    # GET reads the draft.
    assert (await client.get(f"{base}/settings", headers=h())).json()["audience"]["mode"] == "list"

    pub = await client.post(f"{base}/versions/{v1 + 1}/publish", headers=h())
    assert pub.status_code == 200, pub.text
    published = await _version(db_session, a["tenant_id"], v1 + 1)
    assert published.status == AgentConfigStatus.ACTIVE
    access = published.policies["admin_access"]
    assert access["admin_only"] is True
    assert access["admin_phones"] == ["+56991919125", "+34666261967"]

    # CE-004: the partner API reads exactly what the console wrote.
    admins = _admins_out(published.policies)
    assert admins.admin_only is True
    assert [(x.phone, x.name, x.role) for x in admins.admins] == [
        ("+56991919125", "Daniel, ventas", "full"),
        ("+34666261967", None, "full"),
    ]


async def test_back_to_everyone_applies_on_publish_and_rollback_restores_the_list(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"
    v1 = await _stage_and_publish(client, a)
    await client.put(f"{base}/settings", headers=h(), json={"settings": SETTINGS, "audience": LIST})
    await client.post(f"{base}/versions/{v1 + 1}/publish", headers=h())

    opened = await client.put(
        f"{base}/settings",
        headers=h(),
        json={"settings": SETTINGS, "audience": {"mode": "everyone", "numbers": []}},
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["audience"]["mode"] == "everyone"
    # The numbers are kept so going back to the list does not force retyping.
    assert [n["phone"] for n in opened.json()["audience"]["numbers"]] == [
        "+56991919125",
        "+34666261967",
    ]
    await client.post(f"{base}/versions/{v1 + 2}/publish", headers=h())
    assert (await _version(db_session, a["tenant_id"], v1 + 2)).policies["admin_access"][
        "admin_only"
    ] is False

    back = await client.post(f"{base}/versions/{v1 + 1}/rollback", headers=h())
    assert back.status_code == 200, back.text
    assert (await client.get(f"{base}/settings", headers=h())).json()["audience"]["mode"] == "list"


async def test_a_put_without_audience_leaves_admin_access_alone(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"
    v1 = await _stage_and_publish(client, a)
    await client.put(f"{base}/settings", headers=h(), json={"settings": SETTINGS, "audience": LIST})
    again = await client.put(f"{base}/settings", headers=h(), json={"settings": SETTINGS})
    assert again.status_code == 200
    assert again.json()["audience"]["mode"] == "list"
    draft = await _version(db_session, a["tenant_id"], v1 + 1)
    assert draft.policies["admin_access"]["admin_phones"] == ["+56991919125", "+34666261967"]


async def test_bad_numbers_and_empty_lists_are_refused_by_name(client, console_world) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent/settings"
    await _stage_and_publish(client, a)

    bad = await client.put(
        base,
        headers=h(),
        json={
            "settings": SETTINGS,
            "audience": {"mode": "list", "numbers": [{"phone": "+56991919125"}, {"phone": "1234"}]},
        },
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["detail"] == {"code": "audience_invalid_phone", "phone": "1234"}

    empty = await client.put(
        base, headers=h(), json={"settings": SETTINGS, "audience": {"mode": "list", "numbers": []}}
    )
    assert empty.status_code == 422
    assert empty.json()["detail"] == {"code": "audience_empty"}

    # Nothing was saved: the draft (if any) still answers everyone.
    assert (await client.get(base, headers=h())).json()["audience"]["mode"] == "everyone"


async def test_an_admin_only_template_is_locked(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"
    v1 = await _stage_and_publish(client, a)
    await _set_template(db_session, a["tenant_id"], v1, "cobranza_v1")

    got = await client.get(f"{base}/settings", headers=h())
    assert got.json()["audience"]["locked"] is True

    opened = await client.put(
        f"{base}/settings",
        headers=h(),
        json={"settings": SETTINGS, "audience": {"mode": "everyone", "numbers": []}},
    )
    assert opened.status_code == 409, opened.text
    assert opened.json()["detail"] == {"code": "audience_locked"}

    edited = await client.put(
        f"{base}/settings", headers=h(), json={"settings": SETTINGS, "audience": LIST}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["audience"]["locked"] is True


async def test_a_sales_template_is_not_locked(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    v1 = await _stage_and_publish(client, a)
    await _set_template(db_session, a["tenant_id"], v1, "woocommerce_sales_v1")
    got = await client.get(f"/console/clients/{a['ref']}/agent/settings", headers=h())
    assert got.json()["audience"]["locked"] is False
