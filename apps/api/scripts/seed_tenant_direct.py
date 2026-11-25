"""Alta a mano de un cliente directo: tenant + canal WhatsApp + API key de envío.

**Ya no es el camino de alta (spec 077).** El alta de un cliente de solo envío se
hace desde el panel: Clientes → Nuevo cliente → «Solo envío por API», y luego
el enlace para conectar su número, la plantilla y la clave desde su ficha (ver
``docs/envio-directo.md``). Este script se conserva solo como referencia de lo
que se hizo con New Air.

Ojo si se usa: crea el canal con un ``provider_identifier`` de relleno, y al
conectar el número real por Embedded Signup se crea **otra** fila (no sobrescribe
esta), así que quedan dos números activos y la API pide ``channel_id`` o un papel
hasta que se retire el de relleno. Imprime la key en claro UNA vez.

Uso (lee NEXUS_DATABASE_URL del entorno; en AWS, con ``aws ecs run-task`` como
``scripts/ops/dlq.sh``):

    python scripts/seed_tenant_direct.py --name "New Air Climatización" --slug newair
"""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    ApiKeyScope,
    Channel,
    ChannelStatus,
    ChannelType,
    Partner,
    PartnerApiKey,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_api.services.console_v2 import born_on_new_console

# Partner contenedor para clientes directos. La FK partner_id es not-null,
# pero lo que decide el tenant es api_keys.tenant_id, no este partner.
DIRECT_PARTNER_SLUG = "auphere-direct"
# Placeholder E.164 hasta que Embedded Signup escriba el número real.
PLACEHOLDER_PHONE = "+56900000000"


def _dsn() -> str:
    dsn = os.environ.get("NEXUS_DATABASE_URL")
    if not dsn:
        raise SystemExit("NEXUS_DATABASE_URL no está seteada en el entorno.")
    # config.py normaliza, pero el engine async necesita el driver explícito.
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


async def main(name: str, slug: str, phone: str) -> None:
    engine = create_async_engine(_dsn())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session, session.begin():
        existing = await session.scalar(sa.select(Tenant).where(Tenant.slug == slug))
        if existing is not None:
            raise SystemExit(f"El tenant {slug!r} ya existe ({existing.id}). Aborto.")

        tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
        session.add(tenant)
        await session.flush()

        session.add(
            Channel(
                tenant_id=tenant.id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=phone,
                status=ChannelStatus.ACTIVE,
            )
        )

        partner = await session.scalar(
            sa.select(Partner).where(Partner.slug == DIRECT_PARTNER_SLUG)
        )
        if partner is None:
            partner = born_on_new_console(
                Partner(id=uuid.uuid4(), name="Auphere Direct", slug=DIRECT_PARTNER_SLUG)
            )
            session.add(partner)
            await session.flush()

        generated = generate_api_key()
        session.add(
            PartnerApiKey(
                partner_id=partner.id,
                tenant_id=tenant.id,
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=[ApiKeyScope.MESSAGES_SEND.value],
            )
        )

        print(f"tenant_id  = {tenant.id}")
        print(f"slug       = {slug}")
        print("API KEY    = " + generated.plaintext + "   <-- guardar ahora, no se repite")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Nombre visible del cliente")
    parser.add_argument("--slug", required=True, help="Slug corto, sin espacios (ej. newair)")
    parser.add_argument(
        "--phone",
        default=PLACEHOLDER_PHONE,
        help=f"E.164 placeholder (default {PLACEHOLDER_PHONE}); se reemplaza al conectar la WABA",
    )
    args = parser.parse_args()
    asyncio.run(main(args.name, args.slug, args.phone))
