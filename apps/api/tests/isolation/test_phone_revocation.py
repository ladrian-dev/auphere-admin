"""Spec 031 · R15.3, R7.2, R9.3, CE-007 — un teléfono revocado deja de leer
y deja de recibir avisos (tarea T032).

Barrido, no enumeración: para **cada** uno de los disparadores que cierran
un teléfono, la siguiente petición del teléfono falla (401/403), la línea en
vivo no vuelve a abrirse y el siguiente reparto de avisos no le entrega nada.
Si mañana aparece un séptimo disparador, se añade a ``TRIGGERS`` y hereda las
tres comprobaciones.

La línea en vivo se comprueba al abrirla; una ya abierta no vuelve a pasar por
la puerta. Por eso la del teléfono se corta sola dentro del plazo de R7.2 y, al
reconectar, la puerta decide otra vez.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.responses import StreamingResponse

from nexus_api.api.console.lite import inbox_stream as stream_route
from nexus_api.db.models import (
    ClientMembership,
    ClientPhone,
    Conversation,
    ConversationStatus,
    Partner,
    PartnerStatus,
    Tenant,
    TenantStatus,
)
from nexus_api.services import operator_identity, principal_access, push_events, push_fanout
from tests.conftest import add_client_phone, console_headers, make_console_account, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

STREAM = "/console/lite/inbox/stream"


@pytest.fixture
def short_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """The phone's line bound and the heartbeat in fractions of a second, and
    the SSE response swapped for one that returns every frame when the line
    ends — so a line that never ends shows up as a timeout, not a hang."""
    monkeypatch.setattr(stream_route, "PHONE_LINE_SECONDS", 0.3, raising=False)
    monkeypatch.setattr(stream_route, "HEARTBEAT_SECONDS", 0.05)

    class WholeLine(StreamingResponse):
        def __init__(self, gen: Any) -> None:
            async def frames() -> Any:
                async for event in gen:
                    yield json.dumps(event) + "\n"

            super().__init__(frames(), media_type="application/x-ndjson")

    monkeypatch.setattr(stream_route, "EventSourceResponse", WholeLine)


@pytest.fixture
def identity(test_engine) -> async_sessionmaker:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture
async def person(db_session, console_world, admin_headers) -> dict[str, Any]:
    """A client with Bandeja, an escalated conversation, and one person (a real
    console account, so a password reset can reach them) with a phone that has
    a notice destination."""
    w = console_world["a"]
    box = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    account = await make_console_account(db_session)
    membership_id = uuid.uuid4()
    db_session.add(
        ClientMembership(
            id=membership_id,
            partner_id=w["partner_id"],
            tenant_id=w["tenant_id"],
            user_id=str(account),
            email=f"revocada-{membership_id.hex[:6]}@cliente.test",
            status="active",
        )
    )
    await db_session.commit()
    phone = await add_client_phone(db_session, membership_id=membership_id)
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == phone["phone_id"])
        .values(
            push_provider="apns",
            push_token="c" * 64,
            push_token_updated_at=datetime.now(UTC),
            apns_environment="sandbox",
        )
    )
    conv = box["conversations"][0]
    await db_session.execute(
        sa.update(Conversation)
        .where(Conversation.id == conv)
        .values(status=ConversationStatus.ESCALATED, agent_active=False, assigned_user_id=None)
    )
    await db_session.commit()
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
        )
    return {
        "w": w,
        "account": account,
        "membership_id": membership_id,
        "phone": phone,
        "conv": conv,
        "web": lambda: console_headers(
            user_id=str(account), partner_id=w["partner_id"], role="client"
        ),
        "admin": {**admin_headers, "X-Operator-Id": str(op.id)},
    }


Trigger = Callable[[Any, Any, dict[str, Any]], Awaitable[None]]


async def _signed_out(client, _db, p) -> None:
    r = await client.delete("/console/lite/phones/current", headers=p["phone"]["headers"]())
    assert r.status_code == 204, r.text


async def _closed_by_person(client, _db, p) -> None:
    r = await client.delete(f"/console/lite/phones/{p['phone']['phone_id']}", headers=p["web"]())
    assert r.status_code == 204, r.text


async def _closed_by_auphere(client, _db, p) -> None:
    base = f"/admin/tenants/{p['w']['tenant_id']}/client-members/{p['membership_id']}"
    r = await client.delete(f"{base}/phones/{p['phone']['phone_id']}", headers=p["admin"])
    assert r.status_code == 204, r.text


async def _access_disabled(client, _db, p) -> None:
    r = await client.put(
        f"/admin/tenants/{p['w']['tenant_id']}/client-access",
        headers=p["admin"],
        json={"enabled": False, "modules": ["panel", "inbox", "usage"]},
    )
    assert r.status_code == 200, r.text


async def _member_removed(client, _db, p) -> None:
    r = await client.post(
        f"/admin/tenants/{p['w']['tenant_id']}/client-members/{p['membership_id']}/revoke",
        headers=p["admin"],
    )
    assert r.status_code == 204, r.text


async def _password_reset(_client, db, p) -> None:
    async with db.begin():
        await principal_access.revoke_all_access(
            db, principal_id=p["account"], reason="password_reset", actor="system"
        )


async def _client_archived(_client, db, p) -> None:
    """El partner archiva al cliente desde su consola: el teléfono deja de leer
    y **también** de recibir lo que estuviera pendiente."""
    await db.execute(
        sa.update(Tenant)
        .where(Tenant.id == p["w"]["tenant_id"])
        .values(status=TenantStatus.ARCHIVED)
    )
    await db.commit()


async def _partner_suspended(_client, db, p) -> None:
    await db.execute(
        sa.update(Partner)
        .where(Partner.id == p["w"]["partner_id"])
        .values(status=PartnerStatus.SUSPENDED.value)
    )
    await db.commit()


TRIGGERS: dict[str, Trigger] = {
    "signed_out": _signed_out,
    "closed_by_person": _closed_by_person,
    "closed_by_auphere": _closed_by_auphere,
    "access_disabled": _access_disabled,
    "member_removed": _member_removed,
    "password_reset": _password_reset,
    "client_archived": _client_archived,
    "partner_suspended": _partner_suspended,
}


async def test_an_open_line_on_the_phone_ends_within_the_bound(client, person, short_line) -> None:
    """R7.2, «en menos de 15 minutos»: lo que se cierre mientras la línea está
    abierta deja de llegar, como tarde, cuando la línea se corta sola."""
    r = await asyncio.wait_for(client.get(STREAM, headers=person["phone"]["headers"]()), timeout=5)
    assert r.status_code == 200, r.text
    frames = [json.loads(line)["event"] for line in r.text.splitlines()]
    assert frames[0] == "ready"
    assert set(frames[1:]) <= {"ping"}


async def test_the_web_line_is_not_cut(client, person, short_line) -> None:
    """La consola web no cambia (spec 031): su línea, la de la BFF, sigue
    abierta mientras el navegador la quiera."""
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(client.get(STREAM, headers=person["web"]()), timeout=0.8)


@pytest.mark.parametrize("trigger", sorted(TRIGGERS))
async def test_after_each_trigger_the_phone_neither_reads_nor_gets_notices(
    client, db_session, scoped_session_factory, identity, person, short_line, trigger: str
) -> None:
    p = person
    before = await client.get("/console/lite/me", headers=p["phone"]["headers"]())
    assert before.status_code == 200, before.text

    await TRIGGERS[trigger](client, db_session, p)

    after = await client.get("/console/lite/me", headers=p["phone"]["headers"]())
    assert after.status_code in (401, 403), f"{trigger}: still reads ({after.status_code})"
    line = await asyncio.wait_for(client.get(STREAM, headers=p["phone"]["headers"]()), timeout=5)
    assert line.status_code in (401, 403), f"{trigger}: the line reopens ({line.status_code})"

    tid = p["w"]["tenant_id"]
    async with db_session.begin():
        await push_events.enqueue(
            db_session,
            tenant_id=tid,
            kind="inbox.waiting",
            conversation_id=p["conv"],
            dedupe_key=f"rev:{trigger}",
        )
    session = await scoped_session_factory(tid)
    try:
        out = await push_fanout.claim(session, identity)
        await session.commit()
    finally:
        await session.close()
    assert p["phone"]["phone_id"] not in {o.phone_id for o in out}, f"{trigger}: still notified"
