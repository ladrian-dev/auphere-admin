"""Spec 030 — la persona de un cliente ante la API (Requisito 2).

``require_client_principal`` es la puerta de ``/console/lite/*``. Lo que
fija este archivo:

- los problemas de credencial son 401, igual que en la consola del partner
  (misma firma, misma caducidad, mismo anti-replay);
- una persona del partner NO pasa: no está en ``client_memberships``;
- persona revocada, acceso apagado, partner suspendido, tenant archivado o
  módulo que el cliente no tiene → 403, sin decir cuál;
- ``partners.console_enabled`` NO cuenta: es el interruptor de la consola
  del partner, no la del cliente;
- el cliente sale de la membresía, nunca del token, y el ámbito abre una
  transacción con ``app.tenant_id`` fijado.
"""

from __future__ import annotations

import time
import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.models import ClientAccess, ClientMembership, Partner, Tenant
from tests.conftest import add_client_member, make_client_access, mint_console_token

pytestmark = pytest.mark.asyncio

ME = "/console/lite/me"


async def _client_world(db_session, console_world, *, modules=("panel", "inbox", "usage")):
    w = console_world["a"]
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=modules
    )
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    return w, member


# ── 401: el mismo trato que la consola del partner ─────────────────────


async def test_missing_or_expired_token_is_401(client, db_session, console_world) -> None:
    _w, member = await _client_world(db_session, console_world)
    assert (await client.get(ME)).status_code == 401
    old = member["headers"](issued_at=int(time.time()) - 180)
    assert (await client.get(ME, headers=old)).status_code == 401


async def test_replayed_token_is_401(client, db_session, console_world) -> None:
    _w, member = await _client_world(db_session, console_world)
    headers = member["headers"](jti=uuid.uuid4().hex)
    assert (await client.get(ME, headers=headers)).status_code == 200
    assert (await client.get(ME, headers=headers)).status_code == 401


# ── 403: quién no pasa ─────────────────────────────────────────────────


async def test_partner_member_cannot_use_lite_routes(client, db_session, console_world) -> None:
    w, _ = await _client_world(db_session, console_world)
    resp = await client.get(ME, headers=w["headers"]())
    assert resp.status_code == 403


async def test_client_member_cannot_use_partner_routes(client, db_session, console_world) -> None:
    """La otra mitad de la frontera: el claim ``role`` no abre nada."""
    w, member = await _client_world(db_session, console_world)
    for claim in ("client", "owner"):
        headers = (
            member["headers"]()
            if claim == "client"
            else {
                "Authorization": "Bearer "
                + mint_console_token(
                    user_id=member["user_id"], partner_id=w["partner_id"], role="owner"
                )
            }
        )
        assert (await client.get("/console/me", headers=headers)).status_code == 403


async def test_revoked_member_is_403(client, db_session, console_world) -> None:
    _w, member = await _client_world(db_session, console_world)
    await db_session.execute(
        sa.update(ClientMembership)
        .where(ClientMembership.id == member["membership_id"])
        .values(status="revoked")
    )
    await db_session.commit()
    assert (await client.get(ME, headers=member["headers"]())).status_code == 403


async def test_access_switched_off_is_403(client, db_session, console_world) -> None:
    w, member = await _client_world(db_session, console_world)
    await db_session.execute(
        sa.update(ClientAccess)
        .where(ClientAccess.tenant_id == w["tenant_id"])
        .values(enabled=False)
    )
    await db_session.commit()
    assert (await client.get(ME, headers=member["headers"]())).status_code == 403


async def test_suspended_partner_is_403(client, db_session, console_world) -> None:
    w, member = await _client_world(db_session, console_world)
    await db_session.execute(
        sa.update(Partner).where(Partner.id == w["partner_id"]).values(status="suspended")
    )
    await db_session.commit()
    assert (await client.get(ME, headers=member["headers"]())).status_code == 403


async def test_archived_tenant_is_403(client, db_session, console_world) -> None:
    w, member = await _client_world(db_session, console_world)
    await db_session.execute(
        sa.update(Tenant).where(Tenant.id == w["tenant_id"]).values(status="archived")
    )
    await db_session.commit()
    assert (await client.get(ME, headers=member["headers"]())).status_code == 403


async def test_token_naming_another_partner_is_403(client, db_session, console_world) -> None:
    """El ``partner_id`` del token tiene que ser el de la membresía."""
    _w, member = await _client_world(db_session, console_world)
    other = console_world["b"]
    headers = {
        "Authorization": "Bearer "
        + mint_console_token(
            user_id=member["user_id"], partner_id=other["partner_id"], role="client"
        )
    }
    assert (await client.get(ME, headers=headers)).status_code == 403


async def test_partner_console_switch_does_not_close_the_client_console(
    client, db_session, console_world
) -> None:
    w, member = await _client_world(db_session, console_world)
    await db_session.execute(
        sa.update(Partner).where(Partner.id == w["partner_id"]).values(console_enabled=False)
    )
    await db_session.commit()
    assert (await client.get(ME, headers=member["headers"]())).status_code == 200


# ── módulos y ámbito ───────────────────────────────────────────────────


async def _resolve(test_engine, fake_redis, token: str, *modules: str):
    from nexus_api.core.client_auth import require_client_principal

    dep = require_client_principal(*modules)
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with factory() as session:
        return await dep(authorization=f"Bearer {token}", session=session, redis=fake_redis)


async def test_module_the_client_lacks_is_403(
    db_session, console_world, test_engine, fake_redis
) -> None:
    w, member = await _client_world(db_session, console_world, modules=("panel",))
    token = mint_console_token(user_id=member["user_id"], partner_id=w["partner_id"], role="client")
    with pytest.raises(HTTPException) as exc:
        await _resolve(test_engine, fake_redis, token, "inbox")
    assert exc.value.status_code == 403
    token = mint_console_token(user_id=member["user_id"], partner_id=w["partner_id"], role="client")
    principal = await _resolve(test_engine, fake_redis, token, "panel")
    assert principal.modules == ("panel",)


async def test_principal_carries_the_client_from_the_membership(
    db_session, console_world, test_engine, fake_redis
) -> None:
    w, member = await _client_world(db_session, console_world)
    token = mint_console_token(user_id=member["user_id"], partner_id=w["partner_id"], role="client")
    principal = await _resolve(test_engine, fake_redis, token)
    assert principal.tenant_id == w["tenant_id"]
    assert principal.client_ref == w["ref"]
    assert principal.client_name == "Client A One"
    assert principal.partner.id == w["partner_id"]
    assert principal.modules == ("panel", "inbox", "usage")
    assert principal.actor.startswith("client:persona-")


async def test_lite_scope_opens_a_tenant_scoped_transaction(
    db_session, console_world, test_engine, fake_redis
) -> None:
    from nexus_api.api.console.lite.deps import lite_scope

    w, member = await _client_world(db_session, console_world)
    token = mint_console_token(user_id=member["user_id"], partner_id=w["partner_id"], role="client")
    principal = await _resolve(test_engine, fake_redis, token, "panel")
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with factory() as session:
        gen = lite_scope("panel")(principal=principal, session=session)
        scope = await gen.__anext__()
        seen = await scope.session.scalar(sa.text("SELECT current_setting('app.tenant_id', true)"))
        assert seen == str(w["tenant_id"])
        assert scope.tenant.id == w["tenant_id"]
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
