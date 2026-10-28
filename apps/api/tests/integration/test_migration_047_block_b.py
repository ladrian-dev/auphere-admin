"""Spec 047, bloque B — las migraciones 0176 a 0180 dejan lo que la ola 1, la ola 2 y
el router dan por hecho (T031, T023, T039, T046, T139).

Lo que se fija aquí es lo que vive en la base y no en un servicio:

- **0176**: el motivo de espera es de la lista cerrada; un efecto con efecto se
  guarda una vez por clave y cliente; el resolutor de números reconoce los
  canales en pausa y con problemas, y no los desconectados.
- **0177**: la partida es de su lista y los orígenes de «Construcción y pruebas»
  caben en ``source``.
- **0178**: como mucho un borrador por agente; el número «v{n}» lo pone la base,
  por agente y no por cliente.
- **0179**: la ficha rechaza un nicho de menos de 2 caracteres y un enlace repetido.
- **0180**: la oferta fija de hoy y los precios pasan a datos, con su vigencia, y
  la taxonomía v1 trae sus 15 tareas.

La RLS FORCE y las FK compuestas de todas las tablas nuevas las barre ``test_43``;
la ida y vuelta, ``test_migration_reversibility.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _exec(sql: str, *, tenant: uuid.UUID | None = None, **params: Any) -> list[Any]:
    """One transaction. With ``tenant``, as ``nexus_app`` under that client."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            if tenant is not None:
                await conn.execute(
                    sa.text(
                        "SELECT set_config('app.tenant_id', :t, true), "
                        "set_config('role', 'nexus_app', true)"
                    ),
                    {"t": str(tenant)},
                )
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _tenant() -> uuid.UUID:
    tid = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'B', :s, 'pro', 'active')",
        i=tid,
        s=f"b-{tid.hex[:10]}",
    )
    return tid


async def _agent(tenant: uuid.UUID, name: str = "Recepción") -> uuid.UUID:
    aid = uuid.uuid4()
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status) VALUES (:a, :t, :n, 'active')",
        a=aid,
        t=tenant,
        n=name,
    )
    return aid


async def _version(tenant: uuid.UUID, agent: uuid.UUID, version: int, status: str) -> list[Any]:
    return await _exec(
        "INSERT INTO agent_configs (tenant_id, agent_id, version, status, system_prompt_rendered) "
        "VALUES (:t, :a, :v, CAST(:s AS agent_config_status), 'Eres X.') "
        "RETURNING agent_version_number",
        t=tenant,
        a=agent,
        v=version,
        s=status,
    )


async def _channel(tenant: uuid.UUID, status: str) -> str:
    identifier = f"pnid-{uuid.uuid4().hex[:12]}"
    await _exec(
        "INSERT INTO channels (tenant_id, type, provider, provider_identifier, status) "
        "VALUES (:t, 'whatsapp', 'meta', :i, CAST(:s AS channel_status))",
        t=tenant,
        i=identifier,
        s=status,
    )
    return identifier


@pytest.fixture
async def _clean() -> Any:
    yield
    await _exec(
        "TRUNCATE TABLE turn_effects, meta_reconciliation_runs, business_profiles, "
        "business_links, agent_model_certifications, router_anomalies, agent_configs, "
        "channels, agents, tenants RESTART IDENTITY CASCADE"
    )


# ── 0176 ───────────────────────────────────────────────────────────────


async def test_waiting_reason_is_a_closed_list(_clean: Any) -> None:
    rows = await _exec(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'ck_conversations_waiting_reason'"
    )
    assert rows, "conversations has no waiting_reason CHECK"
    for code in ("no_balance", "paused_channel", "provider_failure", "human_takeover"):
        assert code in rows[0][0]


async def test_a_turn_effect_happens_once_per_key(_clean: Any) -> None:
    tenant, other = await _tenant(), await _tenant()
    turn = uuid.uuid4()
    insert = (
        "INSERT INTO turn_effects (tenant_id, turn_id, effect, idempotency_key) "
        "VALUES (:t, :turn, 'book', :k)"
    )
    await _exec(insert, tenant=tenant, t=tenant, turn=turn, k=f"{turn}:book")
    with pytest.raises(IntegrityError):
        await _exec(insert, tenant=tenant, t=tenant, turn=turn, k=f"{turn}:book")
    # The key is per client: another client's same key is another effect.
    await _exec(insert, tenant=other, t=other, turn=turn, k=f"{turn}:book")
    assert await _exec("SELECT count(*) FROM turn_effects", tenant=tenant) == [(1,)]


async def test_the_resolver_knows_paused_and_degraded_numbers(_clean: Any) -> None:
    tenant = await _tenant()
    found = {}
    for status in ("active", "paused", "degraded", "disconnected"):
        identifier = await _channel(tenant, status)
        rows = await _exec(
            "SELECT set_config('role', 'nexus_app', true), resolve_channel_tenant('meta', :i)",
            i=identifier,
        )
        found[status] = rows[0][1]
    assert found == {
        "active": tenant,
        "paused": tenant,
        "degraded": tenant,
        "disconnected": None,
    }


