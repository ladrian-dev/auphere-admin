"""Spec 085, isolation guarantee 1 — an owner link connects only in its client.

The public page has no account: the link's token decides the client, and the
connection runs under that client's tenant scope. Checked here, against the
real routes:

1. A link of client A connects the account in A, never in B.
2. A pending account choice begun by link L1 is not completed by link L2 of
   the same client.
3. A choice begun in the console is not completed from a link, nor the other
   way round.
4. No public route of the owner page (``/console/channel-signup/*``, swept
   from the router, not listed by hand) accepts ``tenant_id`` or returns it,
   and the bodies refuse one.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute
from nexus_channels.meta_social import MetaSocialClient

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, Channel, ChannelSignupLink, Partner
from nexus_api.main import app
from nexus_api.services import meta_social_service
from nexus_api.services.channel_signup_links import mint_link
from tests.conftest import console_headers
from tests.unit.test_endpoint_console_meta_social import IG_ID, FakeGraph

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

PREFIX = "/console/channel-signup"
OTHER_IG = "17841400000000778"
TENANT_WORDS = {"tenant_id", "tenantid", "tenant", "partner_id", "partnerid", "partner"}


def _svc() -> dict[str, str]:
    return console_headers(user_id="console-bff", partner_id=None, service=True)


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    """Meta: the fake Graph of spec 049's tests behind the real client."""
    fake = FakeGraph()
    client = MetaSocialClient("dev-meta-app-secret-change-me", transport=httpx.MockTransport(fake))
    monkeypatch.setattr(meta_social_service, "_client", client)
    return fake


async def _instagram_for(db_session: Any, *worlds: dict[str, Any]) -> None:
    for w in worlds:
        await db_session.execute(
            sa.update(Partner)
            .where(Partner.id == w["partner_id"])
            .values(beta_channels=["instagram"])
        )
    await db_session.commit()


async def _link(tenant_id: uuid.UUID, *, agent_id: uuid.UUID | None = None) -> str:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        minted = await mint_link(
            s,
            tenant_id=tenant_id,
            channel="instagram",
            actor="console:test@example.com",
            agent_id=agent_id,
        )
        return minted.token


async def _agent(db_session: Any, tenant_id: uuid.UUID) -> uuid.UUID:
    agent_id = uuid.uuid4()
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(
            Agent(id=agent_id, tenant_id=tenant_id, name="Ventas", lifecycle="published")
        )
    await db_session.commit()
    return agent_id


def _two_accounts(fake: FakeGraph) -> None:
    fake.instagram_accounts = [
        {"id": IG_ID, "username": "demo.store"},
        {"id": OTHER_IG, "username": "other"},
    ]


async def _channels_of(db_session: Any, tenant_id: uuid.UUID) -> list[Channel]:
    return list(
        (await db_session.scalars(sa.select(Channel).where(Channel.tenant_id == tenant_id))).all()
    )


