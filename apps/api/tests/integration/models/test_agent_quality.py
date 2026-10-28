"""Spec 047, T146 — la pantalla Calidad (historia 23; requisito 39).

Un catálogo sintético (``q4t/…``): un modelo barato y uno de gama alta con
inferencia en la UE y uno global, los tres certificados por clase para las tareas
del turno y con sus precios vigentes.

- **Las opciones**: cada perfil con su línea y su precio estimado por mensaje
  (coste por 2,2), comparado con el actual; del perfil del sector sin tráfico, y
  el real de 7 días después.
- **«Fijar un modelo»**: solo activo, permitido y con la residencia del cliente;
  dice si ya está certificado para este agente.
- **Sin certificar**: se comprueba con la suite del agente y la puerta no deja
  guardar el cambio hasta que pasa.
- **«Solo UE»**: filtra los perfiles y los modelos.
- **Agentes migrados**: se les propone «Automático».
- **Quién**: leer con ``agents:read``; comprobar, ``agents:write``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.runtime import model_resolver
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    Message,
    MessageDirection,
    Partner,
)
from nexus_api.db.models.agent_spec import AgentTestRun
from nexus_api.db.models.usage_record import UsageRecord
from nexus_api.services import agent_quality, publishing
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business, seed_agent

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

CHEAP, TOP, GLOBAL = "q4t/cheap-eu", "q4t/top-eu", "q4t/global"
CAPS = {
    "tools": True,
    "strict_structured_outputs": True,
    "structured_outputs": True,
    "context_window": 200_000,
}


async def _deployment(
    key: str, *, residency: str, price_in: str, price_out: str, tier: str
) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                """
                INSERT INTO model_profiles (
                    provider, model_id, display_name, route, family, residency, zero_retention,
                    retention_how, contract_dpa, subprocessor_listed, status, capabilities,
                    supports_tools, price_input_per_mtok, price_output_per_mtok,
                    quota_weight_input, quota_weight_cache_read, quota_weight_output
                ) VALUES (
                    'q4t', :key, :name, :key, :fam, :res, true, 'store=false', true, true,
                    'active', CAST(:caps AS jsonb), true, :pin, :pout, 0.011, 0.0011, 0.044
                )
                """
            ),
            {
                "key": key,
                "name": key.split("/")[1],
                "fam": f"fam-{key}",
                "res": residency,
                "caps": json.dumps({**CAPS, "tier": tier}),
                "pin": Decimal(price_in),
                "pout": Decimal(price_out),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_prices (deployment_id, valid_from, input, output, source_url) "
                "SELECT id, DATE '2026-01-01', :pin, :pout, 'https://example.invalid' "
                "FROM model_profiles WHERE model_id = :key"
            ),
            {"key": key, "pin": Decimal(price_in), "pout": Decimal(price_out)},
        )
        for task in ("classify", "answer", "tool_turn"):
            await session.execute(
                sa.text(
                    "INSERT INTO model_task_certifications "
                    "(deployment_id, task, battery_version, scores, quality, passed) "
                    "SELECT id, :task, (SELECT COALESCE(MAX(battery_version), 1) "
                    "FROM model_task_certifications WHERE invalidated_at IS NULL), "
                    "'{\"pass3\": 0.99}'::jsonb, 0.99, true "
                    "FROM model_profiles WHERE model_id = :key"
                ),
                {"key": key, "task": task},
            )


@pytest_asyncio.fixture(autouse=True)
async def catalog() -> AsyncIterator[None]:
    model_resolver.invalidate_catalog()
    await _deployment(CHEAP, residency="eu", price_in="0.05", price_out="0.20", tier="basic")
    await _deployment(TOP, residency="eu", price_in="0.80", price_out="3.20", tier="top")
    await _deployment(GLOBAL, residency="global", price_in="0.10", price_out="0.40", tier="medium")
    yield
    model_resolver.invalidate_catalog()
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'q4t/%'"))


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Clínica Lumen")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    # El partner puede usar los modelos de prueba (su lista es el techo, 39.7) y el
    # cliente empieza sin «Solo UE»: la prueba de la residencia lo enciende.
    from nexus_api.core.partner_allowlist import read_allowlist, replace_allowlist
    from nexus_api.core.partner_context import apply_partner_to_session

    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, biz.partner_id)
        current = await read_allowlist(session, biz.partner_id)
        await replace_allowlist(session, biz.partner_id, sorted({*current, CHEAP, TOP, GLOBAL}))
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(sa.text("UPDATE business_profiles SET eu_only = false"))
    await db_session.commit()
    return biz


async def _agent(db_session: AsyncSession, biz: Biz, policy: dict[str, Any] | None) -> uuid.UUID:
    agent_id, cfg_id = await seed_agent(db_session, biz.tenant_id, name="Recepción", prompt="Hola.")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.get(AgentConfig, cfg_id)
        assert cfg is not None
        cfg.policies = {"model_policy": policy} if policy else {}
    await db_session.commit()
    return agent_id


async def _certify(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID, *keys: str) -> None:
    """Certificados para este agente (42.3), como deja una comprobación que pasa."""
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg_id = await db_session.scalar(
            sa.select(AgentConfig.id).where(AgentConfig.agent_id == agent_id)
        )
        for key in keys:
            await db_session.execute(
                sa.text(
                    "INSERT INTO agent_model_certifications (tenant_id, agent_id, deployment_id, "
                    "agent_config_id, suite_revision, result, passed, paid_by) "
                    "SELECT :t, :a, id, :v, 1, '{}'::jsonb, true, 'partner' FROM model_profiles "
                    "WHERE model_id = :k"
                ),
                {"t": biz.tenant_id, "a": agent_id, "v": cfg_id, "k": key},
            )
    await db_session.commit()


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}/quality"


async def _quality(client: Any, biz: Biz, agent_id: uuid.UUID) -> dict[str, Any]:
    resp = await client.get(_url(biz, agent_id), headers=biz.headers())
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def test_each_option_has_its_line_and_its_estimated_price_against_the_current(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    agent_id = await _agent(db_session, biz, {"kind": "profile", "profile": "auto"})
    await _certify(db_session, biz, agent_id, CHEAP, TOP, GLOBAL)
    body = await _quality(client, biz, agent_id)
    assert body["estimate_source"] == "sector", "sin tráfico, el perfil del sector"
    assert body["allowed"] == ["change"]
    profiles = {p["profile"]: p for p in body["profiles"]}
    assert set(profiles) == {"auto", "economy", "balanced", "max"}
    assert all(p["line"] for p in profiles.values())
    assert profiles["auto"]["current"] is True
    assert profiles["auto"]["delta"] == {"amount_micros": 0, "currency": "USD"}
    for p in profiles.values():
        assert p["offered"] and p["price_per_message"]["currency"] == "USD"
    # El precio sale del router de verdad: el modelo más barato que cumple, por 2,2.
    estimate = agent_quality.SECTOR_TURN
    expected_auto = 0
    for tokens in estimate.values():
        cost = (
            Decimal(tokens.input_tokens) * Decimal("0.05")
            + Decimal(tokens.output_tokens) * Decimal("0.20")
            + Decimal(tokens.cache_read_tokens) * Decimal("0.05")
        )
        expected_auto += int(
            (
                Decimal(int(cost.to_integral_value(rounding="ROUND_CEILING"))) * Decimal("2.2")
            ).to_integral_value()
        )
    # El contrato cuenta en cien milésimas de la moneda; el router, en micro-USD.
    assert profiles["auto"]["price_per_message"]["amount_micros"] == round(expected_auto / 10)
    assert "cost" not in json.dumps(body).lower(), "precios, nunca costes (C9)"


async def test_pinning_offers_only_active_allowed_and_resident_models(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    agent_id = await _agent(db_session, biz, {"kind": "profile", "profile": "auto"})
    await _certify(db_session, biz, agent_id, CHEAP)
    body = await _quality(client, biz, agent_id)
    pinnable = {p["deployment"]: p for p in body["pinnable"] if p["deployment"].startswith("q4t/")}
    assert set(pinnable) == {CHEAP, TOP, GLOBAL}
    assert pinnable[CHEAP]["certified"] is True and pinnable[TOP]["certified"] is False

    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text("UPDATE model_profiles SET status = 'retiring' WHERE model_id = :k"), {"k": TOP}
        )
    model_resolver.invalidate_catalog()
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(sa.text("UPDATE business_profiles SET eu_only = true"))
    await db_session.commit()
    eu = await _quality(client, biz, agent_id)
    keys = {p["deployment"] for p in eu["pinnable"] if p["deployment"].startswith("q4t/")}
    assert keys == {CHEAP}, "«Solo UE» quita el global; uno que no está activo no se ofrece"
    assert eu["eu_only"] is True


async def test_an_unchecked_policy_is_checked_with_the_suite_and_only_then_saves(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(db_session, biz, {"kind": "profile", "profile": "auto"})
    policy = {"kind": "pinned", "deployment": TOP}
    bad = await client.post(
        f"{_url(biz, agent_id)}/check",
        json={"model_policy": {"kind": "pinned", "deployment": "x"}},
        headers=biz.headers(),
    )
    assert bad.status_code == 422
    started = await client.post(
        f"{_url(biz, agent_id)}/check", json={"model_policy": policy}, headers=biz.headers()
    )
    assert started.status_code == 202, started.text
    body = await _quality(client, biz, agent_id)
    top = next(p for p in body["pinnable"] if p["deployment"] == TOP)
    assert top["check"]["status"] == "queued", "«Comprobando la calidad…»"

    # La puerta no deja guardar el cambio mientras no pasa.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        active = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id)
        )
        assert active is not None
        draft = AgentConfig(
            tenant_id=biz.tenant_id,
            agent_id=agent_id,
            version=active.version + 1,
            status="staged",
            system_prompt_rendered=active.system_prompt_rendered,
            channels=[],
            tools=[],
            policies={"model_policy": policy, "console": {"ai_disclosure": {"enabled": False}}},
        )
        db_session.add(draft)
        await db_session.flush()
        from nexus_api.db.models import Agent

        agent = await db_session.get(Agent, agent_id)
        assert agent is not None
        gate = await publishing.evaluate_gate(
            db_session, agent=agent, version=draft, active=active, partner_id=biz.partner_id
        )
        assert "model_policy_unchecked" in {i["code"] for i in gate.hard}

        # La comprobación termina y pasa: el modelo queda certificado y la puerta deja.
        run = await db_session.scalar(
            sa.select(AgentTestRun).where(AgentTestRun.reason == "certification")
        )
        assert run is not None and run.model_policy == policy
        assert run.summary["check_deployments"] == [TOP]
        run.status = "done"
        await agent_quality.finish_check(db_session, run, {"rate": 95.0, "critical_failed": []})
        gate = await publishing.evaluate_gate(
            db_session, agent=agent, version=draft, active=active, partner_id=biz.partner_id
        )
        assert "model_policy_unchecked" not in {i["code"] for i in gate.hard}
    await db_session.commit()
    after = await _quality(client, biz, agent_id)
    top = next(p for p in after["pinnable"] if p["deployment"] == TOP)
    assert top["certified"] is True and top["check"]["status"] == "passed"


async def test_a_failing_check_does_not_certify(db_session: AsyncSession, biz: Biz) -> None:
    agent_id = await _agent(db_session, biz, {"kind": "profile", "profile": "auto"})
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg_id = await db_session.scalar(
            sa.select(AgentConfig.id).where(AgentConfig.agent_id == agent_id)
        )
        run = AgentTestRun(
            tenant_id=biz.tenant_id,
            agent_id=agent_id,
            agent_config_id=cfg_id,
            model_policy={"kind": "pinned", "deployment": CHEAP},
            scope="all",
            reason="certification",
            status="done",
            paid_by="partner",
            summary={"check_deployments": [CHEAP]},
        )
        db_session.add(run)
        await db_session.flush()
        verdict = await agent_quality.finish_check(
            db_session, run, {"rate": 60.0, "critical_failed": ["t1"]}
        )
        certified = await db_session.scalar(
            sa.text("SELECT count(*) FROM agent_model_certifications WHERE agent_id = :a"),
            {"a": agent_id},
        )
    await db_session.commit()
    assert verdict["passed"] is False and "critical_failed" in verdict["reasons"]
    assert certified == 0


async def test_migrated_agents_are_offered_auto_and_the_real_price_shows(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    agent_id = await _agent(db_session, biz, None)
    body = await _quality(client, biz, agent_id)
    assert body["current"] == {"kind": "legacy"} and body["suggest_auto"] is True
    assert body["real_price_7d"] is None

    async with tenant_scoped_session(db_session, biz.tenant_id):
        from nexus_api.db.models import (
            Channel,
            ChannelType,
            Conversation,
            ConversationStatus,
            Customer,
        )

        channel = Channel(
            tenant_id=biz.tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3491{uuid.uuid4().int % 10**7:07d}",
            config={},
        )
        customer = Customer(tenant_id=biz.tenant_id, identifier="34600000777", preferences={})
        db_session.add_all([channel, customer])
        await db_session.flush()
        conversation = Conversation(
            tenant_id=biz.tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        db_session.add(conversation)
        await db_session.flush()
        for n in range(4):
            db_session.add(
                Message(
                    tenant_id=biz.tenant_id,
                    conversation_id=conversation.id,
                    direction=MessageDirection.OUTBOUND,
                    content=f"r{n}",
                    tool_calls=[],
                    agent_id=agent_id,
                )
            )
        db_session.add(
            UsageRecord(
                occurred_at=datetime.now(UTC),
                tenant_id=biz.tenant_id,
                partner_id=biz.partner_id,
                meter="llm.input_tokens",
                quantity=Decimal(4000),
                cost_usd=Decimal("0.0002"),
                billable_qty=Decimal(4000),
                agent_id=agent_id,
                idempotency_key=uuid.uuid4().hex,
                task="tool_turn",
            )
        )
    await db_session.commit()
    after = await _quality(client, biz, agent_id)
    # 0,0002 USD entre 4 mensajes, por 2,2: 110 micro-USD = 11 cien milésimas.
    assert after["real_price_7d"] == {"amount_micros": 11, "currency": "USD"}


async def test_only_agents_write_checks(client: Any, db_session: AsyncSession, biz: Biz) -> None:
    agent_id = await _agent(db_session, biz, {"kind": "profile", "profile": "auto"})
    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    seen = await client.get(_url(biz, agent_id), headers=analyst["headers"]())
    assert seen.status_code == 200 and seen.json()["allowed"] == []
    denied = await client.post(
        f"{_url(biz, agent_id)}/check",
        json={"model_policy": {"kind": "profile", "profile": "economy"}},
        headers=analyst["headers"](),
    )
    assert denied.status_code == 403
