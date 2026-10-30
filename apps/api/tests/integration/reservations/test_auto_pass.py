"""Spec 048, T026 — the automatic pass to Reservas at deploy time (requirement 3,
amended on 2026-10-29; story 3, scenarios 1 to 6).

``release.sh`` runs it after ``alembic upgrade head``. Nobody has to do
anything: for every client with an active agent whose active version or draft
names ``booking.*``

- if the client has no Reservas, it is turned on — capacity (restaurant) when
  the business is a restaurant (saved sector, or else the agent's template),
  appointments per person otherwise — without opening the client's people's
  access nor inviting anybody;
- a version equal to the **active** one, with ``reservas.*`` instead of
  ``booking.*`` in its four places, is published without the test gate, as
  Auphere (``platform:reservas-pass``) and with its reason; the agent's tests
  go stale;
- a partner's draft that names ``booking.*`` is rewritten the same way and is
  **not** published;
- future appointments are imported, with a report in the client's audit
  (``reservations.passed``, marked automatic);
- a second run finds nobody; a client that fails is rolled back alone, logged
  (``reservations.auto_pass_failed``) and the others pass; the end is logged
  (``reservations.auto_pass_done``) and the deploy goes on.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from structlog.testing import capture_logs

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Appointment,
    AppointmentStatus,
    AuditLog,
    ClientAccess,
    ClientInvitation,
    ClientMembership,
    Reservation,
    ReservationOutbox,
    ReservationSettings,
)
from nexus_api.db.models.agent_spec import AgentTest
from nexus_api.services import operator_identity
from tests.conftest import add_client_member, make_client_access, make_reservas
from tests.integration.reservations._legacy_world import (
    BOOKING,
    agent_with_booking,
    appointment,
    barber,
    business_sector,
    customer,
    plain_version,
    read,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ACTOR = "platform:reservas-pass"
RESERVAS_PAIR = {"reservas.find_slots", "reservas.create"}


def _now() -> datetime:
    return datetime.now(UTC)


async def _run(now: datetime | None = None):  # type: ignore[no-untyped-def]
    from nexus_api.services.reservations import auto_pass

    return await auto_pass.run(get_sessionmaker(), now=now or _now())


async def _versions(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> list[AgentConfig]:
    async def fn(session):  # type: ignore[no-untyped-def]
        return list(
            (
                await session.execute(
                    sa.select(AgentConfig)
                    .where(AgentConfig.agent_id == agent_id)
                    .order_by(AgentConfig.version)
                )
            ).scalars()
        )

    return await read(tenant_id, fn)


async def _audit(tenant_id: uuid.UUID, action: str) -> list[AuditLog]:
    async def fn(session):  # type: ignore[no-untyped-def]
        return list(
            (
                await session.execute(
                    sa.select(AuditLog)
                    .where(AuditLog.action == action)
                    .order_by(AuditLog.created_at)
                )
            ).scalars()
        )

    return await read(tenant_id, fn)


def _no_booking(cfg: AgentConfig) -> None:
    """``reservas.*`` in the four places, ``booking.*`` in none."""
    assert not [t for t in cfg.tools if t.startswith("booking.")], cfg.tools
    assert set(cfg.tools) >= RESERVAS_PAIR
    assert not [t for t in cfg.spec["tools"] if t.startswith("booking.")]
    assert set(cfg.spec["tools"]) >= RESERVAS_PAIR
    assert cfg.spec["procedures"][0]["tools"] == ["reservas.find_slots", "reservas.create"]
    assert "booking." not in cfg.spec["procedures"][0]["steps"]
    assert "reservas.create" in cfg.spec["procedures"][0]["steps"]
    assert "booking." not in cfg.system_prompt_rendered
    assert "reservas.find_slots" in cfg.system_prompt_rendered


# ── scenario 2: Reservas is turned on, by sector or template ───────────────


async def test_a_client_without_reservas_gets_it_by_its_saved_sector(
    db_session, console_world
) -> None:
    """A restaurant gets capacity (restaurant), a barbershop appointments per
    person. Neither opens the people's access nor invites anybody, and the
    agent can book with ``reservas.*`` right away."""
    a, b = console_world["a"], console_world["b"]
    await business_sector(db_session, a["tenant_id"], "restaurante")
    await business_sector(db_session, b["tenant_id"], "barberia_peluqueria")
    await agent_with_booking(db_session, a["tenant_id"])
    await agent_with_booking(db_session, b["tenant_id"])
    # B already has a person, with the access closed and no Reservas.
    await make_client_access(
        db_session,
        partner_id=b["partner_id"],
        tenant_id=b["tenant_id"],
        modules=("panel",),
        enabled=False,
    )
    member = await add_client_member(
        db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"]
    )

    summary = await _run()

    assert set(summary.passed) == {a["tenant_id"], b["tenant_id"]}
    assert summary.failed == []
    assert summary.activated == 2

    from nexus_api.services.reservations import passing

    async def state_of(tid: uuid.UUID):  # type: ignore[no-untyped-def]
        async def fn(session):  # type: ignore[no-untyped-def]
            return (
                (await session.execute(sa.select(ReservationSettings))).scalar_one(),
                (await session.execute(sa.select(ClientAccess))).scalar_one(),
                list((await session.execute(sa.select(ClientInvitation))).scalars()),
                list((await session.execute(sa.select(ClientMembership))).scalars()),
                await passing.reservas_enabled(session, tid),
            )

        return await read(tid, fn)

    settings_a, access_a, invites_a, _, on_a = await state_of(a["tenant_id"])
    assert (settings_a.mode, settings_a.capacity_kind) == ("capacity", "restaurant")
    # The starting values of the mode, as the panel's first activation.
    assert settings_a.seats is not None and settings_a.schedule is not None
    assert access_a.modules == ["reservas"]
    assert access_a.enabled is False
    assert invites_a == []
    assert on_a is True

    settings_b, access_b, invites_b, members_b, on_b = await state_of(b["tenant_id"])
    assert (settings_b.mode, settings_b.capacity_kind) == ("services", None)
    assert access_b.enabled is False, "the people's access stays closed"
    assert access_b.modules == ["panel", "reservas"]
    assert invites_b == []
    assert [(m.id, m.status) for m in members_b] == [(member["membership_id"], "active")]
    assert on_b is True

    # Reservas is on for the agent: its tools answer instead of «no está activo».
    from nexus_mcp import build_default_registry
    from nexus_mcp.registry import reset_default_registry

    reset_default_registry()
    registry = build_default_registry()
    with tenant_context(a["tenant_id"]):
        env = await registry.dispatch("reservas.services", {}, whitelist=["reservas.services"])
    assert env["result"]["mode"] == "capacity", env

    (row,) = await _audit(a["tenant_id"], "reservations.passed")
    assert row.actor == ACTOR
    assert row.after_json["automatic"] is True
    assert row.after_json["activated"] == {
        "mode": "capacity",
        "capacity_kind": "restaurant",
        "from": "sector",
    }


async def test_without_a_sector_the_agents_template_decides(db_session, console_world) -> None:
    """No saved sector: the template the agent comes from. ``restaurante_v1``
    → capacity; any other (or none) → appointments per person."""
    a, b = console_world["a"], console_world["b"]
    await business_sector(db_session, a["tenant_id"], None)
    await agent_with_booking(db_session, a["tenant_id"], template="restaurante_v1")
    await agent_with_booking(db_session, b["tenant_id"], template="barbershop_v1")

    summary = await _run()
    assert set(summary.passed) == {a["tenant_id"], b["tenant_id"]}

    async def settings(session):  # type: ignore[no-untyped-def]
        return (await session.execute(sa.select(ReservationSettings))).scalar_one()

    got_a = await read(a["tenant_id"], settings)
    got_b = await read(b["tenant_id"], settings)
    assert (got_a.mode, got_a.capacity_kind) == ("capacity", "restaurant")
    assert (got_b.mode, got_b.capacity_kind) == ("services", None)
    (row,) = await _audit(a["tenant_id"], "reservations.passed")
    assert row.after_json["activated"]["from"] == "template"


# ── scenario 1 and requirement 3.3: the active version, published ──────────


async def test_the_active_version_is_published_with_reservas_without_the_gate(
    db_session, console_world
) -> None:
    w = console_world["a"]
    tenant_id = w["tenant_id"]
    res = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tenant_id)
    agent_id = await agent_with_booking(db_session, tenant_id, tests=True)

    summary = await _run()
    assert summary.passed == [tenant_id]
    assert summary.published == 1
    assert summary.activated == 0

    old, new = await _versions(tenant_id, agent_id)
    assert old.status == AgentConfigStatus.ARCHIVED
    assert new.status == AgentConfigStatus.ACTIVE
    _no_booking(new)
    # Everything else, as the active version had it.
    assert "escalate.escalate_to_human" in new.tools
    assert new.policies == old.policies
    assert new.channels == old.channels
    assert new.runtime_memory_tool is True
    assert new.base_version_id == old.id
    for key in set(old.spec) - {"tools", "procedures"}:
        assert new.spec[key] == old.spec[key], key
    # A platform change: Auphere, its reason, and no gate.
    assert new.created_by == ACTOR
    assert new.promoted_by == ACTOR
    assert new.published_by == ACTOR
    assert new.published_at is not None
    assert new.override_reason and "booking" in new.override_reason
    assert new.gate is None
    assert new.undo_until is None

    # No draft appears: the change is already live.
    assert [v.status for v in await _versions(tenant_id, agent_id)].count(
        AgentConfigStatus.STAGED
    ) == 0

    # The agent's tests go stale.
    async def tests(session):  # type: ignore[no-untyped-def]
        return list((await session.execute(sa.select(AgentTest))).scalars())

    assert [t.stale for t in await read(tenant_id, tests)] == [True]

    # It already had Reservas: its mode does not change.
    async def settings(session):  # type: ignore[no-untyped-def]
        return await session.get(ReservationSettings, tenant_id)

    kept = await read(tenant_id, settings)
    assert (kept.mode, kept.version) == ("services", 1)
    assert res["corte"] is not None

    # In the client's audit, as Auphere, with the reason.
    (promote,) = await _audit(tenant_id, "agent_config.promote")
    assert promote.actor == ACTOR
    (publish,) = await _audit(tenant_id, "agent.publish")
    assert publish.actor == ACTOR
    assert publish.after_json["origin"] == "platform"
    assert publish.after_json["override_reason"] == new.override_reason
    (passed,) = await _audit(tenant_id, "reservations.passed")
    assert passed.actor == ACTOR
    assert passed.after_json["automatic"] is True
    assert passed.after_json["activated"] is None
    assert [p["agent_id"] for p in passed.after_json["published"]] == [str(agent_id)]
    assert passed.after_json["published"][0]["number"] == new.agent_version_number


async def test_the_pass_follows_the_fixed_map_and_grants_nothing_else(
    db_session, console_world
) -> None:
    """Spec 048 R3.3 «con el mapa fijo» (T217, security review of 2026-10-30; plan,
    decision 26): an agent that could only look at the agenda does not come out of
    the pass able to book, cancel or move appointments. The published version gets
    the 1:1 map of ``agent_spec.retired`` plus ``reservas.services`` — the ids of
    the services that ``reservas.find_slots`` asks for (decision 19) — and no other
    ``reservas.*``. The partner's draft is rewritten the same way."""
    w = console_world["a"]
    tenant_id = w["tenant_id"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tenant_id)
    agent_id = await agent_with_booking(db_session, tenant_id, draft=True)
    looks_only = ["booking.check_availability", "escalate.escalate_to_human"]

    async def narrow(session):  # type: ignore[no-untyped-def]
        for cfg in (
            await session.execute(sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id))
        ).scalars():
            spec = dict(cfg.spec)
            spec["tools"] = list(looks_only)
            spec["procedures"] = [
                {
                    **spec["procedures"][0],
                    "tools": ["booking.check_availability"],
                    "steps": "Mira el hueco con booking.check_availability.",
                }
            ]
            cfg.spec = spec
            cfg.tools = list(looks_only)
            cfg.system_prompt_rendered = "Antes de dar una hora, booking.check_availability."
        await session.flush()

    await read(tenant_id, narrow)
    summary = await _run()
    assert summary.passed == [tenant_id]

    _old, draft, new = await _versions(tenant_id, agent_id)
    expected = {"reservas.find_slots", "reservas.services", "escalate.escalate_to_human"}
    for cfg in (new, draft):
        assert set(cfg.tools) == expected, cfg.tools
        assert set(cfg.spec["tools"]) == expected, cfg.spec["tools"]
        assert cfg.spec["procedures"][0]["tools"] == ["reservas.find_slots"]
        assert "reservas.find_slots" in cfg.system_prompt_rendered
    assert new.status == AgentConfigStatus.ACTIVE and draft.status == AgentConfigStatus.STAGED


