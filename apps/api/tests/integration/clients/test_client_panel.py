"""Spec 047, T066 — el Panel del cliente cuenta cómo va (historia 16, requisito 14).

``GET /console/clients/{ref}/panel`` (``contracts/console-api.md`` §2), con los
bloques de ``services/console_home_blocks.py``. Hasta la ola 7 la bolsa se lee
de ``partner_allocations`` (US$, 1 crédito = cien milésimas de US$):

- **la bolsa**: lo que queda, lo consumido de lo asignado y su porcentaje;
- **los días** al ritmo de los últimos 7 días completos, solo con 3 días o más de
  consumo (14.2);
- **la barra por agente** y **los avisos** del 80 % y del 100 %;
- **el mes**, con su periodo: conversaciones, resueltas sin persona y pasadas a una;
- **los 4 agentes que más consumen**, con su consumo, sus conversaciones, lo que
  sale cada conversación y su tope;
- **la primera carencia** de la ficha (horario, servicios, sedes, documentos y
  redes), que no aparece con la ficha completa;
- **el cuadre** al céntimo con la consola lite;
- **la tarjeta de lectura**.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import TenantStatus
from nexus_api.services.business.sections import Actor, touch_section
from nexus_api.services.lite_home import lite_home

from ._client_world import (
    add_agent,
    add_conversations,
    add_spend,
    new_client,
    roomy,
    set_bag,
    tenant_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

USD = 100_000
ANA = Actor(kind="partner_member", id="ana", origin="console")


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    await roomy(db_session, console_world)
    return console_world


def _day(n: int) -> datetime:
    """Hace ``n`` días completos (mediodía UTC)."""
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    return today - timedelta(days=n)


async def _cultor(
    client: Any, db_session: AsyncSession, world: dict[str, Any], **body: Any
) -> dict[str, Any]:
    a = world["a"]
    created = await new_client(
        client, a["headers"](), name="Barbería Cultor", niche="Barbería", **body
    )
    tenant_id = await tenant_of(db_session, a["partner_id"], created["ref"])
    return {
        "ref": created["ref"],
        "tenant_id": tenant_id,
        "url": f"/console/clients/{created['ref']}/panel",
        "created": created,
    }


async def _panel(client: Any, headers: dict[str, str], url: str) -> dict[str, Any]:
    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def test_the_bag_says_what_is_left_and_for_how_many_days(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 1: 10 US$ en los últimos 7 días y 6 en la bolsa → unos 4 días."""
    a = world["a"]
    c = await _cultor(client, db_session, world)
    agent = await add_agent(db_session, c["tenant_id"], "Recepción")
    await set_bag(db_session, a["partner_id"], c["tenant_id"], cap=16 * USD, remaining=6 * USD)
    for n in (1, 2, 3, 5, 7):
        await add_spend(
            db_session,
            a["partner_id"],
            c["tenant_id"],
            2 * USD,
            agent_id=agent["agent_id"],
            at=_day(n),
        )
    # Lo de hoy no cuenta en el ritmo: el día no está completo.
    await add_spend(db_session, a["partner_id"], c["tenant_id"], 50_000, agent_id=agent["agent_id"])

    bag = (await _panel(client, a["headers"](), c["url"]))["bag"]
    assert bag["balance"] == {"amount_micros": 6 * USD, "currency": "USD"}
    assert bag["assigned"] == {"amount_micros": 16 * USD, "currency": "USD"}
    assert bag["spent"] == {"amount_micros": 10 * USD, "currency": "USD"}
    assert bag["pct_spent"] == 62.5
    assert bag["days_left"] == 4.2 and round(bag["days_left"]) == 4
    assert bag["days_estimable"] is True
    assert bag["alerts"] == []
    assert bag["state"] in ("ok", "not_enough")


