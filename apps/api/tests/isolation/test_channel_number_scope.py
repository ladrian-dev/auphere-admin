"""Garantía de aislamiento — el número se puede mover (spec 021, T004).

La regla de unicidad del número cambia de forma: deja de contar los canales
desvinculados. Lo que **no** cambia es la promesa: una fila de otro tenant no
se lee, no se altera, y no se averigua de quién es. Este fichero lo deja
escrito, y barre en vez de enumerar (constitución §I).

Lo que aquí no está, y dónde vive: el cuerpo exacto del 409 ``number_in_use``
—que no nombra a nadie— se comprueba por HTTP en
``tests/unit/test_endpoint_console_whatsapp.py`` (T008), donde está el arnés de
consola; aquí se comprueba la capa de abajo, la RLS.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute

from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.main import app

pytestmark = [pytest.mark.isolation]


async def set_tenant(session, tenant_id: uuid.UUID) -> None:
    """El scope de RLS, igual que el helper del conftest (que no es fixture)."""
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(sa.text("SET LOCAL ROLE nexus_app"))


PROHIBIDOS = {"tenant_id", "partner_id", "tenant", "partner"}


def _channel(tenant_id: uuid.UUID, number: str, status: ChannelStatus) -> Channel:
    return Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=number,
        config={"phone_number_id": "PN"},
        status=status,
    )


@pytest.mark.asyncio
async def test_a_released_number_of_another_tenant_neither_blocks_nor_shows(
    db_session, tenants_ab
) -> None:
    """(a) La fila desvinculada de A no bloquea a B, y B no la ve."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    number = f"+3464{uuid.uuid4().int % 10**7:07d}"
    db_session.add(_channel(a, number, ChannelStatus.DISCONNECTED))
    await db_session.commit()

    async with db_session.begin():
        await set_tenant(db_session, b)
        visibles = (
            await db_session.execute(
                sa.select(Channel.id).where(Channel.provider_identifier == number)
            )
        ).all()
        assert visibles == [], "B ve la fila desvinculada de A"
        # Y puede quedarse con el número: el índice ya no choca con la de A.
        db_session.add(_channel(b, number, ChannelStatus.ACTIVE))
        await db_session.flush()


@pytest.mark.asyncio
async def test_a_live_number_of_another_tenant_still_blocks_and_stays_untouched(
    db_session, tenants_ab
) -> None:
    """(b, capa RLS) Con el número vivo en A, B choca —y A no cambia."""
    from sqlalchemy.exc import IntegrityError

    a, b = tenants_ab["a"], tenants_ab["b"]
    number = f"+3465{uuid.uuid4().int % 10**7:07d}"
    vivo = _channel(a, number, ChannelStatus.ACTIVE)
    db_session.add(vivo)
    await db_session.commit()
    # El id se lee ahora: tras el choque y el rollback el objeto queda expirado,
    # y leerlo entonces intentaría refrescarlo fuera del bucle asíncrono.
    vivo_id = vivo.id

    with pytest.raises(IntegrityError) as exc:
        async with db_session.begin():
            await set_tenant(db_session, b)
            db_session.add(_channel(b, number, ChannelStatus.ACTIVE))
            await db_session.flush()
    assert "uq_channels_live_number" in str(exc.value.orig)

    # La sesión queda rota tras el choque: se limpia y se **relee de la base**,
    # no de la caché de identidad, que es donde vive la RLS.
    await db_session.rollback()
    fila = (
        await db_session.execute(
            sa.select(Channel.status, Channel.tenant_id).where(Channel.id == vivo_id)
        )
    ).one()
    assert fila.status is ChannelStatus.ACTIVE and fila.tenant_id == a


@pytest.mark.asyncio
async def test_disconnecting_a_foreign_channel_reads_as_absent(db_session, tenants_ab) -> None:
    """(c) Bajo el scope de B, el canal de A no existe: ni para leer ni para
    escribir. Es lo que hace que el endpoint devuelva 404 y no 403."""
    a, b = tenants_ab["a"], tenants_ab["b"]
    de_a = _channel(a, f"+3466{uuid.uuid4().int % 10**7:07d}", ChannelStatus.ACTIVE)
    db_session.add(de_a)
    await db_session.commit()

    # `session.get` contestaría desde la caché de identidad sin ir a la base;
    # la RLS solo se ve con una consulta de verdad.
    db_session.expunge_all()
    async with db_session.begin():
        await set_tenant(db_session, b)
        visto = (
            await db_session.execute(sa.select(Channel.id).where(Channel.id == de_a.id))
        ).first()
        assert visto is None, "B lee un canal de A"
        hecho = await db_session.execute(
            sa.update(Channel)
            .where(Channel.id == de_a.id)
            .values(status=ChannelStatus.DISCONNECTED)
        )
        assert hecho.rowcount == 0, "B alteró un canal de A"


def test_no_channel_route_accepts_a_destination() -> None:
    """(d) Barrido, no enumeración: ninguna ruta de canal de la consola deja
    que el llamante diga a qué tenant o partner apunta."""
    spec = app.openapi()
    rutas = [p for p in spec["paths"] if p.startswith("/console/clients/{ref}/channels")]
    assert len(rutas) >= 8, rutas
    for path in rutas:
        for metodo, op in spec["paths"][path].items():
            if metodo not in {"get", "post", "put", "patch", "delete"}:
                continue
            nombres = {p["name"] for p in op.get("parameters", [])}
            assert not (nombres & PROHIBIDOS), f"{metodo} {path} acepta {nombres & PROHIBIDOS}"
            ref = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("$ref")
            )
            if ref:
                modelo = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
                campos = set(modelo.get("properties", {}))
                assert not (campos & PROHIBIDOS), (
                    f"{metodo} {path} acepta en el cuerpo {campos & PROHIBIDOS}"
                )
    montadas = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert "/console/clients/{ref}/channels/{channel_id}/disconnect" in montadas
