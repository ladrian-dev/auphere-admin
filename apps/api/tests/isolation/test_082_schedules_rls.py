"""Garantía 1 para las rutinas — spec 082, T003 (requisitos 1.1, 1.3 y 1.4).

Las dos tablas nuevas son de cliente, y aquí se comprueba lo que eso tiene que
significar, no que la migración las creara:

1. **RLS ENABLE y FORCE con la política canónica.** El cliente A no ve ni una
   fila del B, ni leyendo ni escribiendo.
2. **La clave foránea al agente es compuesta.** Una FK de una sola columna no
   pasa por la RLS: dejaría que una rutina del cliente A colgara del agente del
   B. Aquí se comprueba que el intento revienta.
3. **La ejecución sigue a su rutina**, con la misma clave compuesta.
4. **Borrar un cliente no deja nada**, ni rutinas ni ejecuciones.
5. **La función del barrido no filtra contenido.** `due_schedules` existe para
   que el disparador vea lo vencido de todos los clientes a la vez, y es
   `SECURITY DEFINER`: si devolviera la instrucción o la respuesta, sería un
   agujero del tamaño de la plataforma. Devuelve identificadores y horas.

`test_21`, `test_22` y `test_43` recogen estas tablas en sus barridos
estructurales. Esto es lo específico de la feature.

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError

from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio


async def _as_app_role(session, tenant_id: uuid.UUID | None) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, false)"),
        {"t": "" if tenant_id is None else str(tenant_id)},
    )
    await session.execute(sa.text("SET ROLE nexus_app"))


async def _seed_tenant_with_agent(session, tenant_id: uuid.UUID) -> uuid.UUID:
    """Un cliente con un agente, por SQL y como superusuario: el sujeto de la
    prueba es la RLS de las tablas nuevas, no la de las que ya existen."""
    await session.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, plan, status) "
            "VALUES (:t, 'rutinas rls', :s, 'essential', 'active') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"t": str(tenant_id), "s": f"rut-{tenant_id.hex[:10]}"},
    )
    agent_id = uuid.uuid4()
    await session.execute(
        sa.text("INSERT INTO agents (id, tenant_id, name) VALUES (:a, :t, 'Soporte')"),
        {"a": str(agent_id), "t": str(tenant_id)},
    )
    return agent_id


async def _insert_schedule(
    session, tenant_id: uuid.UUID, agent_id: uuid.UUID, *, name: str = "Altas de ayer"
) -> uuid.UUID:
    schedule_id = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO schedules "
            "(id, tenant_id, agent_id, name, instruction, cadence, local_time, "
            " state, next_run_at, created_by) "
            "VALUES (:i, :t, :a, :n, 'Dime qué pasó ayer.', 'daily', '09:00', "
            "        'active', :next, 'pedro@example.com')"
        ),
        {
            "i": str(schedule_id),
            "t": str(tenant_id),
            "a": str(agent_id),
            "n": name,
            "next": datetime.now(UTC) + timedelta(hours=1),
        },
    )
    return schedule_id


async def _insert_run(session, tenant_id: uuid.UUID, schedule_id: uuid.UUID) -> uuid.UUID:
    run_id = uuid.uuid4()
    await session.execute(
        sa.text(
            "INSERT INTO schedule_runs "
            "(id, tenant_id, schedule_id, scheduled_for, trigger, status, instruction) "
            "VALUES (:i, :t, :s, now(), 'schedule', 'running', 'Dime qué pasó ayer.')"
        ),
        {"i": str(run_id), "t": str(tenant_id), "s": str(schedule_id)},
    )
    return run_id


async def test_a_tenant_only_sees_its_own_schedules(db_session) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    agent_a = await _seed_tenant_with_agent(db_session, a)
    agent_b = await _seed_tenant_with_agent(db_session, b)
    schedule_a = await _insert_schedule(db_session, a, agent_a, name="La de A")
    await _insert_schedule(db_session, b, agent_b, name="La de B")
    await _insert_run(db_session, a, schedule_a)
    await db_session.commit()

    sm = get_sessionmaker()
    async with sm() as session:
        await _as_app_role(session, a)
        names = (await session.execute(sa.text("SELECT name FROM schedules"))).scalars().all()
        assert names == ["La de A"]
        runs = (await session.execute(sa.text("SELECT count(*) FROM schedule_runs"))).scalar_one()
        assert runs == 1

    async with sm() as session:
        await _as_app_role(session, b)
        names = (await session.execute(sa.text("SELECT name FROM schedules"))).scalars().all()
        assert names == ["La de B"]
        runs = (await session.execute(sa.text("SELECT count(*) FROM schedule_runs"))).scalar_one()
        assert runs == 0


async def test_a_tenant_cannot_write_into_another(db_session) -> None:
    """``WITH CHECK``: con el cliente A puesto, escribir una fila de B no cuela."""
    a, b = uuid.uuid4(), uuid.uuid4()
    agent_a = await _seed_tenant_with_agent(db_session, a)
    await _seed_tenant_with_agent(db_session, b)
    await db_session.commit()

    sm = get_sessionmaker()
    async with sm() as session:
        await _as_app_role(session, a)
        with pytest.raises((DBAPIError, IntegrityError)):
            await _insert_schedule(session, b, agent_a)
            await session.flush()


async def test_a_schedule_cannot_hang_off_another_tenants_agent(db_session) -> None:
    """La clave compuesta ``(tenant_id, agent_id)``. Con una FK de una sola
    columna esto pasaría: la comprobación de una FK no mira la RLS."""
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed_tenant_with_agent(db_session, a)
    agent_b = await _seed_tenant_with_agent(db_session, b)
    await db_session.commit()

    with pytest.raises((DBAPIError, IntegrityError)):
        await _insert_schedule(db_session, a, agent_b)
        await db_session.flush()
    await db_session.rollback()


async def test_a_run_cannot_hang_off_another_tenants_schedule(db_session) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    await _seed_tenant_with_agent(db_session, a)
    agent_b = await _seed_tenant_with_agent(db_session, b)
    schedule_b = await _insert_schedule(db_session, b, agent_b)
    await db_session.commit()

    with pytest.raises((DBAPIError, IntegrityError)):
        await _insert_run(db_session, a, schedule_b)
        await db_session.flush()
    await db_session.rollback()


async def test_the_same_slot_fires_once(db_session) -> None:
    """Requisito 7.7: lo que impide el disparo doble es la clave única, no un
    candado. Dos réplicas intentan crear la misma fila y una pierde."""
    a = uuid.uuid4()
    agent_a = await _seed_tenant_with_agent(db_session, a)
    schedule_a = await _insert_schedule(db_session, a, agent_a)
    await db_session.commit()

    slot = datetime.now(UTC).replace(microsecond=0)
    insert = sa.text(
        "INSERT INTO schedule_runs "
        "(tenant_id, schedule_id, scheduled_for, trigger, status, instruction) "
        "VALUES (:t, :s, :w, 'schedule', 'running', 'x')"
    )
    params = {"t": str(a), "s": str(schedule_a), "w": slot}

    await db_session.execute(insert, params)
    await db_session.commit()

    # La segunda réplica, con la misma hora: pierde en la base, no en el código.
    with pytest.raises((DBAPIError, IntegrityError)):
        await db_session.execute(insert, params)
        await db_session.flush()
    await db_session.rollback()


async def test_deleting_a_tenant_leaves_nothing(db_session) -> None:
    a = uuid.uuid4()
    agent_a = await _seed_tenant_with_agent(db_session, a)
    schedule_a = await _insert_schedule(db_session, a, agent_a)
    await _insert_run(db_session, a, schedule_a)
    await db_session.commit()

    await db_session.execute(sa.text("DELETE FROM tenants WHERE id = :t"), {"t": str(a)})
    await db_session.commit()

    left = (
        await db_session.execute(
            sa.text(
                "SELECT (SELECT count(*) FROM schedules WHERE tenant_id = :t) "
                "     + (SELECT count(*) FROM schedule_runs WHERE tenant_id = :t)"
            ),
            {"t": str(a)},
        )
    ).scalar_one()
    assert left == 0


async def test_due_schedules_gives_ids_and_times_and_nothing_else(db_session) -> None:
    """La función del barrido es ``SECURITY DEFINER``: ve a todos los clientes.
    Por eso sus columnas son un contrato, no un detalle."""
    columns = (
        (
            await db_session.execute(
                sa.text("SELECT unnest(proargnames) FROM pg_proc WHERE proname = 'due_schedules'")
            )
        )
        .scalars()
        .all()
    )
    returned = [c for c in columns if c not in {"", None, "max_rows"}]
    assert set(returned) == {"tenant_id", "schedule_id", "scheduled_for"}


async def test_due_schedules_only_returns_what_is_due(db_session) -> None:
    a = uuid.uuid4()
    agent_a = await _seed_tenant_with_agent(db_session, a)
    due = await _insert_schedule(db_session, a, agent_a, name="Vencida")
    await db_session.execute(
        sa.text("UPDATE schedules SET next_run_at = now() - interval '1 minute' WHERE id = :i"),
        {"i": str(due)},
    )
    await _insert_schedule(db_session, a, agent_a, name="Todavía no")
    paused = await _insert_schedule(db_session, a, agent_a, name="En pausa")
    await db_session.execute(
        sa.text(
            "UPDATE schedules SET state = 'paused', pause_reason = 'manual', "
            "next_run_at = now() - interval '1 minute' WHERE id = :i"
        ),
        {"i": str(paused)},
    )
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                sa.text("SELECT schedule_id FROM due_schedules(100) WHERE tenant_id = :t"),
                {"t": str(a)},
            )
        )
        .scalars()
        .all()
    )
    assert rows == [due]