async def test_reconciliation_points_at_its_own_channel(_clean: Any) -> None:
    a, b = await _tenant(), await _tenant()
    await _channel(b, "active")
    channel_b = (await _exec("SELECT id FROM channels WHERE tenant_id = :t", t=b))[0][0]
    with pytest.raises(IntegrityError):  # composite FK: A cannot point at B's number
        await _exec(
            "INSERT INTO meta_reconciliation_runs "
            "(tenant_id, channel_id, date, meta_count, stored_count, diff) "
            "VALUES (:t, :c, current_date, 3, 3, 0)",
            t=a,
            c=channel_b,
        )


# ── 0177 ───────────────────────────────────────────────────────────────


async def test_usage_line_and_build_sources(_clean: Any) -> None:
    rows = await _exec(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname IN ('ck_usage_line', 'ck_usage_source') "
        "AND conrelid = 'usage_records'::regclass"
    )
    defs = dict(rows)
    for line in ("conversations", "build", "companion"):
        assert line in defs["ck_usage_line"]
    for source in ("builder", "tests", "reader", "indexer", "suggestions", "certification"):
        assert source in defs["ck_usage_source"]
    columns = {
        row[0]
        for row in await _exec(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'usage_records'"
        )
    }
    assert {"task", "route_decision_id", "line"} <= columns


# ── 0178 ───────────────────────────────────────────────────────────────


async def test_one_draft_per_agent_numbered_per_agent(_clean: Any) -> None:
    tenant = await _tenant()
    recep, ventas = await _agent(tenant), await _agent(tenant, "Ventas")

    assert await _version(tenant, recep, 1, "active") == [(1,)]
    assert await _version(tenant, ventas, 2, "active") == [(1,)]  # per agent, not per client
    assert await _version(tenant, recep, 3, "staged") == [(2,)]
    with pytest.raises(IntegrityError):  # a second draft of the same agent
        await _version(tenant, recep, 4, "staged")
    assert await _version(tenant, ventas, 5, "staged") == [(2,)]

    revision = await _exec("SELECT draft_revision FROM agents WHERE id = :a", a=recep)
    assert revision == [(0,)]


# ── 0179 ───────────────────────────────────────────────────────────────


async def test_the_business_profile_holds_its_rules(_clean: Any) -> None:
    tenant = await _tenant()
    insert = "INSERT INTO business_profiles (tenant_id, niche, timezone) VALUES (:t, :n, 'Europe/Madrid')"
    with pytest.raises(IntegrityError):
        await _exec(insert, tenant=tenant, t=tenant, n="x")
    await _exec(insert, tenant=tenant, t=tenant, n="Cafetería de especialidad")

    link = "INSERT INTO business_links (tenant_id, network, handle) VALUES (:t, 'instagram', :h)"
    await _exec(link, tenant=tenant, t=tenant, h="cafeorigen")
    with pytest.raises(IntegrityError):
        await _exec(link, tenant=tenant, t=tenant, h="cafeorigen")

    other = await _tenant()
    assert await _exec("SELECT tenant_id FROM business_profiles", tenant=other) == []
    with pytest.raises(DBAPIError):  # WITH CHECK
        await _exec(insert, tenant=other, t=tenant, n="Otra ficha")


# ── 0180 ───────────────────────────────────────────────────────────────


async def test_the_offer_and_prices_are_data(_clean: Any) -> None:
    offer = await _exec(
        "SELECT model_id, offer_label FROM model_profiles WHERE offer_label IS NOT NULL "
        "ORDER BY model_id"
    )
    assert offer == [
        ("openai/gpt-5.6-luna", "Luna"),
        ("openai/gpt-5.6-sol", "Sol"),
        ("openai/gpt-5.6-terra", "Terra"),
    ]
    # Los borradores de Bedrock y Scaleway (0185, T142) entran sin precio a
    # propósito: se cargan con su fuente desde el panel antes de activarlos.
    without_price = await _exec(
        "SELECT p.model_id FROM model_profiles p "
        "LEFT JOIN model_prices m ON m.deployment_id = p.id "
        "WHERE m.deployment_id IS NULL AND p.status <> 'draft'"
    )
    assert without_price == []
    families = await _exec(
        "SELECT DISTINCT family FROM model_profiles WHERE status <> 'draft' ORDER BY 1"
    )
    assert families == [("anthropic-claude",), ("openai-gpt",)]


async def test_the_taxonomy_v1_has_its_fifteen_tasks(_clean: Any) -> None:
    rows = await _exec("SELECT jsonb_array_length(tasks) FROM router_taxonomy WHERE version = 1")
    assert rows == [(15,)]
    codes = await _exec(
        "SELECT t ->> 'code' FROM router_taxonomy, jsonb_array_elements(tasks) t "
        "WHERE version = 1 AND (t ->> 'conversation')::boolean"
    )
    assert sorted(c for (c,) in codes) == ["answer", "tool_turn"]
