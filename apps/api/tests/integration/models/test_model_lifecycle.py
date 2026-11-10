"""El ciclo de vida de los modelos (spec 047, T148 · requisitos 41.7, 41.8 y 41.9).

- **Retirada**: Auphere registra la fecha. Los partners con agentes fijados en
  ese modelo reciben ``model.retirement`` con 30 días o más (o en cuanto se sepa,
  si el proveedor avisa con menos) y otra vez a 7 días, con el modelo propuesto:
  el certificado para su agente, de la misma gama y con el precio más cercano.
  En la fecha, cada agente pasa al propuesto si está certificado para él, o a
  «Automático» si no, con una versión nueva (su historial) y una fila de
  auditoría. Los agentes con perfil no notan nada.
- **Precio**: un precio nuevo entra con su fecha. Si sube más de un 10 % el
  precio estimado por mensaje de un agente, su partner recibe
  ``model.price_change`` antes de que entre en vigor.
- **«No disponible»**: el router deja de usarlo desde el siguiente turno.

Contra la base de verdad, con despliegues de prueba (prefijo ``c3l-``) que se
borran al acabar: ``model_profiles`` es de plataforma y el ``conftest`` no lo
vacía. Ninguna llamada a un modelo.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.runtime import model_resolver
from nexus_worker.runtime.model_resolver import PinnedModel, RouteContext, chain_for

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig, AgentConfigStatus, ConsoleNotification
from nexus_api.services import model_lifecycle
from nexus_api.services.router_catalog import Price

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
OLD = "c3l-a/old-basic"
NEAR = "c3l-b/near-basic"
FAR = "c3l-c/far-basic"
BIG = "c3l-d/medium"
CHEAP_PRICE = {OLD: "1.00", NEAR: "1.10", FAR: "3.00", BIG: "1.05"}


async def _deployment(key: str, *, tier: str, price_in: str) -> None:
    caps = {
        "tools": True,
        "strict_structured_outputs": True,
        "structured_outputs": True,
        "context_window": 200000,
        "tier": tier,
    }
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                """
                INSERT INTO model_profiles (
                    provider, model_id, display_name, route, family, residency, zero_retention,
                    retention_how, contract_dpa, subprocessor_listed, status, capabilities,
                    supports_tools, max_context, price_input_per_mtok, price_output_per_mtok,
                    quota_weight_input, quota_weight_cache_read, quota_weight_output
                ) VALUES (
                    :provider, :key, :key, :key, 'anthropic-claude', 'eu', true, 'store=false',
                    true, true, 'active', CAST(:caps AS jsonb), true, 200000, :pin, :pout,
                    0.2, 0.02, 1
                )
                """
            ),
            {
                "provider": key.split("/")[0],
                "key": key,
                "caps": json.dumps(caps),
                "pin": Decimal(price_in),
                "pout": Decimal(price_in) * 5,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_prices (deployment_id, valid_from, input, output, source_url) "
                "SELECT id, DATE '2026-10-01', :pin, :pout, 'https://example.invalid' "
                "FROM model_profiles WHERE model_id = :key"
            ),
            {"key": key, "pin": Decimal(price_in), "pout": Decimal(price_in) * 5},
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_task_certifications "
                "(deployment_id, task, battery_version, scores, quality, passed) "
                "SELECT id, t, 1, '{}'::jsonb, 0.96, true FROM model_profiles, "
                "unnest(ARRAY['answer', 'tool_turn']) AS t WHERE model_id = :key"
            ),
            {"key": key},
        )


@pytest_asyncio.fixture
async def catalog() -> AsyncIterator[None]:
    await _deployment(OLD, tier="basic", price_in=CHEAP_PRICE[OLD])
    await _deployment(NEAR, tier="basic", price_in=CHEAP_PRICE[NEAR])
    await _deployment(FAR, tier="basic", price_in=CHEAP_PRICE[FAR])
    await _deployment(BIG, tier="medium", price_in=CHEAP_PRICE[BIG])
    model_resolver.invalidate_catalog()
    try:
        yield
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'c3l-%'"))
        model_resolver.invalidate_catalog()
        respond_catalog.reset()


async def _agent(
    tenant_id: uuid.UUID,
    name: str,
    policies: dict[str, Any],
    *,
    certified: tuple[str, ...] = (),
) -> tuple[uuid.UUID, uuid.UUID]:
    """Un agente publicado del cliente, con sus certificaciones."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent_id = uuid.uuid4()
        await session.execute(
            sa.text("INSERT INTO agents (id, tenant_id, name) VALUES (:a, :t, :n)"),
            {"a": agent_id, "t": tenant_id, "n": name},
        )
        version = (
            await session.execute(sa.select(sa.func.coalesce(sa.func.max(AgentConfig.version), 0)))
        ).scalar_one() + 1
        config = AgentConfig(
            tenant_id=tenant_id,
            agent_id=agent_id,
            version=version,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered=f"Prompt de {name}",
            channels=[],
            tools=[],
            policies=policies,
            seed_template_ref=None,
        )
        session.add(config)
        await session.flush()
        for key in certified:
            await session.execute(
                sa.text(
                    "INSERT INTO agent_model_certifications (tenant_id, agent_id, deployment_id, "
                    "agent_config_id, suite_revision, result, passed, paid_by) "
                    "SELECT :t, :a, id, :v, 1, '{}'::jsonb, true, 'auphere' "
                    "FROM model_profiles WHERE model_id = :k"
                ),
                {"t": tenant_id, "a": agent_id, "v": config.id, "k": key},
            )
        return agent_id, config.id


