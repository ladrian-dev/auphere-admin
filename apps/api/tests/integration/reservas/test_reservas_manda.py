"""Spec 043, requisito 11 — Reservas es la única agenda (enmienda del 2026-11-04).

Decisión de Luis: «el calendario nativo de auphere debe ser la fuente de la verdad».
Sustituye a la de ``b45a86c7``, ``d0a83763`` y ``82ff213c``, con la que un agente con
Google conectado reservaba solo en Google: la cita no aparecía en Reservas, no llevaba
recordatorios y alguien podía ocupar esa hora desde la consola.
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from structlog.testing import capture_logs

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    ClientAccess,
    Connector,
    ConsoleNotification,
    Customer,
    Reservation,
    ReservationService,
    ReservationSettings,
    ReservationStaff,
    Tenant,
    TenantConnector,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.services import activations, publishing
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.agent_spec.retired import (
    agent_may_use,
    mentions_retired,
    names_retired,
    replacement,
    rewrite_text,
)
from nexus_api.services.agent_spec.validator import load_context
from nexus_api.services.business.writes import drain_after_commit
from nexus_api.services.connectors import booking_skills
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.reservations import auto_pass, passing
from tests.conftest import future_day, make_reservas
from tests.integration.reservations._legacy_world import (
    agent_with_booking,
    read,
    spec_with_booking,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

CREATE = "GOOGLECALENDAR_CREATE_EVENT"
FREE = "GOOGLECALENDAR_FIND_FREE_SLOTS"
EVENTS = "GOOGLECALENDAR_EVENTS_LIST"
DELETE = "GOOGLECALENDAR_DELETE_EVENT"
GOOGLE = [FREE, CREATE, EVENTS]
CALENDLY = [
    "CALENDLY_WHO_AM_I",
    "CALENDLY_LIST_EVENT_TYPES",
    "CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES",
    "CALENDLY_POST_INVITEE",
    "CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK",
]
RESERVAS_PAIR = {"reservas.find_slots", "reservas.create"}


async def _agent(
    db_session: Any,
    tenant_id: uuid.UUID,
    *,
    tools: list[str],
    prompt: str = "Eres la recepción.",
    spec: dict[str, Any] | None = None,
    name: str = "Recepción",
    version: int = 1,
) -> uuid.UUID:
    agent = Agent(tenant_id=tenant_id, name=name)
    db_session.add(agent)
    await db_session.flush()
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=version,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered=prompt,
            channels=[],
            tools=tools,
            policies={},
            spec=spec,
            created_by="test",
        )
    )
    await db_session.commit()
    return agent.id


async def _google_connected(
    db_session: Any,
    tenant_id: uuid.UUID,
    *,
    slug: str = "googlecalendar",
    names: list[str] = GOOGLE,
) -> tuple[Connector, TenantConnector]:
    connector = await db_session.scalar(sa.select(Connector).where(Connector.slug == slug))
    if connector is None:
        connector = Connector(
            slug=slug,
            display_name=slug.title(),
            vendor=slug.title(),
            category="calendar",
            auth_kind="oauth_composio",
            mcp_server_ref=f"composio:{slug}",
            auto_enable_on_connect=True,
        )
        db_session.add(connector)
        await db_session.flush()
    known = set(await db_session.scalars(sa.select(ToolCatalog.name)))
    for name in names:
        if name in known:
            continue
        db_session.add(
            ToolCatalog(
                name=name,
                description=name,
                mcp_server=f"composio:{slug}",
                status=ToolStatus.ACTIVE,
                connector_id=connector.id,
                read_only=name in (FREE, EVENTS),
                destructive=name == CREATE,
                default_mode="always" if name in (FREE, EVENTS) else "blocked",
            )
        )
    install = TenantConnector(
        tenant_id=tenant_id,
        connector_id=connector.id,
        status="connected",
        credentials_ref={"composio_connection_id": f"ca_{slug}", "user_id": "tenant_x"},
    )
    db_session.add(install)
    await db_session.commit()
    return connector, install


async def _versions(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> dict[str, AgentConfig]:
    return {
        ("active" if v.status == AgentConfigStatus.ACTIVE else "draft"): v
        for v in await read(
            tenant_id,
            lambda s: _rows(s, agent_id),
        )
    }


async def _rows(session: Any, agent_id: uuid.UUID) -> list[AgentConfig]:
    rows = await session.scalars(
        sa.select(AgentConfig).where(
            AgentConfig.agent_id == agent_id,
            AgentConfig.status.in_([AgentConfigStatus.ACTIVE, AgentConfigStatus.STAGED]),
        )
    )
    return list(rows)


# ── 11.1 Conectar Google no da herramientas ─────────────────────────────────


async def test_connecting_google_gives_no_agent_any_tool(db_session, console_world) -> None:
    w = console_world["a"]
    agent_id = await _agent(db_session, w["tenant_id"], tools=["escalate.escalate_to_human"])
    connector, install = await _google_connected(db_session, w["tenant_id"])

    assert not booking_skills.books("googlecalendar")
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        added = await connector_service.enable_booking_once(
            db_session, connector=connector, install=install, agent_id=agent_id, actor="test"
        )
        enabled = await connector_service.auto_enable_connector_tools(
            db_session, tenant_id=w["tenant_id"], connector=connector, actor="test"
        )
        await booking_skills.enable_after_sync(
            db_session, connector=connector, install=install, actor="test"
        )
    await db_session.commit()

    assert added == [] and enabled == []
    versions = await _versions(w["tenant_id"], agent_id)
    assert "draft" not in versions, "no draft appears because an account was connected"


# ── 11.2 El turno, según si el agente ya pasó ───────────────────────────────


async def _policy(db_session: Any, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Any:
    async with tenant_scoped_session(db_session, tenant_id):
        policy = await activations.tool_policy(db_session, tenant_id, agent_id)
    await db_session.commit()
    return policy


async def test_an_agent_that_books_in_reservas_never_gets_a_google_tool(
    db_session, console_world
) -> None:
    """Aunque su versión la nombre y la conexión esté activada: dos agendas son una doble
    reserva."""
    w = console_world["a"]
    await _google_connected(db_session, w["tenant_id"])
    agent_id = await _agent(db_session, w["tenant_id"], tools=["reservas.create", CREATE, EVENTS])

    policy = await _policy(db_session, w["tenant_id"], agent_id)

    offered = activations.allowed_names(("reservas.create", CREATE, EVENTS), policy)
    assert offered == ("reservas.create",)


async def test_an_agent_that_has_not_passed_keeps_working_as_it_did(
    db_session, console_world
) -> None:
    """Decisión de la revisión: si el cliente aún no puede reservar, el agente sigue como está.
    Bloquearle Google sin darle Reservas lo dejaría sin agenda ninguna."""
    w = console_world["a"]
    await _google_connected(db_session, w["tenant_id"])
    agent_id = await _agent(db_session, w["tenant_id"], tools=[FREE, CREATE])

    policy = await _policy(db_session, w["tenant_id"], agent_id)

    assert activations.allowed_names((FREE, CREATE), policy) == (FREE, CREATE)


async def test_a_new_version_can_never_name_google(db_session, console_world) -> None:
    """El nombre, sin mirar al cliente: lo que manda en lo que se escribe a partir de ahora."""
    for name in (CREATE, FREE, EVENTS, DELETE, "GOOGLECALENDAR_CALENDAR_LIST_DELETE"):
        assert agent_may_use(name) is False
    assert agent_may_use("reservas.create") is True
    assert agent_may_use("CALENDLY_POST_INVITEE") is True


async def test_the_proxy_builds_what_the_turn_then_decides(db_session, console_world) -> None:
    """El proxy no sabe de qué agente es el turno: quien decide es la política."""
    from nexus_mcp.servers.composio_proxy import load_blueprints_for_tenant

    w = console_world["a"]
    await _google_connected(db_session, w["tenant_id"], names=[CREATE])

    blueprints = await load_blueprints_for_tenant(w["tenant_id"])

    assert [b.tool_name for b in blueprints] == [CREATE]


# ── 11.3 Retiradas con su sustituta ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("tool", "instead"),
    [
        (CREATE, "reservas.create"),
        ("GOOGLECALENDAR_QUICK_ADD", "reservas.create"),
        (FREE, "reservas.find_slots"),
        (DELETE, "reservas.cancel"),
        ("GOOGLECALENDAR_UPDATE_EVENT", "reservas.reschedule"),
        ("GOOGLECALENDAR_PATCH_EVENT", "reservas.reschedule"),
        ("GOOGLECALENDAR_FIND_EVENT", "reservas.list_mine"),
        (EVENTS, "reservas.list_mine"),
    ],
)
async def test_what_touched_the_agenda_in_google_has_its_replacement(
    tool: str, instead: str
) -> None:
    assert replacement(tool) == instead
    assert names_retired([tool])


async def test_any_mention_of_google_goes_out_of_a_text() -> None:
    """También la que no tiene sustituta: un texto no puede prometer lo que el agente ya no
    tiene."""
    text = f"Borra con {DELETE}. Mira GOOGLECALENDAR_CALENDAR_LIST_DELETE si hace falta."
    assert mentions_retired(text)
    out = rewrite_text(text)
    assert "GOOGLECALENDAR" not in out
    assert "reservas.cancel" in out
    assert not names_retired(["CALENDLY_POST_INVITEE"])


# ── 11.4 El paso automático ─────────────────────────────────────────────────


def _spec_with_google() -> dict[str, Any]:
    doc = copy.deepcopy(spec_with_booking())
    doc["tools"] = [FREE, CREATE, EVENTS, "escalate.escalate_to_human"]
    doc["procedures"][0]["tools"] = [FREE, CREATE, EVENTS]
    doc["procedures"][0]["steps"] = (
        f"Mira el hueco con {FREE} y reserva con {CREATE}, avisando al cliente."
    )
    doc["skills"] = [{"key": "agenda", "enabled": True, "integration": "googlecalendar"}]
    doc["connection_requests"] = [{"integration": "googlecalendar", "reason": "Su agenda"}]
    return doc


async def test_the_deploy_pass_takes_google_out_of_the_live_agent(
    db_session, console_world
) -> None:
    """Lo que ya reservaba en Google pasa solo a Reservas, en sus cuatro sitios, sin la
    puerta de pruebas y firmado por Auphere, si el cliente ya puede reservar."""
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    agent_id = await _agent(
        db_session,
        w["tenant_id"],
        tools=[*GOOGLE, "escalate.escalate_to_human"],
        prompt=f"Para reservar usa {CREATE}.",
        spec=_spec_with_google(),
    )

    summary = await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))

    assert w["tenant_id"] in summary.passed
    live = (await _versions(w["tenant_id"], agent_id))["active"]
    assert set(live.tools) >= RESERVAS_PAIR
    assert "reservas.services" in live.tools
    assert "escalate.escalate_to_human" in live.tools
    assert not [t for t in live.tools if t.startswith("GOOGLECALENDAR_")]
    assert "reservas.create" in live.system_prompt_rendered
    assert "GOOGLECALENDAR" not in live.system_prompt_rendered
    assert live.created_by == auto_pass.ACTOR
    doc = live.spec
    assert doc is not None
    assert not [t for t in doc["tools"] if t.startswith("GOOGLECALENDAR_")]
    assert set(doc["procedures"][0]["tools"]) == {*RESERVAS_PAIR, "reservas.list_mine"}
    assert "GOOGLECALENDAR" not in doc["procedures"][0]["steps"]
    assert doc["skills"][0]["integration"] == "reservas"
    assert not [
        r for r in doc.get("connection_requests") or [] if r["integration"] == "googlecalendar"
    ]

    again = await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))
    assert w["tenant_id"] not in again.passed


async def test_after_the_pass_the_agent_really_books(db_session, console_world) -> None:
    """No basta con que la versión diga ``reservas.*``: la cita tiene que nacer."""
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    w = console_world["a"]
    shop = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    agent_id = await _agent(db_session, w["tenant_id"], tools=[FREE, CREATE])
    ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", name="Ana", preferences={})
    db_session.add(ana)
    await db_session.commit()

    await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))

    tools = (await _versions(w["tenant_id"], agent_id))["active"].tools
    reset_default_registry()
    registry = build_default_registry()
    with tenant_context(w["tenant_id"]), customer_context(ana.id):
        listed = await registry.dispatch("reservas.services", {}, whitelist=tools)
        service = next(s for s in listed["result"]["services"] if s["id"] == str(shop["corte"]))
        made = await registry.dispatch(
            "reservas.create",
            {
                "date": future_day().isoformat(),
                "time": "10:00",
                "service_id": service["id"],
                "idempotency_key": "after-the-pass",
            },
            whitelist=tools,
        )
    assert made["result"]["booking"]["status"] in ("pending", "confirmed")
    rows = await read(w["tenant_id"], lambda s: _count_bookings(s))
    assert rows == 1


async def _count_bookings(session: Any) -> int:
    return int(await session.scalar(sa.select(sa.func.count()).select_from(Reservation)) or 0)


async def _notices(tenant: dict[str, Any]) -> list[Any]:
    sm = get_sessionmaker()
    async with sm() as session:
        rows = await session.scalars(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.kind == "reservas.pass_not_ready",
                ConsoleNotification.partner_id == tenant["partner_id"],
            )
        )
        return list(rows)


@pytest.mark.parametrize(
    ("break_it", "reason"),
    [
        ("no_module", "reservas_off"),
        ("no_hours", "hours_missing"),
        ("no_staff", "no_staff"),
        ("no_services", "no_services"),
        ("only_impossible", "no_bookable_service"),
    ],
)
async def test_a_client_that_cannot_book_keeps_its_agent_and_says_why(
    db_session, console_world, break_it: str, reason: str
) -> None:
    """Decisión de la revisión: si el cliente no puede reservar, no se publica. Publicar dejaría
    a un negocio que reservaba con Google respondiendo que no hay agenda."""
    w = console_world["a"]
    tid = w["tenant_id"]
    if break_it != "no_module":
        await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tid)
    agent_id = await _agent(db_session, tid, tools=[FREE, CREATE], prompt=f"Reserva con {CREATE}.")
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tid):
        if break_it == "no_hours":
            await session.execute(
                sa.update(Tenant).where(Tenant.id == tid).values(business_hours=None)
            )
        if break_it == "no_staff":
            await session.execute(sa.update(ReservationStaff).values(archived_at=sa.func.now()))
        if break_it == "no_services":
            await session.execute(sa.update(ReservationService).values(archived_at=sa.func.now()))
        if break_it == "only_impossible":
            await session.execute(sa.update(ReservationService).values(all_staff=False))

    with capture_logs() as logs:
        summary = await auto_pass.run(sm, now=datetime.now(UTC))

    assert tid not in summary.passed
    assert tid in summary.not_ready
    versions = await _versions(tid, agent_id)
    assert versions["active"].tools == [FREE, CREATE], "nothing is published"
    assert versions["active"].created_by == "test"
    event = next(e for e in logs if e["event"] == "reservations.auto_pass_not_ready")
    assert event["tenant_id"] == str(tid)
    assert reason in event["reasons"]
    await drain_after_commit()
    notices = await _notices(w)
    assert notices, "the partner is told"
    assert reason in notices[0].payload["reasons"]
    if break_it == "no_module":
        assert await read(tid, lambda s: s.get(ReservationSettings, tid)) is None
        access = await read(tid, lambda s: s.get(ClientAccess, tid))
        assert access is None or not access.reservas_on, "nothing is switched on by itself"


async def test_a_failed_pass_leaves_the_agent_working_and_says_so(
    db_session, console_world, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = console_world["a"]
    tid = w["tenant_id"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tid)
    agent_id = await _agent(db_session, tid, tools=[CREATE])

    async def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("no se pudo")

    monkeypatch.setattr(passing, "pass_to_reservas", boom)
    summary = await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))
    await drain_after_commit()

    assert tid in summary.failed
    live = (await _versions(tid, agent_id))["active"]
    assert live.tools == [CREATE]
    policy = await _policy(db_session, tid, agent_id)
    assert activations.allowed_names((CREATE,), policy) == (CREATE,), "it can still book"
    rows = await read(tid, lambda s: _failures(s, tid))
    assert rows, "the failure stays written"
    assert "no se pudo" not in str(rows[0].after_json), "without the text of the error"
    assert await _notices(w)


async def _failures(session: Any, tenant_id: uuid.UUID) -> list[AuditLog]:
    return list(
        await session.scalars(
            sa.select(AuditLog).where(
                AuditLog.tenant_id == tenant_id, AuditLog.action == "reservations.pass_failed"
            )
        )
    )


async def _operator(db_session, admin_headers) -> dict[str, str]:
    from nexus_api.services import operator_identity

    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def test_the_operator_sees_who_still_books_in_google_and_why(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    agent_id = await _agent(db_session, w["tenant_id"], tools=[CREATE])
    h = await _operator(db_session, admin_headers)
    r = await client.get(f"/admin/tenants/{w['tenant_id']}/client-access", headers=h)
    assert r.status_code == 200, r.text
    pending = r.json()["reservas_pending_pass"]
    assert [a["agent_id"] for a in pending["agents"]] == [str(agent_id)]
    assert pending["reasons"] == ["reservas_off"]


async def test_nobody_pending_says_nothing(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    await _agent(db_session, w["tenant_id"], tools=["escalate.escalate_to_human"])
    h = await _operator(db_session, admin_headers)
    r = await client.get(f"/admin/tenants/{w['tenant_id']}/client-access", headers=h)
    assert r.json()["reservas_pending_pass"] is None


async def test_the_deploy_pass_rewrites_a_draft_and_does_not_publish_it(
    db_session, console_world
) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    agent_id = await _agent(db_session, w["tenant_id"], tools=["escalate.escalate_to_human"])
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        db_session.add(
            AgentConfig(
                tenant_id=w["tenant_id"],
                agent_id=agent_id,
                version=2,
                status=AgentConfigStatus.STAGED,
                system_prompt_rendered="Borrador.",
                channels=[],
                tools=[CREATE],
                policies={},
                created_by="partner@example.com",
            )
        )
    await db_session.commit()

    await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))

    versions = await _versions(w["tenant_id"], agent_id)
    assert "reservas.create" in versions["draft"].tools
    assert CREATE not in versions["draft"].tools
    assert versions["active"].tools == ["escalate.escalate_to_human"]


async def test_a_tool_without_a_replacement_leaves_with_nothing_in_its_place(
    db_session, console_world
) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    agent_id = await _agent(
        db_session,
        w["tenant_id"],
        tools=["GOOGLECALENDAR_CALENDAR_LIST_DELETE", "escalate.escalate_to_human"],
    )
    await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))
    live = (await _versions(w["tenant_id"], agent_id))["active"]
    assert live.tools == ["escalate.escalate_to_human"]


async def test_the_pass_tells_the_audit_it_was_about_google(db_session, console_world) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _agent(db_session, w["tenant_id"], tools=[CREATE])
    await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))
    rows = await read(
        w["tenant_id"],
        lambda s: _audit(s, w["tenant_id"]),
    )
    assert [r.actor for r in rows] == [auto_pass.ACTOR]


async def _audit(session: Any, tenant_id: uuid.UUID) -> list[AuditLog]:
    return list(
        await session.scalars(
            sa.select(AuditLog).where(
                AuditLog.tenant_id == tenant_id, AuditLog.action == "reservations.passed"
            )
        )
    )


# ── 11.5 Encender Reservas ──────────────────────────────────────────────────


async def test_switching_reservas_on_takes_the_connector_out_of_the_draft(
    client, db_session, console_world, admin_headers
) -> None:
    from nexus_api.services import operator_identity

    w = console_world["a"]
    agent_id = await _agent(
        db_session, w["tenant_id"], tools=[*CALENDLY, "escalate.escalate_to_human"]
    )
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    r = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers={**admin_headers, "X-Operator-Id": str(op.id)},
        json={"enabled": True, "modules": ["panel", "reservas"], "reservas": {"mode": "services"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()["reservas"]

    versions = await _versions(w["tenant_id"], agent_id)
    draft = versions["draft"]
    assert set(draft.tools) >= RESERVAS_PAIR
    assert not [t for t in draft.tools if t.startswith("CALENDLY_")]
    # La activa no cambia sola (constitución §IV), y mientras tanto el panel lo dice.
    assert "CALENDLY_POST_INVITEE" in versions["active"].tools
    assert [a["agent_id"] for a in body["agents_pending_promotion"]] == [str(agent_id)]
    assert [a["agent_id"] for a in body["agents_with_other_calendar"]] == [str(agent_id)]


async def test_an_agent_whose_live_version_no_longer_books_outside_is_not_listed(
    client, db_session, console_world, admin_headers
) -> None:
    from nexus_api.services import operator_identity

    w = console_world["a"]
    await _agent(db_session, w["tenant_id"], tools=["reservas.create"])
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    r = await client.put(
        f"/admin/tenants/{w['tenant_id']}/client-access",
        headers={**admin_headers, "X-Operator-Id": str(op.id)},
        json={"enabled": True, "modules": ["panel", "reservas"], "reservas": {"mode": "services"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["reservas"]["agents_with_other_calendar"] == []


# ── 11.6 y 11.7 Calendly, con y sin Reservas ────────────────────────────────


async def test_with_reservas_on_calendly_does_not_add_a_second_calendar(
    db_session, console_world
) -> None:
    w = console_world["a"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    agent_id = await _agent(db_session, w["tenant_id"], tools=["escalate.escalate_to_human"])
    connector, install = await _google_connected(
        db_session, w["tenant_id"], slug="calendly", names=CALENDLY
    )
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        added = await booking_skills.enable_booking_skills(
            db_session, connector=connector, install=install, agent_id=agent_id, actor="test"
        )
    await db_session.commit()
    assert added == []
    assert "draft" not in await _versions(w["tenant_id"], agent_id)


async def test_without_reservas_calendly_keeps_booking(db_session, console_world) -> None:
    w = console_world["a"]
    agent_id = await _agent(db_session, w["tenant_id"], tools=["escalate.escalate_to_human"])
    connector, install = await _google_connected(
        db_session, w["tenant_id"], slug="calendly", names=CALENDLY
    )
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        added = await booking_skills.enable_booking_skills(
            db_session, connector=connector, install=install, agent_id=agent_id, actor="test"
        )
    await db_session.commit()
    assert "CALENDLY_POST_INVITEE" in added
    assert "CALENDLY_POST_INVITEE" in (await _versions(w["tenant_id"], agent_id))["draft"].tools


async def test_the_deploy_pass_leaves_calendly_in_a_draft_where_reservas_is_on(
    db_session, console_world
) -> None:
    """R11.5, decisión de la revisión: Calendly no está retirado, así que no se publica sin la
    puerta. Se prepara su borrador, y el panel dice que falta publicarlo. Sin Reservas, no se
    toca: Luis no decidió sobre esos negocios."""
    a, b = console_world["a"], console_world["b"]
    await make_reservas(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    with_module = await _agent(db_session, a["tenant_id"], tools=list(CALENDLY))
    without = await _agent(db_session, b["tenant_id"], tools=list(CALENDLY))

    await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))

    versions = await _versions(a["tenant_id"], with_module)
    assert versions["active"].tools == CALENDLY, "not published"
    assert {"reservas.find_slots", "reservas.create"} <= set(versions["draft"].tools)
    assert not [t for t in versions["draft"].tools if t.startswith("CALENDLY_")]
    kept = await _versions(b["tenant_id"], without)
    assert kept["active"].tools == CALENDLY
    assert "draft" not in kept

    again = await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))
    assert a["tenant_id"] not in again.passed, "a second deploy has nothing left to do"


# ── 11.8 No se ofrece a un agente ───────────────────────────────────────────


async def test_google_is_not_offered_to_an_agent(client, db_session, console_world) -> None:
    from nexus_api.api.console import agent_integrations

    assert "googlecalendar" in agent_integrations.NOT_FOR_AGENTS


# ── 11.9 No cuenta como reservar ────────────────────────────────────────────


async def test_google_does_not_keep_the_promise_of_booking() -> None:
    from nexus_api.api.console.capability_names import TOOL_ACTIONS

    assert CREATE not in TOOL_ACTIONS
    assert "CALENDLY_POST_INVITEE" in TOOL_ACTIONS


# ── Mientras espera a pasar, se sigue pudiendo editar ───────────────────────


async def _draft_url(w: dict[str, Any], agent_id: uuid.UUID) -> str:
    return f"/console/clients/{w['ref']}/agents/{agent_id}/draft"


async def _save(client: Any, w: dict[str, Any], agent_id: uuid.UUID, change: Any) -> Any:
    url = await _draft_url(w, agent_id)
    got = await client.get(url, headers=w["headers"]())
    assert got.status_code == 200, got.text
    draft = got.json()
    spec = draft["spec"]
    change(spec)
    return await client.patch(
        url,
        json={"spec": spec},
        headers={**w["headers"](), "If-Match": f'"{draft["revision"]}"'},
    )


async def test_an_agent_waiting_to_pass_can_still_be_edited_and_published(
    client, db_session, console_world
) -> None:
    """Revisión, D1: la consola manda la ficha entera, y cambiar el tono de un agente que nombra
    Google daba 422 sin ninguna forma de quitar la herramienta. Se queda sin poder cambiar nada
    justo cuando su cliente aún no puede pasar."""
    w = console_world["a"]
    tid = w["tenant_id"]
    agent_id = await _agent(
        db_session,
        tid,
        tools=[*GOOGLE, "escalate.escalate_to_human"],
        prompt="Eres la recepción.",
        spec=_spec_with_google(),
    )

    def set_rules(spec: dict[str, Any]) -> None:
        spec["rules"] = ["Pide siempre el nombre."]

    saved = await _save(client, w, agent_id, set_rules)
    assert saved.status_code == 200, saved.text
    assert FREE in saved.json()["spec"]["tools"], "what it had stays"

    versions = await _versions(tid, agent_id)
    agent = await read(tid, lambda s: s.get(Agent, agent_id))
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tid):
        gate = await publishing.evaluate_gate(
            session,
            agent=agent,
            version=versions["draft"],
            active=versions["active"],
            partner_id=w["partner_id"],
        )
    assert not [h for h in gate.hard if h.get("code") == "tool_retired"], gate.hard


async def test_an_agent_waiting_to_pass_cannot_add_another_google_tool(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    agent_id = await _agent(
        db_session,
        w["tenant_id"],
        tools=[*GOOGLE, "escalate.escalate_to_human"],
        spec=_spec_with_google(),
    )

    def add(spec: dict[str, Any]) -> None:
        spec["tools"] = [*spec["tools"], "GOOGLECALENDAR_DELETE_EVENT"]

    refused = await _save(client, w, agent_id, add)
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["problems"][0]["code"] == "tool_retired"


async def test_what_one_agent_has_does_not_let_another_have_it(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    await _agent(
        db_session,
        w["tenant_id"],
        tools=[*GOOGLE, "escalate.escalate_to_human"],
        spec=_spec_with_google(),
    )
    clean = copy.deepcopy(spec_with_booking())
    clean["tools"] = ["escalate.escalate_to_human"]
    clean["procedures"] = []
    other = await _agent(
        db_session,
        w["tenant_id"],
        tools=["escalate.escalate_to_human"],
        spec=clean,
        name="Ventas",
        version=50,
    )

    def add(spec: dict[str, Any]) -> None:
        spec["tools"] = [*spec["tools"], FREE]

    refused = await _save(client, w, other, add)
    assert refused.status_code == 422, refused.text


async def test_each_way_of_validating_knows_what_the_agent_already_has(
    db_session, console_world
) -> None:
    w = console_world["a"]
    agent_id = await _agent(
        db_session,
        w["tenant_id"],
        tools=[*GOOGLE, "escalate.escalate_to_human"],
        spec=_spec_with_google(),
    )
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        ctx = await load_context(session, partner_id=w["partner_id"], agent_id=agent_id)
        nobody = await load_context(session, partner_id=w["partner_id"])
    assert ctx.held_tools == frozenset(GOOGLE)
    assert nobody.held_tools == frozenset()


# ── Lo que se descarta no vuelve ────────────────────────────────────────────


async def test_a_calendly_draft_thrown_away_does_not_come_back(db_session, console_world) -> None:
    """Revisión, D5: volvía en cada despliegue, con todas las pruebas desactualizadas y otra línea
    de auditoría. Y cada fusión a ``develop`` despliega."""
    w = console_world["a"]
    tid = w["tenant_id"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tid)
    agent_id = await _agent(db_session, tid, tools=list(CALENDLY))
    sm = get_sessionmaker()

    first = await auto_pass.run(sm, now=datetime.now(UTC))
    assert tid in first.passed
    assert (await _versions(tid, agent_id))["draft"] is not None

    async with sm() as session, tenant_scoped_session(session, tid):
        await AgentConfigService(session).discard_draft(
            actor="partner@example.com", agent_id=agent_id, expected_revision=None
        )

    async def passes() -> int:
        async with sm() as session, tenant_scoped_session(session, tid):
            found = await session.scalar(
                sa.select(sa.func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "reservations.passed")
            )
        return int(found or 0)

    before = await passes()
    again = await auto_pass.run(sm, now=datetime.now(UTC))

    assert tid not in again.passed
    async with sm() as session, tenant_scoped_session(session, tid):
        drafts = await session.scalar(
            sa.select(sa.func.count())
            .select_from(AgentConfig)
            .where(
                AgentConfig.agent_id == agent_id,
                AgentConfig.status == AgentConfigStatus.STAGED,
            )
        )
    assert drafts == 0, "what somebody threw away does not come back"
    assert await passes() == before


# ── Se decide agente por agente ─────────────────────────────────────────────


async def test_an_agent_with_google_does_not_hold_back_one_with_booking(
    db_session, console_world
) -> None:
    """Revisión, D6: uno que espera a que el cliente esté listo no retiene al que usa ``booking.*``,
    que se retira de todas formas (spec 048)."""
    w = console_world["a"]
    tid = w["tenant_id"]
    google = await _agent(
        db_session, tid, tools=[*GOOGLE, "escalate.escalate_to_human"], name="Google", version=50
    )
    booking = await agent_with_booking(db_session, tid)
    sm = get_sessionmaker()

    summary = await auto_pass.run(sm, now=datetime.now(UTC))

    assert tid in summary.passed, "booking.* passes, as spec 048 asks"
    assert tid in summary.not_ready, "and the other one says it is waiting"
    moved = (await _versions(tid, booking))["active"]
    assert "reservas.create" in moved.tools
    assert not [t for t in moved.tools if t.startswith("booking.")]
    stays = await _versions(tid, google)
    assert stays["active"].created_by == "test"
    assert set(stays["active"].tools) >= set(GOOGLE)
    assert "draft" not in stays

    again = await auto_pass.run(sm, now=datetime.now(UTC))
    assert tid not in again.passed
    assert tid in again.not_ready


async def test_two_agents_pass_together_when_the_client_is_ready(db_session, console_world) -> None:
    w = console_world["a"]
    tid = w["tenant_id"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tid)
    google = await _agent(
        db_session, tid, tools=[*GOOGLE, "escalate.escalate_to_human"], name="Google", version=50
    )
    booking = await agent_with_booking(db_session, tid)

    summary = await auto_pass.run(get_sessionmaker(), now=datetime.now(UTC))

    assert tid in summary.passed
    assert tid not in summary.not_ready
    for agent_id in (google, booking):
        assert "reservas.create" in (await _versions(tid, agent_id))["active"].tools