# ── scenario 3 and requirement 3.4: the partner's draft ────────────────────


async def test_a_partner_draft_is_rewritten_and_not_published(db_session, console_world) -> None:
    w = console_world["a"]
    tenant_id = w["tenant_id"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tenant_id)
    reception = await agent_with_booking(db_session, tenant_id, draft=True)

    # Ventas: its active version does not book, its draft does → only the draft.
    ventas = Agent(tenant_id=tenant_id, name="Ventas")
    # Soporte: nothing with booking.* → nothing happens to it.
    soporte = Agent(tenant_id=tenant_id, name="Soporte")
    db_session.add_all([ventas, soporte])
    await db_session.flush()
    db_session.add_all(
        [plain_version(tenant_id, ventas.id, 10), plain_version(tenant_id, soporte.id, 20)]
    )
    await db_session.flush()
    staged = plain_version(tenant_id, ventas.id, 11, status=AgentConfigStatus.STAGED)
    staged.tools = [*BOOKING]
    db_session.add(staged)
    await db_session.commit()

    async def revision(session):  # type: ignore[no-untyped-def]
        return await session.scalar(sa.select(Agent.draft_revision).where(Agent.id == reception))

    before = await read(tenant_id, revision)
    summary = await _run()
    assert summary.passed == [tenant_id]
    assert summary.published == 1
    assert summary.drafts == 2

    old, draft, new = await _versions(tenant_id, reception)
    assert (old.status, draft.status, new.status) == (
        AgentConfigStatus.ARCHIVED,
        AgentConfigStatus.STAGED,
        AgentConfigStatus.ACTIVE,
    )
    # Published from the ACTIVE version: the partner's sentence is not live.
    _no_booking(new)
    assert "Somos la mejor barbería" not in new.system_prompt_rendered
    assert new.base_version_id == old.id
    # The draft says reservas.* too, keeps the partner's change and stays a draft.
    _no_booking(draft)
    assert "Somos la mejor barbería del barrio." in draft.system_prompt_rendered
    # One write on the draft, as any writer: a tab editing it is told.
    assert await read(tenant_id, revision) == before + 1
    stage = [
        r
        for r in await _audit(tenant_id, "agent_config.stage")
        if r.after_json["agent"] == str(reception)
    ]
    assert [(r.actor, r.after_json["created"]) for r in stage] == [(ACTOR, False)]
    assert {"tools", "system_prompt"} <= set(stage[0].after_json["fields"])

    ventas_versions = await _versions(tenant_id, ventas.id)
    assert [v.status for v in ventas_versions] == [
        AgentConfigStatus.ACTIVE,
        AgentConfigStatus.STAGED,
    ]
    assert ventas_versions[0].tools == ["escalate.escalate_to_human"]
    assert not [t for t in ventas_versions[1].tools if t.startswith("booking.")]
    assert "reservas.create" in ventas_versions[1].tools

    assert [v.version for v in await _versions(tenant_id, soporte.id)] == [20]

    (passed,) = await _audit(tenant_id, "reservations.passed")
    assert {a["agent_id"] for a in passed.after_json["agents"]} == {str(reception), str(ventas.id)}


