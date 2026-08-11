"""El ack del webhook cuesta un número ACOTADO de viajes a Postgres.

El gate de la Fase 1 pide ``webhook_ack_ms`` p95 < 50 ms y la campaña de
carga del 2026-08-09 midió ~120. Sacar el acuse de lectura del handler
quitó el trozo grande; lo que quedaba eran idas y vueltas a la base en
serie dentro del propio handler, cada una barata y todas juntas caras.

Este test cuenta sentencias, no milisegundos. Un test de latencia en CI
mide sobre todo el ruido de la máquina; el número de viajes es
determinista y es la magnitud que de verdad se optimizó. Si alguien
vuelve a separar la consulta combinada en tres, o reintroduce la búsqueda
del canal de Auphere sin caché, esto se pone rojo el mismo día — y no
tres semanas después, en la siguiente campaña de carga.

El tope deja un margen pequeño sobre el mínimo medido: no se
trata de congelar el plan exacto, sino de impedir que vuelva a crecer.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from sqlalchemy import event, text

pytestmark = pytest.mark.asyncio

META_APP_SECRET = "dev-meta-app-secret-change-me"

# Medido: con las cachés calientes el ack son DOS sentencias — el
# ``set_config`` combinado (tenant + rol) y la consulta combinada del
# preludio. El tope deja una de margen y nada más: con tres consultas
# separadas serían cuatro y esto tiene que ponerse rojo.
MAX_STATEMENTS = 3


def _hub_sig(body: bytes) -> str:
    return sign_meta_request(META_APP_SECRET, body)


@contextmanager
def _count_statements(engine):
    """Cuenta sentencias sobre el engine SÍNCRONO subyacente — es donde
    SQLAlchemy emite los eventos, incluso con el driver asyncpg."""
    seen: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        # Sin truncar: las aserciones inspeccionan el cuerpo de la consulta
        # combinada, que pasa holgadamente de 120 caracteres.
        seen.append(" ".join(statement.split()))

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before)
    try:
        yield seen
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before)


def _envelope(*, business_phone: str, sender: str, wamid: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business_phone.lstrip("+"),
                                "phone_number_id": "PN-ACK",
                            },
                            "contacts": [{"profile": {"name": "Cliente"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": wamid,
                                    "timestamp": "1716300000",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


async def _seed_channel(db_session, tenant_id, business_phone: str) -> None:
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=business_phone,
                status=ChannelStatus.ACTIVE,
                config={"waba_id": "WABA1", "phone_number_id": "PN-ACK"},
            )
        )


async def test_a_warm_inbound_ack_stays_under_the_roundtrip_budget(
    client, db_session, fake_redis, seed_tenants
) -> None:
    from nexus_api.db.base import get_engine

    tenant_id = seed_tenants["a"]
    business_phone = "+56988880001"
    await _seed_channel(db_session, tenant_id, business_phone)

    async def _post(wamid: str):
        body = json.dumps(
            _envelope(business_phone=business_phone, sender="56911110001", wamid=wamid)
        ).encode()
        return await client.post(
            "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
        )

    # Primera petición: calienta las cachés de Redis (tenant, tier y el
    # conjunto de números de Auphere). Lo que se mide es el estado
    # estacionario, que es el que ve el 99,99% del tráfico.
    assert (await _post("wamid.ack-warm")).json()["status"] == "ok"

    with _count_statements(get_engine()) as statements:
        r = await _post("wamid.ack-measured")

    assert r.json()["status"] == "ok"
    assert len(statements) <= MAX_STATEMENTS, (
        f"el ack hizo {len(statements)} sentencias (tope {MAX_STATEMENTS}):\n"
        + "\n".join(f"  - {s[:160]}" for s in statements)
    )


async def test_the_prelude_is_a_single_statement(
    client, db_session, fake_redis, seed_tenants
) -> None:
    """El dedupe durable, el canal y las políticas del agente viajan
    juntos. Separarlos otra vez no rompe ninguna aserción funcional —
    solo triplica los viajes— así que hace falta afirmarlo aquí."""
    from nexus_api.db.base import get_engine

    tenant_id = seed_tenants["a"]
    business_phone = "+56988880002"
    await _seed_channel(db_session, tenant_id, business_phone)

    body = json.dumps(
        _envelope(business_phone=business_phone, sender="56911110002", wamid="wamid.ack-single")
    ).encode()
    with _count_statements(get_engine()) as statements:
        await client.post(
            "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
        )

    reads = [
        s
        for s in statements
        if "FROM messages" in s or "FROM channels" in s or "FROM agent_configs" in s
    ]
    assert len(reads) == 1, (
        "el preludio del ack volvió a partirse en varias consultas:\n"
        + "\n".join(f"  - {s[:160]}" for s in reads)
    )
    assert "FROM messages" in reads[0]
    assert "FROM channels" in reads[0]
    assert "FROM agent_configs" in reads[0]


async def test_the_auphere_number_lookup_does_not_hit_the_db_on_tenant_traffic(
    client, db_session, fake_redis, seed_tenants
) -> None:
    """El registro de números de Auphere se consulta por Redis. Para el
    tráfico de tenants la respuesta siempre es "no", y averiguarlo contra
    Postgres era un viaje por cada mensaje entrante del sistema."""
    from nexus_api.db.base import get_engine

    tenant_id = seed_tenants["a"]
    business_phone = "+56988880003"
    await _seed_channel(db_session, tenant_id, business_phone)

    for wamid in ("wamid.ack-owner-warm", "wamid.ack-owner-measured"):
        body = json.dumps(
            _envelope(business_phone=business_phone, sender="56911110003", wamid=wamid)
        ).encode()
        with _count_statements(get_engine()) as statements:
            await client.post(
                "/webhook/meta", content=body, headers={"X-Hub-Signature-256": _hub_sig(body)}
            )

    assert not [s for s in statements if "auphere_owner_channels" in s], (
        "la resolución del canal Auphere volvió a la base en el camino caliente"
    )
