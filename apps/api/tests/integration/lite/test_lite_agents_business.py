"""Spec 047, T166 — el negocio gestiona lo suyo desde la consola lite y la app
(historia 29; requisitos 50.1, 50.2, 50.3, 50.4, 50.7 y 6.4;
``contracts/lite-app-api.md`` §1 a §4).

- **Agentes** (50.1, 27.6): los mismos códigos, textos y tonos que la consola del
  partner (la lite no recalcula nada); pausar y reanudar un agente o un número,
  con quién y desde dónde (``lite_web`` o ``app``) en el agente, en la auditoría y
  en el aviso al partner. La pausa del sistema no la quita una persona.
- **Negocio** (50.4, 13): horario, fechas especiales, servicios y sedes con
  ``If-Match`` (``428`` sin él, ``412`` con uno viejo), historial con la persona y
  su origen, procedencia y deshacer. El partner recibe ``client.business_changed``.
- **Lo prohibido no tiene ruta** (50.3): crear, archivar o publicar agentes, sus
  instrucciones y su calidad, conectar canales, los datos básicos, las políticas,
  las preguntas frecuentes y la bolsa.
- **Un cliente archivado** cierra la lite y la app con ``client_archived`` (6.4).
- **La Bandeja** dice quién la lleva y por qué espera (50.7).
- **La bolsa** en Consumo, con ``bag_state``, ``days_left`` y ``partner_name``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Agent,
    AuditLog,
    BusinessChange,
    Channel,
    ChannelStatus,
    ClientWallet,
    ConsoleNotification,
    Conversation,
    Partner,
)
from nexus_api.services import agent_states, inbox_lifecycle
from nexus_api.services.business import writes
from tests.conftest import add_client_member, add_client_phone, make_client_access, make_inbox

from ..business._business_world import Biz, if_match, new_business, projected_hours, shifts
from ..clients._client_world import add_agent, add_conversations
from ..wallet._wallet_world import UNIT, money, money_world

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LITE = "/console/lite"
MODULES = ("panel", "inbox", "agents", "business", "usage")


@dataclass
class Shop:
    biz: Biz
    person: dict[str, Any]
    reception: uuid.UUID
    reception_channel: uuid.UUID
    sales: uuid.UUID
    sales_channel: uuid.UUID
    inbox_channel: uuid.UUID
    conversations: list[uuid.UUID]

    def headers(self, **kw: Any) -> dict[str, str]:
        out: dict[str, str] = self.person["headers"](**kw)
        return out


@pytest.fixture
async def shop(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Shop:
    """Barbería Cultor con la Bandeja, Agentes y Negocio; Recepción atiende a
    todos y Ventas mayoristas solo al equipo. Su persona es Valeria Ríos."""
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    reception = await add_agent(db_session, biz.tenant_id, "Recepción")
    sales = await add_agent(db_session, biz.tenant_id, "Ventas mayoristas", audience="team_only")
    inbox = await make_inbox(
        db_session, partner_id=biz.partner_id, tenant_id=biz.tenant_id, modules=MODULES
    )
    assert reception["channel_id"] is not None and sales["channel_id"] is not None
    return Shop(
        biz=biz,
        person=inbox["member"],
        reception=reception["agent_id"],  # type: ignore[arg-type]
        reception_channel=reception["channel_id"],
        sales=sales["agent_id"],  # type: ignore[arg-type]
        sales_channel=sales["channel_id"],
        inbox_channel=inbox["channel_id"],
        conversations=inbox["conversations"],
    )


async def _agents(client: Any, shop: Shop, headers: dict[str, str] | None = None) -> dict[str, Any]:
    resp = await client.get(f"{LITE}/agents", headers=headers or shop.headers())
    assert resp.status_code == 200, resp.text
    return {item["id"]: item for item in resp.json()["items"]}


async def _partner_header(client: Any, shop: Shop, agent_id: uuid.UUID) -> dict[str, Any]:
    resp = await client.get(
        f"/console/clients/{shop.biz.ref}/agents/{agent_id}", headers=shop.biz.headers()
    )
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _notices(db_session: AsyncSession, partner_id: uuid.UUID, kind: str) -> list[Any]:
    async with db_session.begin():
        rows = (
            await db_session.scalars(
                sa.select(ConsoleNotification)
                .where(
                    ConsoleNotification.partner_id == partner_id,
                    ConsoleNotification.kind == kind,
                )
                .order_by(ConsoleNotification.created_at)
            )
        ).all()
    return list(rows)


async def _audit(db_session: AsyncSession, tenant_id: uuid.UUID, action: str) -> list[AuditLog]:
    async with tenant_scoped_session(db_session, tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(AuditLog)
                .where(AuditLog.action == action)
                .order_by(AuditLog.created_at, AuditLog.id)
            )
        ).all()
    return list(rows)


async def _agent_row(db_session: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    async with tenant_scoped_session(db_session, tenant_id):
        agent = await db_session.get(Agent, agent_id, populate_existing=True)
    assert agent is not None
    return agent


async def _channel_row(
    db_session: AsyncSession, tenant_id: uuid.UUID, channel_id: uuid.UUID
) -> Channel:
    async with tenant_scoped_session(db_session, tenant_id):
        channel = await db_session.get(Channel, channel_id, populate_existing=True)
    assert channel is not None
    return channel


# ── Agentes ────────────────────────────────────────────────────────────────


async def test_the_agents_read_the_same_states_as_the_partner_console(
    client: Any, shop: Shop
) -> None:
    """50.1 y 25.5: la lite lee ``visible_state`` de la API, no lo recalcula."""
    agents = await _agents(client, shop)
    assert set(agents) == {str(shop.reception), str(shop.sales)}
    for agent_id in (shop.reception, shop.sales):
        mine = agents[str(agent_id)]
        theirs = await _partner_header(client, shop, agent_id)
        assert mine["visible_state"] == theirs["visible_state"]
    reception = agents[str(shop.reception)]
    assert reception["name"] == "Recepción"
    assert reception["visible_state"]["code"] == "serving"
    assert agents[str(shop.sales)]["visible_state"]["code"] == "testing"
    assert reception["allowed"] == ["pause"]
    # Sus canales, con su estado: el suyo «A todos» y el número sin agente, que
    # atiende el principal (el primero).
    channels = {c["id"]: c for c in reception["channels"]}
    assert channels[str(shop.reception_channel)]["visible_state"]["code"] == "everyone"
    assert channels[str(shop.reception_channel)]["allowed"] == ["pause"]
    assert str(shop.inbox_channel) in channels
    (sales_channel,) = agents[str(shop.sales)]["channels"]
    assert sales_channel["visible_state"]["code"] == "team_only"
    # Nada de lo que la lite no puede hacer.
    assert "tenant_id" not in str(agents)


async def test_pausing_from_the_web_says_who_and_where_and_tells_the_partner(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """Historia 29, escenario 1, y requisitos 27.6 y 27.8."""
    await add_conversations(
        db_session, shop.biz.tenant_id, shop.reception_channel, count=1, escalated=1
    )
    url = f"{LITE}/agents/{shop.reception}"

    ask = await client.post(f"{url}/pause", json={}, headers=shop.headers())
    assert ask.status_code == 409, ask.text
    assert ask.json()["detail"] == {"code": "confirm_required", "open_conversations": 1}

    paused = await client.post(f"{url}/pause", json={"confirm": True}, headers=shop.headers())
    assert paused.status_code == 200, paused.text
    out = paused.json()
    assert out["visible_state"] == {"code": "paused", "tone": "warn", "reason": "manual"}
    assert (out["paused_by_kind"], out["paused_origin"]) == ("client_user", "lite_web")
    assert out["open_conversations"] == 1 and out["allowed"] == ["resume"]

    agent = await _agent_row(db_session, shop.biz.tenant_id, shop.reception)
    assert (agent.lifecycle, agent.pause_reason) == ("paused", "manual")
    assert agent.paused_by_id == shop.person["user_id"]
    header = await _partner_header(client, shop, shop.reception)
    assert header["visible_state"] == out["visible_state"]
    assert (header["paused_by_kind"], header["paused_origin"]) == ("client_user", "lite_web")

    (row,) = await _audit(db_session, shop.biz.tenant_id, "agent.paused")
    assert row.actor.startswith("client:") and "@" in row.actor
    assert row.after_json is not None and row.after_json["origin"] == "lite_web"

    (notice,) = await _notices(db_session, shop.biz.partner_id, "agent.paused")
    assert notice.external_client_ref == shop.biz.ref
    assert notice.payload["agent_id"] == str(shop.reception)
    assert notice.payload["by"] == "Valeria Ríos" and notice.payload["origin"] == "lite_web"

    resumed = await client.post(f"{url}/resume", headers=shop.headers())
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["visible_state"]["code"] == "serving"
    assert resumed.json()["allowed"] == ["pause"]
    (back,) = await _audit(db_session, shop.biz.tenant_id, "agent.resumed")
    assert back.after_json is not None and back.after_json["origin"] == "lite_web"
    (notice,) = await _notices(db_session, shop.biz.partner_id, "agent.resumed")
    assert notice.payload["by"] == "Valeria Ríos"


async def test_pausing_from_the_phone_says_app(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    phone = await add_client_phone(db_session, membership_id=shop.person["membership_id"])
    resp = await client.post(
        f"{LITE}/agents/{shop.sales}/pause", json={"confirm": True}, headers=phone["headers"]()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["paused_origin"] == "app"
    (notice,) = await _notices(db_session, shop.biz.partner_id, "agent.paused")
    assert notice.payload["origin"] == "app"


async def test_a_pause_of_the_system_is_not_lifted_by_a_person(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """27.4: sin saldo se reanuda solo cuando vuelve el saldo."""
    async with tenant_scoped_session(db_session, shop.biz.tenant_id):
        agent = await db_session.get(Agent, shop.reception)
        assert agent is not None
        await agent_states.pause(
            db_session,
            agent,
            reason="no_balance",
            by_kind="system",
            by_id=None,
            origin="system",
            actor="system",
        )
    mine = (await _agents(client, shop))[str(shop.reception)]
    assert mine["visible_state"]["reason"] == "no_balance" and mine["allowed"] == []
    refused = await client.post(f"{LITE}/agents/{shop.reception}/resume", headers=shop.headers())
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "system_pause"
    agent_row = await _agent_row(db_session, shop.biz.tenant_id, shop.reception)
    assert agent_row.pause_reason == "no_balance"


async def test_a_number_pauses_and_resumes_on_its_own(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """27.1: pausar un canal para solo ese número."""
    url = f"{LITE}/channels/{shop.reception_channel}"
    paused = await client.post(f"{url}/pause", headers=shop.headers())
    assert paused.status_code == 200, paused.text
    assert paused.json()["visible_state"]["code"] == "paused"
    assert paused.json()["allowed"] == ["resume"]
    channel = await _channel_row(db_session, shop.biz.tenant_id, shop.reception_channel)
    assert channel.status is ChannelStatus.PAUSED
    assert (channel.paused_by_kind, channel.paused_origin) == ("client_user", "lite_web")
    # El agente no se pausa: su otro número sigue.
    agent = (await _agents(client, shop))[str(shop.reception)]
    theirs = await _partner_header(client, shop, shop.reception)
    assert agent["visible_state"] == theirs["visible_state"]
    assert agent["visible_state"]["code"] != "paused"

    (row,) = await _audit(db_session, shop.biz.tenant_id, "channel.paused")
    assert row.after_json is not None and row.after_json["origin"] == "lite_web"
    (notice,) = await _notices(db_session, shop.biz.partner_id, "channel.paused")
    assert notice.payload["channel_id"] == str(shop.reception_channel)
    assert notice.payload["by"] == "Valeria Ríos"

    resumed = await client.post(f"{url}/resume", headers=shop.headers())
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["visible_state"]["code"] == "everyone"
    channel = await _channel_row(db_session, shop.biz.tenant_id, shop.reception_channel)
    assert channel.status is ChannelStatus.ACTIVE and channel.paused_origin is None
    (notice,) = await _notices(db_session, shop.biz.partner_id, "channel.resumed")
    assert notice.payload["origin"] == "lite_web"


async def test_another_clients_agent_and_number_do_not_exist(
    client: Any, db_session: AsyncSession, shop: Shop, console_world: dict[str, Any]
) -> None:
    other = await add_agent(db_session, console_world["b"]["tenant_id"], "Ajena")
    for path in (
        f"{LITE}/agents/{other['agent_id']}/pause",
        f"{LITE}/agents/{other['agent_id']}/resume",
        f"{LITE}/channels/{other['channel_id']}/pause",
        f"{LITE}/channels/{other['channel_id']}/resume",
    ):
        resp = await client.post(path, json={"confirm": True}, headers=shop.headers())
        assert resp.status_code == 404, f"{path}: {resp.status_code}"
    agent = await _agent_row(db_session, console_world["b"]["tenant_id"], other["agent_id"])  # type: ignore[arg-type]
    assert agent.lifecycle != "paused"


# ── Negocio ────────────────────────────────────────────────────────────────


async def _business(client: Any, shop: Shop) -> dict[str, Any]:
    resp = await client.get(f"{LITE}/business", headers=shop.headers())
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _write(
    client: Any,
    shop: Shop,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    *,
    revision: int | None,
    expect: int = 200,
) -> dict[str, Any]:
    headers = shop.headers()
    if revision is not None:
        headers.update(if_match(revision))
    resp = await client.request(method, f"{LITE}/business{path}", json=body, headers=headers)
    assert resp.status_code == expect, resp.text
    out: dict[str, Any] = resp.json()
    return out


SATURDAY = {
    **{d: shifts(("09:00", "20:00")) for d in ("mon", "tue", "wed", "thu", "fri")},
    "sat": shifts(("10:00", "14:00")),
}


async def test_the_hours_need_if_match_and_carry_the_person_and_where(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """Historia 29, escenario 2, y requisitos 50.2, 50.4, 13.4 y 13.6."""
    before = await _business(client, shop)
    assert set(before) >= {"hours", "special_dates", "services", "locations", "provenance"}
    revision = before["hours"]["revision"]

    await _write(client, shop, "PUT", "/hours", {"days": SATURDAY}, revision=None, expect=428)
    saved = await _write(client, shop, "PUT", "/hours", {"days": SATURDAY}, revision=revision)
    assert saved["label"] and "14:00" in saved["label"]
    stale = await _write(
        client, shop, "PUT", "/hours", {"days": SATURDAY}, revision=revision, expect=412
    )
    assert stale["detail"]["code"] == "revision_conflict"
    # El agente lee el horario nuevo desde el siguiente mensaje (la proyección).
    projected = await projected_hours(db_session, shop.biz.tenant_id)
    assert projected is not None and projected["label"] == saved["label"]

    async with tenant_scoped_session(db_session, shop.biz.tenant_id):
        change = await db_session.scalar(
            sa.select(BusinessChange)
            .where(BusinessChange.section == "hours")
            .order_by(BusinessChange.at.desc())
            .limit(1)
        )
    assert change is not None
    assert (change.actor_kind, change.actor_id, change.origin) == (
        "client_user",
        shop.person["user_id"],
        "lite_web",
    )
    after = await _business(client, shop)
    prov = next(v for k, v in after["provenance"].items() if k.startswith("/hours"))
    assert prov["by"] == {"kind": "client_user", "name": "Valeria Ríos"}
    assert prov["origin"] == "lite_web" and prov["source"] == "person"
    (row,) = await _audit(db_session, shop.biz.tenant_id, "business.section_updated")
    assert row.actor.startswith("client:") and row.after_json is not None
    assert row.after_json["origin"] == "lite_web"

    await writes.drain_after_commit()
    (notice,) = await _notices(db_session, shop.biz.partner_id, "client.business_changed")
    assert notice.payload["sections"] == ["hours"]
    assert (notice.payload["by"], notice.payload["origin"]) == ("Valeria Ríos", "lite_web")


async def test_special_dates_services_and_locations(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """50.1: fechas especiales, servicios (precio y duración) y sedes."""
    view = await _business(client, shop)

    dates = view["special_dates"]
    created = await _write(
        client,
        shop,
        "POST",
        "/special-dates",
        {"name": "Navidad", "from": "2026-12-25", "to": "2026-12-25", "closed": True},
        revision=dates["revision"],
        expect=201,
    )
    (navidad,) = created["items"]
    patched = await _write(
        client,
        shop,
        "PATCH",
        f"/special-dates/{navidad['id']}",
        {"closed": False, "shifts": shifts(("10:00", "13:00"))},
        revision=created["revision"],
    )
    assert patched["items"][0]["shifts"][0]["open"] == "10:00"
    archived = await _write(
        client,
        shop,
        "POST",
        f"/special-dates/{navidad['id']}/archive",
        None,
        revision=patched["revision"],
    )
    assert archived["items"] == []

    services = view["services"]
    corte = await _write(
        client,
        shop,
        "POST",
        "/services",
        {
            "name": "Corte",
            "bookable": True,
            "duration_min": 30,
            "price": {"kind": "amount", "amount_minor": 1500},
        },
        revision=services["revision"],
        expect=201,
    )
    service_id = corte["created_id"]
    priced = await _write(
        client,
        shop,
        "PATCH",
        f"/services/{service_id}",
        {"price": {"kind": "amount", "amount_minor": 1800}, "duration_min": 45},
        revision=corte["revision"],
    )
    item = next(s for s in priced["items"] if s["id"] == service_id)
    assert (item["price"]["amount_minor"], item["duration_min"]) == (1800, 45)
    # El nombre, el equipo y los agentes que lo usan son del partner.
    renamed = await _write(
        client,
        shop,
        "PATCH",
        f"/services/{service_id}",
        {"name": "Otro"},
        revision=priced["revision"],
        expect=422,
    )
    assert renamed["detail"]
    gone = await _write(
        client,
        shop,
        "POST",
        f"/services/{service_id}/archive",
        None,
        revision=priced["revision"],
    )
    assert all(s["id"] != service_id for s in gone["items"])

    locations = view["locations"]
    centro = await _write(
        client,
        shop,
        "POST",
        "/locations",
        {"name": "Centro", "address": "Calle Mayor 1"},
        revision=locations["revision"],
        expect=201,
    )
    location_id = centro["created_id"]
    moved = await _write(
        client,
        shop,
        "PATCH",
        f"/locations/{location_id}",
        {"address": "Calle Mayor 3"},
        revision=centro["revision"],
    )
    assert moved["items"][0]["address"] == "Calle Mayor 3"
    closed = await _write(
        client, shop, "POST", f"/locations/{location_id}/archive", None, revision=moved["revision"]
    )
    assert closed["items"] == []
    back = await _write(
        client, shop, "POST", f"/locations/{location_id}/restore", None, revision=closed["revision"]
    )
    assert [loc["id"] for loc in back["items"]] == [location_id]

    async with tenant_scoped_session(db_session, shop.biz.tenant_id):
        origins = set((await db_session.scalars(sa.select(BusinessChange.origin).distinct())).all())
    assert "lite_web" in origins


async def test_the_last_change_undoes_and_what_is_not_hers_does_not(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """13.3: deshacer su último cambio, con el historial que lo dice."""
    view = await _business(client, shop)
    await _write(
        client, shop, "PUT", "/hours", {"days": SATURDAY}, revision=view["hours"]["revision"]
    )
    view = await _business(client, shop)
    last = view["history"][0]
    assert (last["section"], last["kind"], last["undoable"]) == ("hours", "edit", True)
    assert last["by"] == {"kind": "client_user", "name": "Valeria Ríos"}
    assert last["origin"] == "lite_web"

    undone = await client.post(f"{LITE}/business/history/{last['id']}/undo", headers=shop.headers())
    assert undone.status_code == 200, undone.text
    assert undone.json()["section"] == "hours"
    again = await client.post(f"{LITE}/business/history/{last['id']}/undo", headers=shop.headers())
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_undone"

    # Un cambio de los datos básicos (del partner) no se deshace desde la lite.
    basics = await client.get(
        f"/console/clients/{shop.biz.ref}/business/basics", headers=shop.biz.headers()
    )
    resp = await client.put(
        f"/console/clients/{shop.biz.ref}/business/basics",
        json={"info": "Barbería clásica"},
        headers={**shop.biz.headers(), **if_match(basics.json()["revision"])},
    )
    assert resp.status_code == 200, resp.text
    async with tenant_scoped_session(db_session, shop.biz.tenant_id):
        basics_change = await db_session.scalar(
            sa.select(BusinessChange.id).where(BusinessChange.section == "basics")
        )
    refused = await client.post(
        f"{LITE}/business/history/{basics_change}/undo", headers=shop.headers()
    )
    assert refused.status_code == 404
    assert all(item["section"] != "basics" for item in (await _business(client, shop))["history"])


async def test_a_retried_write_with_the_same_key_is_written_once(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """Contrato lite §0: cada escritura lleva ``Idempotency-Key``. El reintento
    (la red se cortó antes de la respuesta) no repite el alta ni choca con su
    propia revisión: responde lo mismo."""
    view = await _business(client, shop)
    corte = {
        "name": "Corte",
        "bookable": True,
        "duration_min": 30,
        "price": {"kind": "amount", "amount_minor": 1500},
    }

    async def send(method: str, path: str, body: Any, revision: int | None, key: str) -> Any:
        headers = {**shop.headers(), "Idempotency-Key": key}
        if revision is not None:
            headers.update(if_match(revision))
        return await client.request(method, f"{LITE}/business{path}", json=body, headers=headers)

    revision = view["services"]["revision"]
    first = await send("POST", "/services", corte, revision, "alta-corte-1")
    again = await send("POST", "/services", corte, revision, "alta-corte-1")
    assert (first.status_code, again.status_code) == (201, 201), again.text
    assert first.json()["created_id"] == again.json()["created_id"]
    assert [s["name"] for s in again.json()["items"]].count("Corte") == 1
    # Otra clave es otra escritura: con la revisión vieja, 412.
    other = await send("POST", "/services", corte, revision, "alta-corte-2")
    assert other.status_code == 412, other.text

    hours_rev = view["hours"]["revision"]
    saved = await send("PUT", "/hours", {"days": SATURDAY}, hours_rev, "horario-1")
    retried = await send("PUT", "/hours", {"days": SATURDAY}, hours_rev, "horario-1")
    assert (saved.status_code, retried.status_code) == (200, 200), retried.text
    assert retried.json()["revision"] == saved.json()["revision"]
    async with tenant_scoped_session(db_session, shop.biz.tenant_id):
        edits = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(BusinessChange)
            .where(BusinessChange.section == "hours")
        )
    assert edits == 1

    last = (await _business(client, shop))["history"][0]
    undo = f"/history/{last['id']}/undo"
    undone = await send("POST", undo, None, None, "deshacer-1")
    replayed = await send("POST", undo, None, None, "deshacer-1")
    assert (undone.status_code, replayed.status_code) == (200, 200), replayed.text
    assert replayed.json() == undone.json()


async def test_a_location_reads_its_own_hours(client: Any, shop: Shop) -> None:
    """``GET /business/hours?location_id=``: la sede hereda el horario del
    negocio hasta que tiene el suyo. La de otro cliente no existe."""
    view = await _business(client, shop)
    centro = await _write(
        client,
        shop,
        "POST",
        "/locations",
        {"name": "Centro", "address": "Calle Mayor 1"},
        revision=view["locations"]["revision"],
        expect=201,
    )
    url = f"{LITE}/business/hours"
    inherited = await client.get(
        url, params={"location_id": centro["created_id"]}, headers=shop.headers()
    )
    assert inherited.status_code == 200, inherited.text
    assert inherited.json()["inherits"] is True and inherited.headers["ETag"]
    own = await client.put(
        url,
        params={"location_id": centro["created_id"]},
        json={"days": SATURDAY},
        headers={**shop.headers(), **if_match(inherited.json()["revision"])},
    )
    assert own.status_code == 200, own.text
    read = await client.get(
        url, params={"location_id": centro["created_id"]}, headers=shop.headers()
    )
    assert read.json()["inherits"] is False and "14:00" in read.json()["label"]
    nobody = await client.get(
        url, params={"location_id": str(uuid.uuid4())}, headers=shop.headers()
    )
    assert nobody.status_code == 404


async def test_what_the_client_cannot_do_has_no_route(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """50.3: ni crear, archivar o publicar agentes, ni instrucciones, calidad,
    canales, integraciones, datos básicos, políticas, preguntas o la bolsa."""
    agent = shop.reception
    forbidden = [
        ("POST", f"{LITE}/agents"),
        ("POST", f"{LITE}/agents/{agent}/archive"),
        ("POST", f"{LITE}/agents/{agent}/restore"),
        ("POST", f"{LITE}/agents/{agent}/publish"),
        ("PATCH", f"{LITE}/agents/{agent}"),
        ("PATCH", f"{LITE}/agents/{agent}/draft"),
        ("GET", f"{LITE}/agents/{agent}/quality"),
        ("PUT", f"{LITE}/agents/{agent}/quality"),
        ("POST", f"{LITE}/channels"),
        ("POST", f"{LITE}/channels/{shop.reception_channel}/disconnect"),
        ("PUT", f"{LITE}/channels/{shop.reception_channel}/config"),
        ("POST", f"{LITE}/integrations"),
        ("PUT", f"{LITE}/business/basics"),
        ("PUT", f"{LITE}/business/policies"),
        ("POST", f"{LITE}/business/faqs"),
        ("POST", f"{LITE}/business/services/{uuid.uuid4()}/duplicate"),
        ("PUT", f"{LITE}/business/services/{uuid.uuid4()}/agents"),
        ("POST", f"{LITE}/bag/assign"),
        ("POST", f"{LITE}/balance-requests"),
    ]
    for method, path in forbidden:
        resp = await client.request(method, path, json={}, headers=shop.headers())
        assert resp.status_code in (404, 405), f"{method} {path}: {resp.status_code}"

    from nexus_api.main import app

    lite_paths = {
        getattr(r, "path", "") for r in app.routes if getattr(r, "path", "").startswith(LITE)
    }
    for word in ("publish", "quality", "instructions", "bag", "balance", "connect"):
        assert not any(word in p for p in lite_paths), word
    assert not any(p.startswith(f"{LITE}/agents/{{agent_id}}/archive") for p in lite_paths)
    agent_row = await _agent_row(db_session, shop.biz.tenant_id, agent)
    assert agent_row.lifecycle != "archived"


async def test_an_archived_client_closes_the_lite_with_its_code(client: Any, shop: Shop) -> None:
    """6.4: archivar cierra la consola lite y la app."""
    resp = await client.post(f"/console/clients/{shop.biz.ref}/archive", headers=shop.biz.headers())
    assert resp.status_code == 200, resp.text
    for path in (f"{LITE}/agents", f"{LITE}/business", f"{LITE}/me"):
        closed = await client.get(path, headers=shop.headers())
        assert closed.status_code == 403, path
        assert closed.json()["detail"]["code"] == "client_archived", path


async def test_the_sections_follow_the_modules(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """Sin los módulos no hay sección; con la consola nueva vienen por defecto."""
    a = console_world["a"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    person = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    for path in (f"{LITE}/agents", f"{LITE}/business"):
        resp = await client.get(path, headers=person["headers"]())
        assert resp.status_code == 403, path
    me = await client.get(f"{LITE}/me", headers=person["headers"]())
    assert me.json()["nav"] == ["panel", "inbox", "usage"]

    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    me = await client.get(f"{LITE}/me", headers=person["headers"]())
    assert me.json()["nav"] == ["panel", "inbox", "agents", "business", "usage"]
    resp = await client.get(f"{LITE}/agents", headers=person["headers"]())
    assert resp.status_code == 200, resp.text


# ── la Bandeja ─────────────────────────────────────────────────────────────


async def test_the_inbox_says_who_handles_it_and_why_it_waits(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """50.7: «La atiende {agente}» y el motivo de ``events.md`` §2."""
    first = shop.conversations[0]
    async with tenant_scoped_session(db_session, shop.biz.tenant_id):
        conv = await db_session.get(Conversation, first)
        assert conv is not None
        await inbox_lifecycle.mark_waiting_reason(db_session, conv, reason="paused_agent")

    listed = await client.get(f"{LITE}/inbox/conversations", headers=shop.headers())
    assert listed.status_code == 200, listed.text
    items = {i["id"]: i for i in listed.json()["items"]}
    item = items[str(first)]
    assert item["handled_by_agent"] == {"id": str(shop.reception), "name": "Recepción"}
    assert item["waiting_reason"] == "paused_agent"
    other = items[str(shop.conversations[1])]
    assert other["handled_by_agent"]["name"] == "Recepción" and other["waiting_reason"] is None

    detail = await client.get(f"{LITE}/inbox/conversations/{first}", headers=shop.headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["handled_by_agent"] == {"id": str(shop.reception), "name": "Recepción"}
    assert detail.json()["waiting_reason"] == "paused_agent"


# ── la bolsa ───────────────────────────────────────────────────────────────


async def test_usage_says_the_bag_state_days_left_and_whom_to_ask(
    client: Any, db_session: AsyncSession
) -> None:
    """``lite-app-api.md`` §4: la misma cifra que el partner, sin «Pedir saldo»."""
    world = await money_world(db_session)
    assigned = await client.post(
        f"/console/clients/{world.es.ref}/bag/assign",
        json={"amount": money(10 * UNIT, "EUR")},
        headers=world.headers(),
    )
    assert assigned.status_code == 200, assigned.text
    await make_client_access(
        db_session, partner_id=world.partner_id, tenant_id=world.es.tenant_id, modules=MODULES
    )
    person = await add_client_member(
        db_session, partner_id=world.partner_id, tenant_id=world.es.tenant_id
    )

    summary = await client.get(f"{LITE}/usage/summary", headers=person["headers"]())
    assert summary.status_code == 200, summary.text
    out = summary.json()
    assert out["bag_state"] == "ok"
    assert out["days_left"] is None  # menos de 3 días de consumo
    assert out["partner_name"] == "Agencia del dinero"
    assert out["balance"]["currency"] == "EUR"
    assert out["balance"]["remaining_cents"] == 1000

    # La bolsa es una tabla del cliente (garantía 1): se escribe con su contexto.
    async with tenant_scoped_session(db_session, world.es.tenant_id):
        await db_session.execute(
            sa.update(ClientWallet)
            .where(ClientWallet.tenant_id == world.es.tenant_id)
            .values(balance_micros=0)
        )
    empty = (await client.get(f"{LITE}/usage/summary", headers=person["headers"]())).json()
    assert empty["bag_state"] == "empty"
    assert "balance_request" not in str(empty) and "request" not in empty