async def test_a_link_connects_in_its_own_client_only(
    client, console_world, db_session, graph
) -> None:
    a, b = console_world["a"], console_world["b"]
    await _instagram_for(db_session, a, b)
    token = await _link(a["tenant_id"])

    # A body naming another client is refused before anything runs.
    smuggled = await client.post(
        f"{PREFIX}/{token}/meta-social",
        headers=_svc(),
        json={"code": "CODE", "tenant_id": str(b["tenant_id"])},
    )
    assert smuggled.status_code == 422, smuggled.text

    done = await client.post(f"{PREFIX}/{token}/meta-social", headers=_svc(), json={"code": "CODE"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "connected"
    assert "tenant_id" not in done.json()

    db_session.expire_all()
    [channel] = await _channels_of(db_session, a["tenant_id"])
    assert channel.tenant_id == a["tenant_id"] and channel.provider_identifier == IG_ID
    assert await _channels_of(db_session, b["tenant_id"]) == []


async def test_a_choice_begun_by_one_link_is_not_completed_by_another(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _instagram_for(db_session, a)
    _two_accounts(graph)
    first = await _link(a["tenant_id"])
    # The agent's own link of the same channel: alive next to the client's.
    second = await _link(a["tenant_id"], agent_id=await _agent(db_session, a["tenant_id"]))

    began = await client.post(f"{PREFIX}/{first}/meta-social", headers=_svc(), json={"code": "C"})
    assert began.status_code == 200, began.text
    assert began.json()["status"] == "choose"
    nonce = began.json()["nonce"]

    stolen = await client.post(
        f"{PREFIX}/{second}/meta-social/complete",
        headers=_svc(),
        json={"nonce": nonce, "account_id": OTHER_IG},
    )
    assert stolen.status_code == 409, stolen.text
    assert stolen.json()["detail"]["code"] == "pending_expired"
    db_session.expire_all()
    assert await _channels_of(db_session, a["tenant_id"]) == [], "nothing connects"

    # The link that began it still completes it.
    done = await client.post(
        f"{PREFIX}/{first}/meta-social/complete",
        headers=_svc(),
        json={"nonce": nonce, "account_id": OTHER_IG},
    )
    assert done.status_code == 200, done.text
    db_session.expire_all()
    [channel] = await _channels_of(db_session, a["tenant_id"])
    assert channel.provider_identifier == OTHER_IG


async def test_console_and_link_choices_do_not_cross(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _instagram_for(db_session, a)
    _two_accounts(graph)
    console_url = f"/console/clients/{a['ref']}/channels/instagram/connect"

    # Begun in the console → not from a link.
    in_console = await client.post(console_url, headers=a["headers"](), json={"code": "C"})
    assert in_console.json()["status"] == "choose", in_console.text
    token = await _link(a["tenant_id"])
    from_link = await client.post(
        f"{PREFIX}/{token}/meta-social/complete",
        headers=_svc(),
        json={"nonce": in_console.json()["nonce"], "account_id": IG_ID},
    )
    assert from_link.status_code == 409, from_link.text
    assert from_link.json()["detail"]["code"] == "pending_expired"

    # Begun from a link → not in the console.
    by_link = await client.post(f"{PREFIX}/{token}/meta-social", headers=_svc(), json={"code": "C"})
    assert by_link.json()["status"] == "choose", by_link.text
    in_console_again = await client.post(
        f"{console_url}/complete",
        headers=a["headers"](),
        json={"nonce": by_link.json()["nonce"], "account_id": IG_ID},
    )
    assert in_console_again.status_code == 409, in_console_again.text
    assert in_console_again.json()["detail"]["code"] == "pending_expired"

    db_session.expire_all()
    assert await _channels_of(db_session, a["tenant_id"]) == []
    link_row = await db_session.scalar(sa.select(ChannelSignupLink))
    assert link_row is not None and link_row.consumed_at is None, "the link still works"


# ── 4. The owner page's routes, swept from the router ──────────────────────


def _owner_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith(PREFIX)]


def _properties(schema: dict[str, Any], defs: dict[str, Any], seen: set[str]) -> set[str]:
    """Every property name reachable from ``schema``, through ``$ref``s."""
    names: set[str] = set()
    ref = schema.get("$ref")
    if isinstance(ref, str):
        key = ref.rsplit("/", 1)[-1]
        if key in seen:
            return names
        seen.add(key)
        return _properties(defs.get(key, {}), defs, seen)
    for name, sub in (schema.get("properties") or {}).items():
        names.add(name.lower())
        names |= _properties(sub, defs, seen)
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            names |= _properties(schema[key], defs, seen)
    for key in ("anyOf", "allOf", "oneOf"):
        for sub in schema.get(key) or []:
            names |= _properties(sub, defs, seen)
    return names


def test_the_owner_page_routes_never_take_nor_return_a_tenant() -> None:
    routes = _owner_routes()
    assert any("meta-social" in r.path for r in routes), (
        "the sweep must reach the Instagram / Messenger routes of spec 085"
    )
    spec = app.openapi()
    defs = spec.get("components", {}).get("schemas", {})
    for route in routes:
        for method in route.methods - {"HEAD", "OPTIONS"}:
            op = spec["paths"][route.path][method.lower()]
            params = {p["name"].lower() for p in op.get("parameters", [])}
            assert not params & TENANT_WORDS, f"{method} {route.path} takes {params & TENANT_WORDS}"
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {})
            taken = _properties(body.get("schema", {}), defs, set())
            assert not taken & TENANT_WORDS, f"{method} {route.path} body takes a tenant"
            for code, answer in op.get("responses", {}).items():
                if not code.startswith("2"):
                    continue
                schema = answer.get("content", {}).get("application/json", {}).get("schema", {})
                given = _properties(schema, defs, set())
                assert "tenant_id" not in given and "partner_id" not in given, (
                    f"{method} {route.path} returns a tenant"
                )