async def _versions(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> list[tuple[str, dict[str, Any]]]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.execute(
            sa.select(AgentConfig.status, AgentConfig.policies)
            .where(AgentConfig.agent_id == agent_id)
            .order_by(AgentConfig.version)
        )
        return [(str(getattr(s, "value", s)), dict(p or {})) for s, p in rows.all()]


async def _notices(partner_id: uuid.UUID, kind: str) -> list[ConsoleNotification]:
    async with get_sessionmaker()() as session:
        rows = await session.scalars(
            sa.select(ConsoleNotification)
            .where(ConsoleNotification.partner_id == partner_id, ConsoleNotification.kind == kind)
            .order_by(ConsoleNotification.created_at)
        )
        return list(rows.all())


def _pinned(key: str) -> dict[str, Any]:
    return {"model_policy": {"kind": "pinned", "deployment": key}}


AUTO = {"model_policy": {"kind": "profile", "profile": "auto"}}


async def _usage(tenant_id: uuid.UUID, agent_id: uuid.UUID, key: str) -> None:
    """Lo que gastó el agente con ``key`` en los últimos 30 días: un millón de
    tokens de entrada y cien mil de salida (1 + 0,5 USD al precio de hoy)."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        for meter, qty, cost in (
            ("llm.input_tokens", 1_000_000, "1.0"),
            ("llm.output_tokens", 100_000, "0.5"),
        ):
            await session.execute(
                sa.text(
                    "INSERT INTO usage_records (occurred_at, tenant_id, meter, quantity, cost_usd, "
                    "billable_qty, model, agent_id, idempotency_key, task) VALUES "
                    "(now() - interval '1 day', :t, :m, :q, :c, :q, :k, :a, :i, 'answer')"
                ),
                {
                    "t": tenant_id,
                    "m": meter,
                    "q": qty,
                    "c": Decimal(cost),
                    "k": key,
                    "a": agent_id,
                    "i": f"c3l:{agent_id}:{meter}",
                },
            )


@pytest_asyncio.fixture
async def agents(console_world, catalog) -> dict[str, Any]:
    a, b = console_world["a"], console_world["b"]
    out: dict[str, Any] = {"a": a, "b": b}
    out["certified"] = await _agent(
        a["tenant_id"], "Reservas", _pinned(OLD), certified=(NEAR, FAR, BIG)
    )
    out["uncertified"] = await _agent(a["tenant_id"], "Ventas", _pinned(OLD))
    out["profiled"] = await _agent(b["tenant_id"], "Automático", AUTO, certified=(OLD,))
    out["today"] = await _agent(b["tenant_id"], "De hoy", {"llm": {"respond_model": OLD}})
    # El de perfil no está fijado en OLD, pero el router se lo dio estos 30 días.
    await _usage(b["tenant_id"], out["profiled"][0], OLD)
    return out


# ── retirada (41.7) ────────────────────────────────────────────────────────


async def test_a_retirement_is_announced_30_and_7_days_ahead_with_the_closest_substitute(
    agents,
) -> None:
    a, b = agents["a"], agents["b"]
    proposals = await model_lifecycle.announce_retirement(
        OLD, retire_after=NOW + timedelta(days=45), actor="operator:luis@auphere.com", now=NOW
    )
    by_agent = {p.agent.agent_id: p.substitute for p in proposals}
    assert by_agent == {
        agents["certified"][0]: NEAR,
        agents["uncertified"][0]: None,
        agents["today"][0]: None,
    }, "de la misma gama y con el precio más cercano; sin certificado, «Automático»"
    assert await _notices(a["partner_id"], "model.retirement") == [], "faltan más de 30 días"

    report = await model_lifecycle.run_lifecycle(now=NOW + timedelta(days=15))
    assert report.retirement_notices == 2  # partner A y partner B
    [notice] = await _notices(a["partner_id"], "model.retirement")
    assert notice.severity == "warning"
    assert notice.payload["deployment"] == OLD
    assert notice.payload["days_left"] == 30
    assert sorted(
        (x["client_ref"], x["agent"], x["proposed"]) for x in notice.payload["agents"]
    ) == [(a["ref"], "Reservas", NEAR), (a["ref"], "Ventas", "auto")]
    assert str(a["tenant_id"]) not in json.dumps(notice.payload), "el partner ve su referencia"
    [for_b] = await _notices(b["partner_id"], "model.retirement")
    assert [x["agent"] for x in for_b.payload["agents"]] == ["De hoy"], (
        "el agente con perfil no se entera: el router deja de elegirlo"
    )

    again = await model_lifecycle.run_lifecycle(now=NOW + timedelta(days=16))
    assert again.retirement_notices == 0, "uno por despliegue y partner a 30 días"
    await model_lifecycle.run_lifecycle(now=NOW + timedelta(days=38))
    assert [
        n.payload["days_left"] for n in await _notices(a["partner_id"], "model.retirement")
    ] == [
        30,
        7,
    ]


async def test_a_short_notice_retirement_is_announced_at_once(agents) -> None:
    a = agents["a"]
    await model_lifecycle.announce_retirement(
        OLD, retire_after=NOW + timedelta(days=10), actor="operator:luis@auphere.com", now=NOW
    )
    [notice] = await _notices(a["partner_id"], "model.retirement")
    assert notice.payload["days_left"] == 10


async def test_on_the_date_the_agents_move_with_their_history(agents) -> None:
    a, b = agents["a"], agents["b"]
    await model_lifecycle.announce_retirement(
        OLD, retire_after=NOW + timedelta(days=30), actor="operator:luis@auphere.com", now=NOW
    )
    report = await model_lifecycle.run_lifecycle(now=NOW + timedelta(days=30, minutes=1))
    assert report.retired == [OLD]
    assert report.moved_agents == 3

    certified = await _versions(a["tenant_id"], agents["certified"][0])
    assert certified == [
        ("archived", _pinned(OLD)),
        ("active", {"model_policy": {"kind": "pinned", "deployment": NEAR}}),
    ]
    uncertified = await _versions(a["tenant_id"], agents["uncertified"][0])
    assert uncertified[-1] == ("active", AUTO)
    today = await _versions(b["tenant_id"], agents["today"][0])
    assert today[-1][0] == "active" and today[-1][1]["model_policy"] == AUTO["model_policy"]
    assert today[-1][1]["llm"] == {"respond_model": OLD}, "lo demás de la versión, igual"
    assert len(await _versions(b["tenant_id"], agents["profiled"][0])) == 1

    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        audit = (
            await session.execute(
                sa.text(
                    "SELECT actor, after_json AS after FROM audit_log "
                    "WHERE action = 'agent.quality_changed' "
                    "ORDER BY created_at"
                )
            )
        ).all()
    assert len(audit) == 2
    assert {row.actor for row in audit} == {"system:model_lifecycle"}
    assert {row.after["reason"] for row in audit} == {"model.retirement"}

    async with get_sessionmaker()() as session:
        status = await session.scalar(
            sa.text("SELECT status FROM model_profiles WHERE model_id = :k"), {"k": OLD}
        )
    assert status == "retired"
    assert (await model_lifecycle.run_lifecycle(now=NOW + timedelta(days=31))).moved_agents == 0


async def test_a_retiring_model_keeps_serving_until_its_date(agents) -> None:
    await model_lifecycle.announce_retirement(
        OLD, retire_after=NOW + timedelta(days=30), actor="operator:luis@auphere.com", now=NOW
    )
    model_resolver.invalidate_catalog()
    snapshot = await model_resolver.get_catalog_snapshot(force=True)
    assert snapshot.deployments[OLD].status == "retiring"
    decision = chain_for(
        "answer",
        snapshot.profiles["auto"],
        RouteContext(
            tenant_id=agents["b"]["tenant_id"],
            catalog=snapshot,
            agent_id=agents["certified"][0],
            agent_pinned_deployment=OLD,
        ),
    )
    assert decision.chosen == OLD and decision.outcome == "agent_pinned"


# ── precio (41.8) ──────────────────────────────────────────────────────────


async def test_a_price_rise_over_ten_percent_is_announced_before_it_takes_effect(
    agents,
) -> None:
    a, b = agents["a"], agents["b"]
    soon = NOW.date() + timedelta(days=20)
    small = Price(valid_from=soon, input=Decimal("1.04"), output=Decimal("5.2"))
    assert await model_lifecycle.add_price(OLD, small, actor="operator:x", today=NOW.date()) == []
    assert await _notices(a["partner_id"], "model.price_change") == []

    later = soon + timedelta(days=10)
    big = Price(valid_from=later, input=Decimal("1.30"), output=Decimal("6.5"))
    alerts = await model_lifecycle.add_price(OLD, big, actor="operator:x", today=NOW.date())
    assert {x.partner_id for x in alerts} == {a["partner_id"], b["partner_id"]}
    [notice] = await _notices(a["partner_id"], "model.price_change")
    assert notice.payload["deployment"] == OLD
    assert notice.payload["valid_from"] == later.isoformat()
    # Frente al precio que sustituye (el de +4 % del día 20), no al de hoy:
    # 1950 / 1560 µUSD por mensaje nominal.
    assert notice.payload["increase_pct"] == 25
    assert sorted(x["agent"] for x in notice.payload["agents"]) == ["Reservas", "Ventas"]
    [for_b] = await _notices(b["partner_id"], "model.price_change")
    assert sorted(x["agent"] for x in for_b.payload["agents"]) == ["Automático", "De hoy"], (
        "también el agente con perfil que lo usa: su precio por mensaje sube"
    )

    report = await model_lifecycle.run_lifecycle(now=NOW + timedelta(days=1))
    assert report.price_notices == 0, "uno por cambio"


async def test_a_price_enters_on_its_date(agents) -> None:
    soon = NOW.date() + timedelta(days=5)
    await model_lifecycle.add_price(
        OLD, Price(valid_from=soon, input=Decimal("1.30"), output=Decimal("6.5")), actor="x"
    )
    await model_lifecycle.run_lifecycle(now=NOW)
    async with get_sessionmaker()() as session:
        before = await session.scalar(
            sa.text("SELECT price_input_per_mtok FROM model_profiles WHERE model_id = :k"),
            {"k": OLD},
        )
    assert before == Decimal("1.000000"), "antes de su fecha, el de hoy"
    report = await model_lifecycle.run_lifecycle(now=datetime.combine(soon, NOW.timetz()))
    assert report.prices_applied == [OLD]
    async with get_sessionmaker()() as session:
        after = await session.scalar(
            sa.text("SELECT price_input_per_mtok FROM model_profiles WHERE model_id = :k"),
            {"k": OLD},
        )
    assert after == Decimal("1.300000")


# ── «No disponible» (41.9) ─────────────────────────────────────────────────


async def test_unavailable_stops_being_used_from_the_next_turn(agents) -> None:
    b = agents["b"]
    profiled, _ = agents["profiled"]
    snapshot = await model_resolver.get_catalog_snapshot(force=True)
    now = NOW.timestamp()
    ctx = RouteContext(
        tenant_id=b["tenant_id"],
        catalog=snapshot,
        agent_id=profiled,
        agent_version="v1",
        agent_certified=frozenset({OLD, NEAR}),
        pinned=PinnedModel(OLD, "v1", pinned_at=now, expires_at=now + 3600),
        now=now,
    )
    assert chain_for("answer", snapshot.profiles["auto"], ctx).chosen == OLD

    await model_lifecycle.mark_unavailable(
        OLD, actor="operator:luis@auphere.com", reason="El proveedor rompió su DPA."
    )
    fresh = await model_resolver.get_catalog_snapshot()
    decision = chain_for(
        "answer", fresh.profiles["auto"], RouteContext(**{**ctx.__dict__, "catalog": fresh})
    )
    assert decision.chosen != OLD
    assert decision.pin_broken == "status"
    async with get_sessionmaker()() as session:
        audit = (
            await session.execute(
                sa.text(
                    "SELECT actor, after_json AS after FROM audit_log "
                    "WHERE action = 'deployment.unavailable' "
                    "AND target = :t"
                ),
                {"t": f"deployment:{OLD}"},
            )
        ).one()
    assert audit.actor == "operator:luis@auphere.com"
    assert audit.after["reason"] == "El proveedor rompió su DPA."


def test_the_notice_days_are_the_contracts() -> None:
    """Research, parte 7: aviso de retirada ≥ 30 días; de precio, +10 %."""
    days, ratio = model_lifecycle.RETIREMENT_NOTICE_DAYS, model_lifecycle.PRICE_ALERT_RATIO
    assert days == (30, 7)
    assert ratio == Decimal("1.10")