# ── scenario 4 and requirement 3.5: the appointments ───────────────────────


async def _legacy_appointments(db_session, tenant_id: uuid.UUID) -> dict[str, Any]:
    cust = await customer(db_session, tenant_id)
    lucia = await barber(db_session, tenant_id, "Lucia")  # no accent: it matches anyway
    base = (_now() + timedelta(days=4)).replace(hour=15, minute=0, second=0, microsecond=0)
    corte = appointment(tenant_id, cust, lucia, "corte", base)
    color = appointment(tenant_id, cust, lucia, " COLOR ", base + timedelta(hours=2), minutes=90)
    masaje = appointment(tenant_id, cust, lucia, "Masaje", base + timedelta(days=1))
    past = appointment(tenant_id, cust, lucia, "Corte", base - timedelta(days=30))
    gone = appointment(
        tenant_id,
        cust,
        lucia,
        "Corte",
        base + timedelta(days=2),
        status=AppointmentStatus.CANCELLED,
    )
    db_session.add_all([corte, color, masaje, past, gone])
    await db_session.commit()
    return {"customer": cust, "corte": corte.id, "color": color.id, "masaje": masaje.id}


async def test_future_appointments_are_imported_with_a_report(db_session, console_world) -> None:
    w = console_world["a"]
    tenant_id = w["tenant_id"]
    res = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tenant_id)
    await agent_with_booking(db_session, tenant_id)
    appts = await _legacy_appointments(db_session, tenant_id)

    summary = await _run()
    assert (summary.imported, summary.not_imported) == (2, 1)

    async def reservations(session):  # type: ignore[no-untyped-def]
        return list((await session.execute(sa.select(Reservation))).scalars())

    rows = {r.idempotency_key: r for r in await read(tenant_id, reservations)}
    assert set(rows) == {f"appointment:{appts['corte']}", f"appointment:{appts['color']}"}
    corte = rows[f"appointment:{appts['corte']}"]
    assert (corte.staff_id, corte.service_id, corte.status) == (
        res["lucia"],
        res["corte"],
        "confirmed",
    )
    assert (corte.customer_id, corte.contact_name) == (appts["customer"], "Ana Pérez")
    color = rows[f"appointment:{appts['color']}"]
    assert color.service_id == res["color"]
    assert color.ends_at - color.starts_at == timedelta(minutes=90)

    async def outbox(session):  # type: ignore[no-untyped-def]
        return list((await session.execute(sa.select(ReservationOutbox))).scalars())

    assert await read(tenant_id, outbox) == [], "nobody gets a message"

    async def masaje(session):  # type: ignore[no-untyped-def]
        return await session.get(Appointment, appts["masaje"])

    assert await read(tenant_id, masaje) is not None, "what does not pass stays"

    (passed,) = await _audit(tenant_id, "reservations.passed")
    assert passed.after_json["imported"] == 2
    assert [(n["appointment_id"], n["reason"]) for n in passed.after_json["not_imported"]] == [
        (str(appts["masaje"]), "service_missing")
    ]


