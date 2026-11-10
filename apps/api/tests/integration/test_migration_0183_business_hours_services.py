"""Spec 047, T055 — la 0183 deja en la base las reglas del horario y de los servicios.

Lo que sostiene la base y no un servicio (``data-model.md`` §1 a §3):

- un horario por negocio y uno por sede, nunca dos;
- un turno nocturno cierra al día siguiente (hasta 2.880 min) y no dura más de 24 h;
- una fecha especial no termina antes de empezar;
- un servicio reservable lleva duración (5 a 480, en pasos de 5) y uno no
  reservable no la lleva; «con importe» exige el importe; los de antes conservan
  su precio;
- quién ofrece un servicio apunta con FK compuesta al agente y al servicio del
  mismo cliente, y un agente nace «Atiende todos»;
- una compilación es única por versión, revisiones y variante.

La RLS FORCE y las FK compuestas de todas las tablas nuevas las barre ``test_43``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _tenant() -> uuid.UUID:
    tid = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'C', :s, 'pro', 'active')",
        i=tid,
        s=f"c-{tid.hex[:10]}",
    )
    return tid


async def _agent(tenant: uuid.UUID) -> uuid.UUID:
    rows = await _exec(
        "INSERT INTO agents (tenant_id, name, status) VALUES (:t, 'Recepción', 'active') "
        "RETURNING id",
        t=tenant,
    )
    return rows[0][0]


async def _schedule(tenant: uuid.UUID, location: uuid.UUID | None = None) -> uuid.UUID:
    rows = await _exec(
        "INSERT INTO business_schedules (tenant_id, location_id) VALUES (:t, :l) RETURNING id",
        t=tenant,
        l=location,
    )
    return rows[0][0]


async def _service(tenant: uuid.UUID, **cols: Any) -> uuid.UUID:
    fields = {"name": "Corte", "duration_minutes": 30, **cols}
    names = ", ".join(fields)
    values = ", ".join(f":{k}" for k in fields)
    rows = await _exec(
        f"INSERT INTO reservation_services (tenant_id, {names}) VALUES (:t, {values}) RETURNING id",
        t=tenant,
        **fields,
    )
    return rows[0][0]


@pytest.fixture
async def _clean() -> Any:
    yield
    await _exec("TRUNCATE TABLE agents, tenants RESTART IDENTITY CASCADE")


async def test_one_schedule_for_the_business_and_one_per_location(_clean: Any) -> None:
    tid = await _tenant()
    await _schedule(tid)
    with pytest.raises(IntegrityError):  # NULLS NOT DISTINCT: the business has one
        await _schedule(tid)
    rows = await _exec(
        "INSERT INTO business_locations (tenant_id, name) VALUES (:t, 'Providencia') RETURNING id",
        t=tid,
    )
    await _schedule(tid, rows[0][0])
    with pytest.raises(IntegrityError):
        await _schedule(tid, rows[0][0])


async def test_an_overnight_shift_closes_the_next_day_but_lasts_at_most_a_day(
    _clean: Any,
) -> None:
    tid = await _tenant()
    schedule = await _schedule(tid)
    insert = (
        "INSERT INTO business_shifts (tenant_id, schedule_id, weekday, open_min, close_min) "
        "VALUES (:t, :s, :d, :o, :c)"
    )
    await _exec(insert, t=tid, s=schedule, d=4, o=20 * 60, c=26 * 60)  # 20:00 → 02:00
    with pytest.raises(IntegrityError):  # longer than a day
        await _exec(insert, t=tid, s=schedule, d=5, o=60, c=26 * 60)
    with pytest.raises(IntegrityError):  # closes before it opens
        await _exec(insert, t=tid, s=schedule, d=5, o=600, c=540)
    with pytest.raises(IntegrityError):  # no eighth day
        await _exec(insert, t=tid, s=schedule, d=7, o=540, c=600)


async def test_a_special_date_does_not_end_before_it_starts(_clean: Any) -> None:
    tid = await _tenant()
    with pytest.raises(IntegrityError):
        await _exec(
            "INSERT INTO business_special_dates (tenant_id, name, date_from, date_to) "
            "VALUES (:t, 'Navidad', '2026-12-25', '2026-12-24')",
            t=tid,
        )


async def test_bookable_services_have_a_duration_and_the_others_do_not(_clean: Any) -> None:
    tid = await _tenant()
    await _service(tid, duration_minutes=45)  # 45 is a multiple of 5
    await _service(tid, name="Bolsa de café", bookable=False, duration_minutes=None)
    with pytest.raises(IntegrityError):  # bookable without duration
        await _service(tid, duration_minutes=None)
    with pytest.raises(IntegrityError):  # not bookable with a duration
        await _service(tid, bookable=False, duration_minutes=30)
    with pytest.raises(IntegrityError):  # «con importe» without the amount
        await _service(tid, price_kind="amount", price_minor=None)
    await _service(tid, price_kind="free")


async def test_who_offers_a_service_stays_inside_the_client(_clean: Any) -> None:
    a, b = await _tenant(), await _tenant()
    agent_a, agent_b = await _agent(a), await _agent(b)
    service_a = await _service(a)

    assert await _exec("SELECT serves_all_services FROM agents WHERE id = :i", i=agent_a) == [
        (True,)
    ]
    await _exec(
        "INSERT INTO agent_services (tenant_id, agent_id, service_id) VALUES (:t, :a, :s)",
        t=a,
        a=agent_a,
        s=service_a,
    )
    with pytest.raises(IntegrityError):  # B's agent cannot offer A's service
        await _exec(
            "INSERT INTO agent_services (tenant_id, agent_id, service_id) VALUES (:t, :a, :s)",
            t=a,
            a=agent_b,
            s=service_a,
        )


async def test_a_compilation_is_unique_per_version_and_revisions(_clean: Any) -> None:
    tid = await _tenant()
    agent = await _agent(tid)
    rows = await _exec(
        "INSERT INTO agent_configs (tenant_id, agent_id, version, status, system_prompt_rendered) "
        "VALUES (:t, :a, 1, 'active', 'Eres Sofía.') RETURNING id",
        t=tid,
        a=agent,
    )
    insert = (
        "INSERT INTO agent_version_compilations "
        "(tenant_id, agent_config_id, business_rev, knowledge_rev, tools_hash, prompt, sha256) "
        "VALUES (:t, :v, 3, 0, :h, 'Eres Sofía.', :h)"
    )
    await _exec(insert, t=tid, v=rows[0][0], h="0" * 64)
    with pytest.raises(IntegrityError):
        await _exec(insert, t=tid, v=rows[0][0], h="0" * 64)
