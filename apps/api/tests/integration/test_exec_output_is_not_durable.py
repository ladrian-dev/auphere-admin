"""La salida de un comando se ve y **no se guarda** — spec 013, Requisito 3.

Este fichero empieza por el test que afirma que algo **NO** está, y el orden no
es casual: un criterio de esa forma es el más fácil de dar por bueno sin mirar.
Se comprueba **consultando la base de datos**, no confiando en que nadie
escribió nada.

La tensión que la spec resuelve: §III dice que la auditoría cuenta qué pasó y
nunca qué dijo el comando, y eso es lo que legitima guardar el hilo de un
teammate (migración 0090). Pero quien aprueba un comando en su ordenador tiene
derecho a ver qué hizo, o está creyéndose al agente.

La salida:

* vive **solo** en Redis, con quince minutos de vida (`RESULT_TTL_SECONDS`, que
  ya valía eso: no es un número nuevo);
* la lee el turno **y** la pantalla, por dos caminos distintos, porque el del
  turno **consume** (`LPOP`) y un segundo lector no encontraría nada;
* no entra en `local_executions`, ni en la auditoría, ni en ninguna tabla.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.local_workstation import DeviceClientLink, PartnerDevice
from nexus_api.services.local_dispatch import (
    ExecutionResult,
    await_result,
    dispatch,
    publish_result,
    read_output_for_screen,
)

pytestmark = pytest.mark.asyncio

LO_QUE_IMPRIMIO = "src/main.c:42: error: 'nombre' undeclared\nmake: *** [build] Error 1\n"


async def _execution(world) -> uuid.UUID:
    sm = get_sessionmaker()
    device_id = uuid.uuid4()
    async with sm() as session, session.begin():
        session.add(
            PartnerDevice(
                id=device_id,
                partner_id=world["partner_id"],
                principal_id=world["user_id"],
                display_name="portátil",
                hostname="p.local",
                platform="macos",
            )
        )
        await session.flush()
        session.add(
            DeviceClientLink(
                id=uuid.uuid4(),
                device_id=device_id,
                tenant_id=world["tenant_id"],
                workdir="/tmp/cliente",
                created_by=world["user_id"],
            )
        )
    async with sm() as session, session.begin():
        with tenant_context(world["tenant_id"]):
            from nexus_api.core.tenant_context import apply_tenant_to_session

            await apply_tenant_to_session(session, world["tenant_id"])
            row = await dispatch(
                session,
                device_id=device_id,
                executable="make",
                argv_signature='["build"]',
                cwd_relative=None,
                grant_id=None,
                principal_id=world["user_id"],
                teammate_id=None,
                task_id=None,
            )
            return row.id


async def test_no_table_contains_what_the_command_printed(fake_redis, console_world):
    """**CE-005.** Se mira, no se confía."""
    a = console_world["a"]
    execution_id = await _execution(a)

    await publish_result(
        fake_redis,
        execution_id,
        ExecutionResult(
            outcome="completada", exit_code=1, stdout_sample=LO_QUE_IMPRIMIO, denial_code=None
        ),
    )

    # Se barre el esquema entero: cualquier columna de texto de cualquier tabla.
    sm = get_sessionmaker()
    async with sm() as session:
        tablas = (
            await session.execute(
                sa.text(
                    "select table_schema, table_name, column_name from information_schema.columns "
                    "where data_type in ('text','character varying','jsonb') "
                    "and table_schema not in ('pg_catalog','information_schema')"
                )
            )
        ).all()
        for schema, tabla, columna in tablas:
            found = (
                await session.execute(
                    sa.text(
                        f'select 1 from "{schema}"."{tabla}" '
                        f'where "{columna}"::text like :needle limit 1'
                    ),
                    {"needle": "%undeclared%"},
                )
            ).first()
            assert found is None, f"la salida del comando acabó en {schema}.{tabla}.{columna}"


async def test_the_screen_can_read_it_while_it_lasts(fake_redis, console_world):
    a = console_world["a"]
    execution_id = await _execution(a)
    await publish_result(
        fake_redis,
        execution_id,
        ExecutionResult(
            outcome="completada", exit_code=1, stdout_sample=LO_QUE_IMPRIMIO, denial_code=None
        ),
    )

    visto = await read_output_for_screen(fake_redis, execution_id)

    assert visto is not None
    assert "undeclared" in visto.stdout_sample, "es el motivo, y va por el flujo de error"
    assert visto.exit_code == 1


async def test_reading_it_does_not_steal_the_turn_its_own(fake_redis, console_world):
    """La regresión cara y silenciosa: el turno hace ``LPOP`` y se lleva el
    payload. Publicar para dos no puede dejar al modelo sin lo que acaba de
    ganar — sin esto, el agente volvería a ejecutar a ciegas."""
    a = console_world["a"]
    execution_id = await _execution(a)
    await publish_result(
        fake_redis,
        execution_id,
        ExecutionResult(
            outcome="completada", exit_code=1, stdout_sample=LO_QUE_IMPRIMIO, denial_code=None
        ),
    )

    # La pantalla mira primero…
    assert await read_output_for_screen(fake_redis, execution_id) is not None
    # …y el turno sigue recibiendo el suyo.
    del_turno = await await_result(fake_redis, execution_id, wait_seconds=1.0)
    assert del_turno is not None
    assert del_turno.stdout_sample == LO_QUE_IMPRIMIO


async def test_when_it_is_gone_it_says_so_instead_of_pretending(fake_redis, console_world):
    """R3.3 — pasados los quince minutos no hay salida, y eso **no es un
    error**: es lo que permite decirlo en pantalla en vez de dejar un hueco."""
    a = console_world["a"]
    execution_id = await _execution(a)

    # Nada publicado: es el mismo estado al que se llega cuando caduca.
    assert await read_output_for_screen(fake_redis, execution_id) is None


async def test_the_key_the_screen_reads_carries_its_own_expiry(fake_redis, console_world):
    a = console_world["a"]
    execution_id = await _execution(a)
    await publish_result(
        fake_redis,
        execution_id,
        ExecutionResult(outcome="completada", exit_code=0, stdout_sample="hola", denial_code=None),
    )

    from nexus_api.services.local_dispatch import RESULT_TTL_SECONDS, screen_key

    ttl = await fake_redis.ttl(screen_key(execution_id))
    assert 0 < ttl <= RESULT_TTL_SECONDS, "sin caducidad esto sería un almacén"