async def test_a_freshly_activated_client_keeps_its_appointments_in_the_report(
    db_session, console_world
) -> None:
    """Reservas starts empty: nothing matches and nothing is lost (decision 14)."""
    w = console_world["b"]
    tenant_id = w["tenant_id"]
    await agent_with_booking(db_session, tenant_id)
    appts = await _legacy_appointments(db_session, tenant_id)

    summary = await _run()
    assert summary.passed == [tenant_id]
    assert (summary.imported, summary.not_imported) == (0, 3)
    (passed,) = await _audit(tenant_id, "reservations.passed")
    assert sorted(n["reason"] for n in passed.after_json["not_imported"]) == ["service_missing"] * 3

    async def left(session):  # type: ignore[no-untyped-def]
        return await session.scalar(sa.select(sa.func.count()).select_from(Appointment))

    assert await read(tenant_id, left) == 5
    assert appts["customer"] is not None


# ── scenario 5 and requirement 3.6: a second run finds nobody ──────────────


async def test_a_second_run_finds_nobody_and_duplicates_nothing(db_session, console_world) -> None:
    w = console_world["a"]
    tenant_id = w["tenant_id"]
    await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=tenant_id)
    agent_id = await agent_with_booking(db_session, tenant_id, draft=True)
    await _legacy_appointments(db_session, tenant_id)

    first = await _run()
    assert first.passed == [tenant_id]
    versions = [(v.version, v.status) for v in await _versions(tenant_id, agent_id)]

    second = await _run()
    assert (second.passed, second.failed) == ([], [])
    assert (second.published, second.drafts, second.imported) == (0, 0, 0)
    assert [(v.version, v.status) for v in await _versions(tenant_id, agent_id)] == versions

    async def reservations(session):  # type: ignore[no-untyped-def]
        return await session.scalar(sa.select(sa.func.count()).select_from(Reservation))

    assert await read(tenant_id, reservations) == 2
    assert len(await _audit(tenant_id, "reservations.passed")) == 1


