"""Spec 047, enmienda del 2026-10-29, T193 — se relee cuando cambia algo, no cada
semana (requisito 59.6; research D48).

- No hay cron de relectura (ni ``reread_due``).
- Cambiar la web o una red encola una lectura **solo si el valor cambió**; quitar
  una red no lee nada.
- Lo que escribe el propio lector no encola otra lectura.
- Añadir una fuente encola su lectura, y «Volver a leer» sigue.
"""

from __future__ import annotations

import importlib.util
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job
from nexus_api.services.business import profile_edits
from nexus_api.services.business import sources as sources_service
from nexus_api.services.business.sections import READER

from ._business_world import Biz, new_business, read, write

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SITE = "https://cultorbarber.com"


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Barbería Cultor")


async def site_reads(db_session: AsyncSession, tenant_id: uuid.UUID) -> list[Job]:
    """Las lecturas de la web y las redes del cliente (no las de una fuente)."""
    async with tenant_scoped_session(db_session, tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(Job)
                .where(Job.kind == "client_read")
                .order_by(Job.created_at, Job.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    return [j for j in rows if not (j.progress or {}).get("source_id")]


async def finish_reads(db_session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Las lecturas en cola terminan: así la siguiente no se junta con la viva."""
    async with tenant_scoped_session(db_session, tenant_id):
        await db_session.execute(
            sa.update(Job)
            .where(Job.kind == "client_read", Job.status.in_(("queued", "running")))
            .values(status="done", finished_at=sa.func.now(), result={})
        )


async def put_basics(client: Any, biz: Biz, body: dict[str, Any]) -> dict[str, Any]:
    revision = (await read(client, biz, "/basics"))["revision"]
    return await write(client, biz, "PUT", "/basics", body, revision=revision)


async def put_links(client: Any, biz: Biz, links: list[dict[str, Any]]) -> None:
    revision = next(
        s["revision"] for s in (await read(client, biz, ""))["sections"] if s["section"] == "links"
    )
    await write(client, biz, "PUT", "/links", {"links": links}, revision=revision)


def test_there_is_no_weekly_reread() -> None:
    assert importlib.util.find_spec("nexus_worker.streams.source_reread_cron") is None
    assert not hasattr(sources_service, "reread_due")
    assert not hasattr(sources_service, "REREAD_AFTER")


async def test_changing_the_web_reads_it_only_when_it_changed(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    assert await site_reads(db_session, biz.tenant_id) == [], "sin web ni redes no se lee"
    await put_basics(client, biz, {"website": SITE})
    from nexus_api.services.business.writes import drain_after_commit

    await drain_after_commit()
    (first,) = await site_reads(db_session, biz.tenant_id)
    assert first.status == "queued" and first.created_by is not None
    queued = [f for _i, f in await fake_redis.xrange("nexus:jobs") if f["job_id"] == str(first.id)]
    assert queued, "encolada para el worker al confirmar"

    await finish_reads(db_session, biz.tenant_id)
    await put_basics(client, biz, {"name": "Cultor"})
    assert len(await site_reads(db_session, biz.tenant_id)) == 1, "la web no cambió"
    await put_basics(client, biz, {"website": "https://cultorbarber.es"})
    assert len(await site_reads(db_session, biz.tenant_id)) == 2


async def test_adding_a_network_reads_it_and_removing_one_does_not(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    await put_links(client, biz, [{"network": "instagram", "handle": "cultorbarber"}])
    assert len(await site_reads(db_session, biz.tenant_id)) == 1
    await finish_reads(db_session, biz.tenant_id)
    # La misma lista otra vez: nada cambió.
    await put_links(client, biz, [{"network": "instagram", "handle": "cultorbarber"}])
    assert len(await site_reads(db_session, biz.tenant_id)) == 1
    # Quitarla no tiene nada que leer.
    await put_links(client, biz, [])
    assert len(await site_reads(db_session, biz.tenant_id)) == 1


async def test_what_the_reader_writes_does_not_read_again(
    db_session: AsyncSession, biz: Biz
) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await profile_edits.put_links(
            db_session,
            [{"network": "instagram", "handle": "cultorbarber"}],
            actor=READER,
            source="web",
            kind="read_applied",
            review="pending",
        )
        await profile_edits.update_basics(
            db_session,
            {"website": SITE},
            actor=READER,
            source="web",
            kind="read_applied",
            review="pending",
        )
    assert await site_reads(db_session, biz.tenant_id) == []


async def test_adding_a_source_reads_it_and_reading_again_still_works(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    added = await client.post(
        f"{biz.url}/sources", json={"url": f"{SITE}/precios"}, headers=biz.headers()
    )
    assert added.status_code == 202, added.text
    async with tenant_scoped_session(db_session, biz.tenant_id):
        jobs = (await db_session.scalars(sa.select(Job).where(Job.kind == "client_read"))).all()
    assert [j.progress.get("source_id") for j in jobs] == [added.json()["source"]["id"]]

    await put_basics(client, biz, {"website": SITE})
    await finish_reads(db_session, biz.tenant_id)
    again = await client.post(f"/console/clients/{biz.ref}/business/read", headers=biz.headers())
    assert again.status_code == 202, again.text
    assert len(await site_reads(db_session, biz.tenant_id)) == 2
