"""Spec 056, T021 — Agentes y Negocio fuera de la consola del cliente
(historia 2; requisitos 2.1, 2.5 y 2.9; enmienda la spec 047, R50.1, R50.2 y
R50.4 en la parte del cliente).

- **Las rutas siguen montadas** (research R2): borradas responderían 404, y lo que
  pide el requisito 2.5 es el 403 de un módulo que no se tiene. Las 19 de
  ``lite/agents.py`` y ``lite/business.py`` lo dan, con la credencial web y con la
  del teléfono, aunque el partner tenga la consola nueva.
- **Ningún cliente las tiene**: ni por defecto (``/me.nav``) ni porque se guarden
  (``set_access`` los rechaza con ``unknown_module``, desde el panel —
  ``tests/unit/test_admin_client_access.py``— y desde el partner —
  ``tests/integration/console/test_client_access_partner.py``).
- **El partner sigue** pausando y reanudando sus agentes y números y editando la
  ficha desde la consola de partners (2.9); lo fijan ``tests/integration/business/*``
  y las pruebas de agentes del partner, que no cambian.

Lo que no es de Agentes ni de Negocio se queda: lo prohibido no tiene ruta (50.3),
un cliente archivado cierra la lite con su código (6.4), la Bandeja dice quién la
lleva y por qué espera (50.7) y la bolsa en Consumo.
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
from nexus_api.db.models import ClientWallet, Conversation, Partner
from nexus_api.services import inbox_lifecycle
from tests.conftest import add_client_member, add_client_phone, make_client_access, make_inbox
from tests.isolation.test_console_scope import _console_routes
from tests.isolation.test_lite_client_vs_client import is_retired

from ..business._business_world import Biz, new_business
from ..clients._client_world import add_agent
from ..wallet._wallet_world import UNIT, money, money_world

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LITE = "/console/lite"
#: Todo lo que hoy se le puede dar a un cliente salvo Reservas, que hace de módulo
#: ausente con el que comparar.
MODULES = ("panel", "inbox", "usage")
#: Un módulo que la persona no tiene.
ABSENT = f"{LITE}/reservas/settings"


@dataclass
class Shop:
    biz: Biz
    person: dict[str, Any]
    reception: uuid.UUID
    reception_channel: uuid.UUID
    sales: uuid.UUID
    inbox_channel: uuid.UUID
    conversations: list[uuid.UUID]

    def headers(self, **kw: Any) -> dict[str, str]:
        out: dict[str, str] = self.person["headers"](**kw)
        return out


@pytest.fixture
async def shop(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Shop:
    """Barbería Cultor con la Bandeja; Recepción atiende a todos y Ventas
    mayoristas solo al equipo. Su persona es Valeria Ríos."""
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
        inbox_channel=inbox["channel_id"],
        conversations=inbox["conversations"],
    )


def _retired() -> list[tuple[str, str]]:
    return sorted(
        (method, r.path)
        for r in _console_routes()
        if r.path.startswith(LITE) and is_retired(r)
        for method in r.methods
        if method != "HEAD"
    )


def _fill(path: str, shop: Shop) -> str:
    """Los parámetros con objetos reales del propio cliente: ni siendo suyos."""
    own = {
        "agent_id": shop.reception,
        "channel_id": shop.reception_channel,
    }
    for seg in [s[1:-1] for s in path.split("/") if s.startswith("{")]:
        path = path.replace("{" + seg + "}", str(own.get(seg, uuid.uuid4())))
    return path


# ── Agentes y Negocio, retirados ───────────────────────────────────────────


async def test_the_nineteen_routes_are_still_mounted() -> None:
    """Research R2: no se borran, para que respondan 403 y no 404."""
    routes = _retired()
    assert len(routes) == 19, routes
    assert ("GET", f"{LITE}/agents") in routes
    assert ("POST", f"{LITE}/agents/{{agent_id}}/pause") in routes
    assert ("PUT", f"{LITE}/business/hours") in routes


@pytest.mark.parametrize(("method", "path"), _retired())
async def test_every_route_answers_the_absent_module_403(
    method: str, path: str, client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """2.5: lo mismo que a un módulo que no tiene, byte a byte, también con la
    consola nueva del partner (que antes los daba por defecto) y con el teléfono."""
    partner = await db_session.get(Partner, shop.biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    phone = await add_client_phone(db_session, membership_id=shop.person["membership_id"])

    url = _fill(path, shop)
    body = None if method == "GET" else {"confirm": True}
    for headers in (shop.headers, phone["headers"]):
        absent = await client.get(ABSENT, headers=headers())
        resp = await client.request(
            method, url, json=body, headers={**headers(), "If-Match": '"1"'}
        )
        assert absent.status_code == 403, absent.text
        assert resp.status_code == 403, f"{method} {path}: {resp.status_code} {resp.text[:200]}"
        assert resp.content == absent.content, path


async def test_nothing_changes_behind_the_403(
    client: Any, db_session: AsyncSession, shop: Shop
) -> None:
    """Pausar desde la lite no pausa: la dependencia corta antes que la ruta."""
    from nexus_api.db.models import Agent

    resp = await client.post(
        f"{LITE}/agents/{shop.reception}/pause", json={"confirm": True}, headers=shop.headers()
    )
    assert resp.status_code == 403
    async with tenant_scoped_session(db_session, shop.biz.tenant_id):
        agent = await db_session.get(Agent, shop.reception, populate_existing=True)
    assert agent is not None and agent.lifecycle != "paused"


async def test_the_menu_no_longer_brings_them(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """2.1: ni por defecto con la consola nueva ni guardados."""
    a = console_world["a"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    person = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    me = await client.get(f"{LITE}/me", headers=person["headers"]())
    assert me.json()["nav"] == ["panel", "inbox", "usage"]

    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    me = await client.get(f"{LITE}/me", headers=person["headers"]())
    assert me.json()["nav"] == ["panel", "inbox", "usage"]
    for path in (f"{LITE}/agents", f"{LITE}/business"):
        resp = await client.get(path, headers=person["headers"]())
        assert resp.status_code == 403, path


# ── lo que no es de Agentes ni de Negocio ──────────────────────────────────


async def test_what_the_client_cannot_do_has_no_route(client: Any, shop: Shop) -> None:
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


async def test_an_archived_client_closes_the_lite_with_its_code(client: Any, shop: Shop) -> None:
    """6.4: archivar cierra la consola lite y la app."""
    resp = await client.post(f"/console/clients/{shop.biz.ref}/archive", headers=shop.biz.headers())
    assert resp.status_code == 200, resp.text
    for path in (f"{LITE}/home", f"{LITE}/inbox/conversations", f"{LITE}/me"):
        closed = await client.get(path, headers=shop.headers())
        assert closed.status_code == 403, path
        assert closed.json()["detail"]["code"] == "client_archived", path


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