# ── scenario 6 and requirement 3.7: one client fails, the others pass ──────


async def test_a_failing_client_is_rolled_back_alone_and_logged(
    db_session, console_world, monkeypatch
) -> None:
    from nexus_api.services.reservations import passing

    a, b = console_world["a"], console_world["b"]
    await business_sector(db_session, a["tenant_id"], "barberia_peluqueria")
    await business_sector(db_session, b["tenant_id"], "restaurante")
    agent_a = await agent_with_booking(db_session, a["tenant_id"])
    agent_b = await agent_with_booking(db_session, b["tenant_id"], draft=True, tests=True)
    await _legacy_appointments(db_session, b["tenant_id"])

    real = passing.import_appointments

    async def flaky(session, tenant_id, *, now):  # type: ignore[no-untyped-def]
        if tenant_id == b["tenant_id"]:
            # After the activation, the publish and the draft: all of it goes back.
            raise RuntimeError("boom")
        return await real(session, tenant_id, now=now)

    monkeypatch.setattr(passing, "import_appointments", flaky)

    with capture_logs() as logs:
        summary = await _run()

    assert summary.passed == [a["tenant_id"]]
    assert summary.failed == [b["tenant_id"]]

    # A passed.
    assert [v.status for v in await _versions(a["tenant_id"], agent_a)] == [
        AgentConfigStatus.ARCHIVED,
        AgentConfigStatus.ACTIVE,
    ]
    # B is as it was: no Reservas, the same two versions, its tests fresh, no audit.
    versions_b = await _versions(b["tenant_id"], agent_b)
    assert [(v.version, v.status) for v in versions_b] == [
        (1, AgentConfigStatus.ACTIVE),
        (2, AgentConfigStatus.STAGED),
    ]
    assert set(BOOKING) <= set(versions_b[0].tools)
    assert set(BOOKING) <= set(versions_b[1].tools)

    async def b_state(session):  # type: ignore[no-untyped-def]
        return (
            await session.get(ReservationSettings, b["tenant_id"]),
            await session.get(ClientAccess, b["tenant_id"]),
            [t.stale for t in (await session.execute(sa.select(AgentTest))).scalars()],
            await session.scalar(sa.select(sa.func.count()).select_from(AuditLog)),
        )

    settings_b, access_b, stale_b, audit_b = await read(b["tenant_id"], b_state)
    assert (settings_b, access_b, stale_b, audit_b) == (None, None, [False], 0)

    failed = [e for e in logs if e["event"] == "reservations.auto_pass_failed"]
    assert [e["tenant_id"] for e in failed] == [str(b["tenant_id"])]
    assert "RuntimeError" in failed[0]["error"]
    (done,) = [e for e in logs if e["event"] == "reservations.auto_pass_done"]
    assert (done["passed"], done["failed"]) == (1, 1)
    assert done["failed_tenants"] == [str(b["tenant_id"])]
    for key in ("activated", "published", "drafts", "imported", "not_imported"):
        assert key in done, key


