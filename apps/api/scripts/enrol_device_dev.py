#!/usr/bin/env python3
"""Da de alta una máquina y acuña su credencial — **herramienta temporal**.

Existe porque hoy no hay forma de emparejar un dispositivo desde el producto: el
endpoint de alta existe, la superficie de uso no. El emparejamiento de verdad
—quién eres, desde dónde entras, qué máquina reclamas— es una decisión de
identidad, y esa evaluación está sin abrir. Escribir aquí un flujo provisional
para "salir del paso" sería inventar esa decisión por la puerta de atrás.

Así que esto **no es producto**: es un atajo de operador para poder probar el
recorrido antes de que exista el emparejamiento. Cuando la evaluación de
identidad cierre, este fichero se borra.

Uso, con el tenant que quieras y contra la base que quieras::

    NEXUS_DATABASE_URL_DIRECT=<url> NEXUS_DEVICE_TOKEN_SECRET=<secreto> \
      uv run python scripts/enrol_device_dev.py --tenant-slug cultor --name "MacBook de Luis" \
      --workdir /Users/luis/proyectos/cultor

Imprime el token **una sola vez**, igual que hará el producto cuando exista.
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select, text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant
from nexus_api.repositories.local_workstation import PartnerDeviceRepository
from nexus_api.services.device_credential import issue_device_token


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--name", required=True, help="Lo que verá el partner: «MacBook de Luis»")
    parser.add_argument("--workdir", required=True, help="Directorio que el partner declara")
    parser.add_argument("--platform", default="macos", choices=("macos", "windows"))
    parser.add_argument("--principal", default="operator-dev")
    args = parser.parse_args()

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == args.tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"no existe el tenant con slug {args.tenant_slug!r}")
            return 2

        # Misma ceremonia que la API: RLS puesta antes de escribir nada.
        await session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant.id)}
        )
        with tenant_context(tenant.id):
            device = await PartnerDeviceRepository(session).enrol(
                principal_id=args.principal,
                display_name=args.name,
                platform=args.platform,
                workdir=args.workdir,
            )
            await session.commit()
            token = issue_device_token(device_id=device.id, tenant_id=tenant.id)

    print(f"dispositivo   {device.id}")
    print(f"tenant        {tenant.slug} ({tenant.id})")
    print()
    print("AUPHERE_DEVICE_TOKEN=" + token)
    print()
    print("Se muestra una sola vez. Si lo pierdes, archiva el dispositivo y da de alta otro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
