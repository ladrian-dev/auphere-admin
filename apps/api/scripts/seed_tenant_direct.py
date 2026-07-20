"""Alta de un cliente directo: tenant + canal WhatsApp + API key de envío.

Herramienta operacional hasta que el panel tenga la UI para emitirlo. Crea
un tenant en modo solo-canal (sin agente), su canal de WhatsApp y una API
key ligada al tenant con scope ``messages_send``. Imprime la key en claro
UNA vez — no se puede volver a leer (solo se guarda el hash).

El canal se crea con un ``provider_identifier`` placeholder; la conexión
real de la WABA se hace después vía Embedded Signup en el panel, que
sobrescribe ese valor con el número verificado por Meta.

Uso (lee NEXUS_DATABASE_URL del entorno):

    python scripts/seed_tenant_direct.py \
        --name "New Air Climatización" --slug newair

En producción, con las credenciales inyectadas por Railway:

    railway run --service nexus-api \
        python /app/apps/api/scripts/seed_tenant_direct.py \
        --name "New Air Climatización" --slug newair
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
            partner = Partner(id=uuid.uuid4(), name="Auphere Direct", slug=DIRECT_PARTNER_SLUG)
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
