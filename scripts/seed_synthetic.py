"""Seed sintético para staging (WP-25).

Genera carga realista SIN tocar jamás datos de producción (GDPR): 50
tenants sintéticos, 10.000 conversaciones y 200.000 mensajes con datos
inventados de forma determinista (``--seed`` fija el RNG). Los volúmenes
son configurables para humo local / tests.

Guardas:
  - Se niega a correr si ``NEXUS_ENVIRONMENT=production``.
  - Se niega si la BD contiene tenants cuyo slug no empiece por
    ``synthetic-`` (una BD de staging recién migrada está vacía; una BD
    con tenants reales NUNCA es un destino válido). ``--wipe`` borra los
    sintéticos previos y nada más.

Requisitos previos: migraciones en head (``alembic upgrade head``) — el
script llama a ``ensure_month_partition()`` (migración 0064) para los
meses que va a escribir en ``messages`` (particionada, 0063), y setea
``app.tenant_id`` por transacción porque RLS es FORCE.

Uso (lee NEXUS_DATABASE_URL del entorno):

    python scripts/seed_synthetic.py                    # volúmenes del plan
    python scripts/seed_synthetic.py --tenants 2 --conversations 10 --messages 200
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# El script vive en <repo>/scripts pero los modelos son de nexus-api; en
# staging corre dentro de la imagen (paquete instalado), en local basta
# con el venv de apps/api.
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantPlan,
    TenantStatus,
)

SLUG_PREFIX = "synthetic-"
HISTORY_DAYS = 90
BATCH_ROWS = 2000

FIRST_NAMES = [
    "Camila",
    "Mateo",
    "Valentina",
    "Benjamín",
    "Isidora",
    "Vicente",
    "Antonia",
    "Joaquín",
    "Florencia",
    "Tomás",
    "Emilia",
    "Agustín",
]
LAST_NAMES = [
    "Rojas",
    "Muñoz",
    "González",
    "Díaz",
    "Soto",
    "Contreras",
    "Silva",
    "Martínez",
    "Sepúlveda",
    "Morales",
    "Araya",
    "Flores",
]
BUSINESS_KINDS = [
    "Barbería",
    "Clínica",
    "Ferretería",
    "Pastelería",
    "Óptica",
    "Veterinaria",
    "Autoservicio",
    "Estudio",
    "Gimnasio",
    "Boutique",
]
INTENTS = [
    "consulta_precio",
    "agendar_cita",
    "estado_pedido",
    "reclamo",
    "consulta_horario",
    "consulta_stock",
    "saludo",
    None,
]
INBOUND_SNIPPETS = [
    "Hola, ¿tienen disponibilidad para esta semana?",
    "¿Cuánto cuesta el servicio básico?",
    "Mi pedido no ha llegado todavía",
    "¿A qué hora cierran hoy?",
    "Gracias, quedo atento",
    "¿Hacen despacho a domicilio?",
    "Quiero cambiar mi hora del viernes",
]
OUTBOUND_SNIPPETS = [
    "¡Hola! Claro que sí, tenemos horas disponibles el jueves y viernes.",
    "El servicio básico cuesta $15.000. ¿Te reservo una hora?",
    "Déjame revisar el estado de tu pedido, dame un momento.",
    "Hoy atendemos hasta las 19:00.",
    "¡Gracias a ti! Cualquier cosa me escribes.",
    "Sí, despachamos en toda la región. El envío demora 2-3 días hábiles.",
    "Listo, moví tu hora del viernes a las 16:30. ¡Te esperamos!",
]


def _dsn() -> str:
    dsn = os.environ.get("NEXUS_DATABASE_URL")
    if not dsn:
        raise SystemExit("NEXUS_DATABASE_URL no está seteada.")
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


def _refuse_if_production() -> None:
    env = os.environ.get("NEXUS_ENVIRONMENT", "").lower()
    if env == "production":
        raise SystemExit(
            "NEXUS_ENVIRONMENT=production — este script genera datos falsos "
            "y NUNCA corre contra producción. Aborto."
        )


async def _refuse_if_real_tenants(conn: AsyncConnection) -> None:
    non_synthetic = await conn.scalar(
        sa.select(sa.func.count())
        .select_from(Tenant.__table__)
        .where(~Tenant.__table__.c.slug.like(f"{SLUG_PREFIX}%"))
    )
    if non_synthetic:
        raise SystemExit(
            f"La BD tiene {non_synthetic} tenant(s) no sintéticos — esto no "
            "parece un staging vacío. Aborto (guarda GDPR: jamás mezclar "
            "seed sintético con datos reales)."
        )


async def _wipe_synthetic(conn: AsyncConnection) -> None:
    """Borra SOLO los tenants sintéticos previos (y sus filas scoped)."""
    rows = (
        (
            await conn.execute(
                sa.select(Tenant.__table__.c.id).where(
                    Tenant.__table__.c.slug.like(f"{SLUG_PREFIX}%")
                )
            )
        )
        .scalars()
        .all()
    )
    for tenant_id in rows:
        await _set_tenant_guc(conn, tenant_id)
        # Orden inverso de FKs. messages cae por CASCADE de conversations.
        await conn.execute(
            sa.delete(Conversation.__table__).where(
                Conversation.__table__.c.tenant_id == tenant_id
            )
        )
        await conn.execute(
            sa.delete(Customer.__table__).where(
                Customer.__table__.c.tenant_id == tenant_id
            )
        )
        await conn.execute(
            sa.delete(Channel.__table__).where(
                Channel.__table__.c.tenant_id == tenant_id
            )
        )
        await conn.execute(
            sa.delete(Tenant.__table__).where(Tenant.__table__.c.id == tenant_id)
        )
    print(f"wipe: {len(rows)} tenants sintéticos previos eliminados")


async def _set_tenant_guc(conn: AsyncConnection, tenant_id: uuid.UUID) -> None:
    """RLS FORCE en las tablas scoped: sin este GUC los INSERT rebotan."""
    await conn.execute(
        sa.text("SELECT set_config('app.tenant_id', :tid, false)"),
        {"tid": str(tenant_id)},
    )


async def _ensure_partitions(conn: AsyncConnection, now: datetime) -> None:
    """messages es particionada por mes (0063); asegura los meses del rango."""
    months = HISTORY_DAYS // 28 + 3  # margen: mes actual + siguiente incluidos
    first = now - timedelta(days=HISTORY_DAYS)
    for i in range(months):
        month = (first + timedelta(days=31 * i)).date().replace(day=1)
        await conn.execute(
            sa.text("SELECT ensure_month_partition('messages', :month)"),
            {"month": month},
        )


async def seed(
    *,
    tenants: int,
    conversations: int,
    messages: int,
    seed: int,
    wipe: bool,
) -> dict[str, int]:
    rng = random.Random(seed)
    now = datetime.now(UTC)
    engine = create_async_engine(_dsn())

    conv_per_tenant = max(1, conversations // tenants)
    msg_per_conv = max(1, messages // conversations)

    created = {"tenants": 0, "conversations": 0, "messages": 0}
    started = time.monotonic()

    try:
        async with engine.begin() as conn:
            if wipe:
                await _wipe_synthetic(conn)
            await _refuse_if_real_tenants(conn)
            await _ensure_partitions(conn, now)

        for t_idx in range(tenants):
            # Una transacción por tenant: el GUC de RLS es por conexión y
            # así un fallo a mitad deja tenants completos, no filas cojas.
            async with engine.begin() as conn:
                tenant_id = uuid.uuid4()
                await _set_tenant_guc(conn, tenant_id)

                kind = rng.choice(BUSINESS_KINDS)
                surname = rng.choice(LAST_NAMES)
                await conn.execute(
                    sa.insert(Tenant.__table__).values(
                        id=tenant_id,
                        name=f"{kind} {surname} (sintético)",
                        slug=f"{SLUG_PREFIX}{t_idx:03d}",
                        plan=TenantPlan.INTERNAL.value,
                        status=TenantStatus.ACTIVE.value,
                        timezone="America/Santiago",
                    )
                )

                channel_id = uuid.uuid4()
                await conn.execute(
                    sa.insert(Channel.__table__).values(
                        id=channel_id,
                        tenant_id=tenant_id,
                        type=ChannelType.WHATSAPP.value,
                        provider="whatsapp_meta",
                        # Numeración reservada de ficción — jamás un E.164 real.
                        provider_identifier=f"+5699000{t_idx:04d}",
                        config={"synthetic": True},
                        status=ChannelStatus.ACTIVE.value,
                    )
                )

                conv_rows: list[dict] = []
                msg_rows: list[dict] = []
                for c_idx in range(conv_per_tenant):
                    customer_id = uuid.uuid4()
                    conv_id = uuid.uuid4()
                    conv_start = now - timedelta(
                        days=rng.uniform(0, HISTORY_DAYS - 1), hours=rng.uniform(0, 12)
                    )
                    await conn.execute(
                        sa.insert(Customer.__table__).values(
                            id=customer_id,
                            tenant_id=tenant_id,
                            identifier=f"+5698{t_idx:03d}{c_idx:05d}",
                            name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                            preferences={},
                            created_at=conv_start,
                            updated_at=conv_start,
                        )
                    )

                    ts = conv_start
                    last_inbound = None
                    for m_idx in range(msg_per_conv):
                        ts = ts + timedelta(seconds=rng.uniform(20, 600))
                        inbound = m_idx % 2 == 0  # diálogo alternado
                        if inbound:
                            last_inbound = ts
                        msg_rows.append(
                            {
                                "id": uuid.uuid4(),
                                "tenant_id": tenant_id,
                                "conversation_id": conv_id,
                                "direction": (
                                    MessageDirection.INBOUND.value
                                    if inbound
                                    else MessageDirection.OUTBOUND.value
                                ),
                                "status": (
                                    MessageStatus.DELIVERED.value
                                    if not inbound
                                    else MessageStatus.SENT.value
                                ),
                                "content": rng.choice(
                                    INBOUND_SNIPPETS if inbound else OUTBOUND_SNIPPETS
                                ),
                                "intent": rng.choice(INTENTS) if inbound else None,
                                "cost_usd": (
                                    round(rng.uniform(0.001, 0.02), 5)
                                    if not inbound
                                    else None
                                ),
                                "latency_ms": rng.randint(800, 6000)
                                if not inbound
                                else None,
                                "model": "synthetic/none",
                                "tool_calls": [],
                                "attempts": 0,
                                "provider_message_id": f"wamid.SYN{uuid.uuid4().hex}",
                                "created_at": ts,
                                "updated_at": ts,
                            }
                        )

                    conv_rows.append(
                        {
                            "id": conv_id,
                            "tenant_id": tenant_id,
                            "channel_id": channel_id,
                            "customer_id": customer_id,
                            "status": rng.choice(
                                [
                                    ConversationStatus.OPEN.value,
                                    ConversationStatus.CLOSED.value,
                                    ConversationStatus.CLOSED.value,
                                ]
                            ),
                            "last_inbound_at": last_inbound,
                            "created_at": conv_start,
                            "updated_at": ts,
                        }
                    )

                await conn.execute(sa.insert(Conversation.__table__), conv_rows)
                for i in range(0, len(msg_rows), BATCH_ROWS):
                    await conn.execute(
                        sa.insert(Message.__table__), msg_rows[i : i + BATCH_ROWS]
                    )

                created["tenants"] += 1
                created["conversations"] += len(conv_rows)
                created["messages"] += len(msg_rows)

            done_pct = math.floor((t_idx + 1) / tenants * 100)
            if done_pct % 10 == 0 or t_idx == tenants - 1:
                print(
                    f"seed: {t_idx + 1}/{tenants} tenants — "
                    f"{created['messages']} mensajes — {done_pct}%",
                    flush=True,
                )
    finally:
        await engine.dispose()

    elapsed = time.monotonic() - started
    print(
        f"seed: listo en {elapsed:.0f}s — {created['tenants']} tenants, "
        f"{created['conversations']} conversaciones, {created['messages']} mensajes"
    )
    return created


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenants", type=int, default=50)
    parser.add_argument("--conversations", type=int, default=10_000)
    parser.add_argument("--messages", type=int, default=200_000)
    parser.add_argument(
        "--seed", type=int, default=42, help="semilla RNG (reproducible)"
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="elimina los tenants synthetic-* previos antes de sembrar",
    )
    args = parser.parse_args(argv)

    _refuse_if_production()
    asyncio.run(
        seed(
            tenants=args.tenants,
            conversations=args.conversations,
            messages=args.messages,
            seed=args.seed,
            wipe=args.wipe,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