async def test_with_fewer_than_three_days_there_is_no_estimate(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    await set_bag(db_session, a["partner_id"], c["tenant_id"], cap=20 * USD, remaining=18 * USD)
    for n in (1, 2):
        await add_spend(db_session, a["partner_id"], c["tenant_id"], USD, at=_day(n))
    bag = (await _panel(client, a["headers"](), c["url"]))["bag"]
    assert bag["days_left"] is None and bag["days_estimable"] is False


async def test_the_80_and_100_percent_warnings(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 2: el 85 % consumido trae el aviso ámbar; a cero, el de sin saldo."""
    a = world["a"]
    c = await _cultor(client, db_session, world)
    await set_bag(db_session, a["partner_id"], c["tenant_id"], cap=20 * USD, remaining=3 * USD)
    bag = (await _panel(client, a["headers"](), c["url"]))["bag"]
    assert bag["pct_spent"] == 85.0 and bag["alerts"] == ["warn_80"] and bag["state"] == "low"
    await set_bag(db_session, a["partner_id"], c["tenant_id"], cap=20 * USD, remaining=0)
    panel = await _panel(client, a["headers"](), c["url"])
    assert panel["bag"]["alerts"] == ["empty"] and panel["bag"]["state"] == "empty"
    assert panel["attention"]["reasons"][0]["code"] == "no_balance"


async def test_the_bar_by_agent_the_month_and_the_four_that_spend_most(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    await set_bag(db_session, a["partner_id"], c["tenant_id"], cap=100 * USD, remaining=50 * USD)
    agents = []
    for i, (name, spend) in enumerate(
        (("Citas", 8), ("Ventas", 5), ("Cobranza", 3), ("Soporte", 2), ("Recordatorios", 1))
    ):
        agent = await add_agent(
            db_session, c["tenant_id"], name, created_at=datetime.now(UTC) - timedelta(hours=10 - i)
        )
        agents.append(agent)
        await add_spend(
            db_session,
            a["partner_id"],
            c["tenant_id"],
            spend * USD,
            agent_id=agent["agent_id"],
            at=datetime.now(UTC) - timedelta(minutes=30),
        )
    await add_conversations(
        db_session, c["tenant_id"], agents[0]["channel_id"], count=4, escalated=1
    )
    await add_conversations(
        db_session, c["tenant_id"], agents[1]["channel_id"], count=1, escalated=1
    )

    panel = await _panel(client, a["headers"](), c["url"])
    bar = panel["spend_by_agent"]
    assert [x["name"] for x in bar] == ["Citas", "Ventas", "Cobranza", "Soporte", "Recordatorios"]
    assert sum(x["spent"]["amount_micros"] for x in bar) == 19 * USD
    assert bar[0]["share_pct"] == round(8 / 19 * 100, 1)

    month = panel["month"]
    assert month["conversations"] == 5 and month["handed_to_person"] == 2
    assert month["resolved_without_person"] == 3 and month["resolved_pct"] == 60.0
    now = datetime.now(UTC)
    assert month["period_start"] == now.replace(day=1).date().isoformat()
    assert month["period_end"] >= now.date().isoformat()

    top = panel["top_agents"]
    assert [x["name"] for x in top] == ["Citas", "Ventas", "Cobranza", "Soporte"]
    citas = top[0]
    assert citas["spent"] == {"amount_micros": 8 * USD, "currency": "USD"}
    assert citas["conversations"] == 4
    assert citas["spend_per_conversation"] == {"amount_micros": 2 * USD, "currency": "USD"}
    assert citas["cap"] is None  # el tope por agente llega con la ola 7
    assert top[2]["conversations"] == 0 and top[2]["spend_per_conversation"] is None
    assert panel["agents_total"] == 5


async def test_without_agents_the_block_explains_and_offers_the_first(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 4."""
    a = world["a"]
    c = await _cultor(client, db_session, world)
    panel = await _panel(client, a["headers"](), c["url"])
    assert panel["agents_total"] == 0 and panel["top_agents"] == []
    assert "new_agent" in panel["allowed"]
    assert {"code": "no_agents", "count": 1} in panel["attention"]["reasons"]


async def test_the_first_thing_the_ficha_lacks_and_none_when_complete(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 3: sin horario, una sola línea: «Horarios: falta…»."""
    a = world["a"]
    c = await _cultor(client, db_session, world)
    order = ["hours", "services", "locations", "sources", "links"]
    for i, section in enumerate(order):
        panel = await _panel(client, a["headers"](), c["url"])
        assert panel["missing"] == {"section": section, "action": f"add_{section}"}, i
        async with tenant_scoped_session(db_session, c["tenant_id"]):
            await touch_section(db_session, section, actor=ANA, state="complete")
    assert (await _panel(client, a["headers"](), c["url"]))["missing"] is None


async def test_the_figures_match_the_lite_console_to_the_cent(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    one = await add_agent(
        db_session, c["tenant_id"], "Citas", created_at=datetime.now(UTC) - timedelta(hours=3)
    )
    two = await add_agent(
        db_session, c["tenant_id"], "Ventas", created_at=datetime.now(UTC) - timedelta(hours=2)
    )
    await set_bag(
        db_session, a["partner_id"], c["tenant_id"], cap=30 * USD, remaining=12_345_678 // 1000
    )
    for agent, credits in ((one, 333_333), (two, 166_667), (one, 1_001)):
        await add_spend(
            db_session,
            a["partner_id"],
            c["tenant_id"],
            credits,
            agent_id=agent["agent_id"],
            at=datetime.now(UTC) - timedelta(minutes=5),
        )
    panel = await _panel(client, a["headers"](), c["url"])
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        lite = await lite_home(
            db_session,
            partner_id=a["partner_id"],
            tenant_id=c["tenant_id"],
            client_ref=c["ref"],
            client_name="Barbería Cultor",
            tenant_status=TenantStatus.ACTIVE,
            with_inbox=False,
        )
    assert lite.balance is not None and lite.spend_month is not None
    assert panel["bag"]["balance"]["amount_micros"] == lite.balance.remaining_cents * 1000
    assert panel["month"]["spent"]["amount_micros"] == lite.spend_month.total_cents * 1000
    assert lite.spend_month.by_agent is not None
    by_lite = {str(x.agent_id): x.cents * 1000 for x in lite.spend_month.by_agent}
    by_panel = {x["agent_id"]: x["spent"]["amount_micros"] for x in panel["spend_by_agent"]}
    assert by_panel == by_lite


async def test_the_reading_card_rides_on_the_panel(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world, info="cultorbarber.com")
    panel = await _panel(client, a["headers"](), c["url"])
    read = panel["read"]
    assert read["website"] == "cultorbarber.com"
    assert read["job"]["job_id"] == c["created"]["read_job_id"]
    assert read["job"]["status"] in ("queued", "running")


async def test_another_partner_gets_the_same_404(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    c = await _cultor(client, db_session, world)
    resp = await client.get(c["url"], headers=world["b"]["headers"]())
    assert resp.status_code == 404 and resp.json() == {"detail": "Unknown client reference"}