async def test_the_release_script_runs_the_pass_and_exits_zero(
    db_session, console_world, monkeypatch
) -> None:
    """``scripts/pass_booking_to_reservas.py``, as ``release.sh`` calls it: it
    passes who it can and exits 0 even if a client fails."""
    import importlib.util
    from pathlib import Path

    from nexus_api.services.reservations import passing

    a, b = console_world["a"], console_world["b"]
    agent_a = await agent_with_booking(db_session, a["tenant_id"])
    await agent_with_booking(db_session, b["tenant_id"])

    real = passing.import_appointments

    async def flaky(session, tenant_id, *, now):  # type: ignore[no-untyped-def]
        if tenant_id == b["tenant_id"]:
            raise RuntimeError("boom")
        return await real(session, tenant_id, now=now)

    monkeypatch.setattr(passing, "import_appointments", flaky)

    script = Path(__file__).resolve().parents[3] / "scripts" / "pass_booking_to_reservas.py"
    spec = importlib.util.spec_from_file_location("pass_booking_to_reservas_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert await module.main() == 0
    assert [v.status for v in await _versions(a["tenant_id"], agent_a)][-1] == (
        AgentConfigStatus.ACTIVE
    )
    assert len(await _versions(a["tenant_id"], agent_a)) == 2


# ── requirement 3.8: nothing by hand ───────────────────────────────────────


async def test_the_manual_pass_routes_are_gone(
    client, db_session, console_world, admin_headers
) -> None:
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    h = {**admin_headers, "X-Operator-Id": str(op.id)}
    tenant_id = console_world["a"]["tenant_id"]
    assert (await client.get("/admin/reservas/legacy-booking", headers=h)).status_code == 404
    assert (
        await client.post(f"/admin/tenants/{tenant_id}/reservas/pass", headers=h)
    ).status_code == 404
